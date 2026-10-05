import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';
import { digest, execute, extensionApi, fixture, task, taskWithStitchGrant, withApproval } from './ui-delivery-policy-helpers.test.mjs';
import { hashStitchInput } from '../runtime/ui-delivery/stitch-policy.ts';
import { loadStitchMutationState, updateStitchMutationState } from '../runtime/ui-delivery/evidence.ts';

test('falls back to unbound reads when a bound task goes stale, keeping mutations fail-closed', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');

  await withApproval(definition, async () => {
    const status = await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    // Live binding: reads outside the approved project stay fail-closed.
    const foreignRead = await hook({ toolName: 'mcp__stitch_get_project', input: { projectId: 'project-999' }, toolCallId: 'foreign-read-1' });
    assert.equal(foreignRead.block, true);
  });

  // Binding is now stale: the env digest is gone, so the binding checks reject
  // and stitch is cleared — reads pass unbound, mutations still block.
  for (const toolName of ['mcp__stitch_get_screen', 'mcp__stitch_list_projects']) {
    assert.equal(await hook({ toolName, input: { projectId: 'project-17' }, toolCallId: `stale-${toolName}` }), undefined, `${toolName} must pass once the binding is stale`);
  }
  const mutation = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'stale-edit-1' });
  assert.equal(mutation.block, true);
  assert.match(mutation.reason, /stale|not authorized|digest|invalid/i);
  // A read result that was in flight when the binding died is ignored, not thrown.
  assert.equal(await handlers.get('tool_result')({ toolName: 'mcp__stitch_list_projects', toolCallId: 'stale-mcp__stitch_list_projects', isError: false, details: {} }), undefined);
});

test('an in-flight mutation result still surfaces loudly after the binding goes stale', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');

  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
  });

  // Env digest is gone: the dispatch was authorized but the binding is stale
  // by the time the result arrives. The result must report "stale", not be
  // silently ignored as if no mutation was ever dispatched.
  await assert.rejects(
    () => handlers.get('tool_result')({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } }),
    /stale/i,
  );
});

test('re-approving a task revives a stale binding instead of staying dead', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');
  const statusTool = tools.find((entry) => entry.name === 'ui_delivery_status');

  await withApproval(definition, async () => {
    await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
  });
  // Drive staleness once so live flips false.
  const staleMutation = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'stale-1' });
  assert.equal(staleMutation.block, true);

  // Re-approve the same task: status must rebind (live flag no longer blocks),
  // and the granted mutation is authorized again.
  await withApproval(definition, async () => {
    const status = await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' }), undefined);
  });
});

test('an in-flight mutation reconciles through a re-approved binding via carried correlations', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');
  const result = handlers.get('tool_result');
  const statusTool = tools.find((entry) => entry.name === 'ui_delivery_status');

  // Dispatch a granted mutation; its result never arrives before staleness.
  await withApproval(definition, async () => {
    await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
  });
  // Force the staleness flip while the mutation is still pending.
  const staleRead = await hook({ toolName: 'mcp__stitch_list_projects', input: {}, toolCallId: 'probe-1' });
  assert.equal(staleRead, undefined);

  // Re-approve the same task: the new binding must carry edit-1's correlation
  // or the late result throws 'cannot be reconciled' and orphans the grant.
  await withApproval(definition, async () => {
    const status = await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    assert.equal(await result({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } }), undefined);
  });
});

test('switching task files does not carry correlations across grants', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definitionA = taskWithStitchGrant(input);
  const definitionB = taskWithStitchGrant(input); // same grant, different task
  definitionB.task_id = 'task-42';
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definitionA);
  const hook = handlers.get('tool_call');
  const result = handlers.get('tool_result');
  const statusTool = tools.find((entry) => entry.name === 'ui_delivery_status');
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task-b.json'), JSON.stringify(definitionB));
  // Seed task B's persisted mutation state with a pending entry for the same
  // toolName:inputHash, so an incorrectly carried edit-a could consume it.
  const entryKey = `mcp__stitch_generate_screen_from_text:${hashStitchInput(input)}`;
  await updateStitchMutationState({ repo, taskId: 'task-42', authorizationDigest: digest(definitionB), expectedVersion: 0, state: { entries: { [entryKey]: 'pending' } } });

  // Bind task A, dispatch its granted mutation (pending, in-flight).
  await withApproval(definitionA, async () => {
    await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-a' }), undefined);
  });

  // Re-approve onto task B: A's toolCallId must not be carried, so B's grant
  // stays unconsumed and A's late result fails loudly instead of reconciling.
  await withApproval(definitionB, async () => {
    const status = await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task-b.json' }, repo);
    assert.equal(status.details.approved, true);
    await assert.rejects(
      () => result({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-a', isError: false, details: { projectId: 'project-17' } }),
      /reconcil|stale/i,
    );
    // B's own pending grant is also protected: a new mutation must wait for
    // its readback, not silently reuse the same input hash.
    const blocked = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-b' });
    assert.equal(blocked.block, true);
    assert.match(blocked.reason, /reconcil/i);
  });
});

test('a late result rejected as stale does not poison the revived binding', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');
  const result = handlers.get('tool_result');
  const statusTool = tools.find((entry) => entry.name === 'ui_delivery_status');

  // Dispatch the granted mutation; the result arrives only after staleness.
  await withApproval(definition, async () => {
    await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
  });
  // Late result on the stale binding: loud rejection, and the correlation is
  // settled so it cannot be carried into the revival.
  await assert.rejects(
    () => result({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } }),
    /stale/i,
  );

  // Re-approve the same task: the replayed result still rejects (its call ID
  // was settled), but the pending entry reconciles via the readback.
  await withApproval(definition, async () => {
    const status = await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    await assert.rejects(
      () => result({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } }),
      /reconcil/i,
    );
    const readback = await hook({ toolName: 'mcp__stitch_get_screen', input: { projectId: 'project-17' }, toolCallId: 'read-1' });
    assert.equal(readback, undefined);
    assert.equal(await result({ toolName: 'mcp__stitch_get_screen', toolCallId: 'read-1', isError: false, details: { projectId: 'project-17' } }), undefined);
    const state = await loadStitchMutationState({ repo, taskId: definition.task_id, authorizationDigest: digest(definition) });
    assert.equal(state?.entries[`mcp__stitch_generate_screen_from_text:${hashStitchInput(input)}`], 'reconciled');
  });
});

test('a stale create_project result preserves the returned project ID for revival', async () => {
  const creation = { title: 'Bounded project' };
  const project = { name: 'projects/12552015941655436857', title: creation.title };
  const definition = task({
    stitch_grant: {
      expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_create_project', input_hash: hashStitchInput(creation), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_project', predictable_fields: { title: creation.title }, resource_identity: 'project' } }],
      readback_tools: ['mcp__stitch_get_project'],
    },
  });
  const { api, tools, handlers } = extensionApi();
  api.getAllTools = () => ['create_project', 'get_project'].map((name) => ({
    name: `mcp__stitch_${name}`, sourceInfo: { source: 'mcp', path: '<mcp:stitch>' }, parameters: { type: 'object' },
  }));
  uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');
  const result = handlers.get('tool_result');
  const statusTool = tools.find((entry) => entry.name === 'ui_delivery_status');
  const created = {
    content: [{ type: 'text', text: JSON.stringify(project) }],
    details: { serverName: 'stitch', mcpToolName: 'create_project', rawContent: [{ type: 'text', text: JSON.stringify(project) }] },
  };

  // Dispatch create_project; the success result lands after staleness.
  await withApproval(definition, async () => {
    await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch_create_project', input: creation, toolCallId: 'create-1' }), undefined);
  });
  await assert.rejects(
    () => result({ toolName: 'mcp__stitch_create_project', toolCallId: 'create-1', isError: false, ...created }),
    /stale/i,
  );

  // The created project survives re-approval: the pending entry reconciles
  // through get_project instead of orphaning the external resource.
  await withApproval(definition, async () => {
    const status = await execute(statusTool, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    const readback = await hook({ toolName: 'mcp__stitch_get_project', input: { name: project.name }, toolCallId: 'readback-1' });
    assert.equal(readback, undefined);
    assert.equal(await result({ toolName: 'mcp__stitch_get_project', toolCallId: 'readback-1', isError: false, ...created }), undefined);
    const state = await loadStitchMutationState({ repo, taskId: definition.task_id, authorizationDigest: digest(definition) });
    assert.equal(state?.projectId, '12552015941655436857');
    assert.equal(state?.entries[`mcp__stitch_create_project:${hashStitchInput(creation)}`], 'reconciled');
  });
});
