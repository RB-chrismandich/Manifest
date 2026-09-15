import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';
import { bindCandidate, digest, execute, extensionApi, fixture, task, taskWithStitchGrant, withApproval } from './ui-delivery-policy-helpers.test.mjs';
import { hashStitchInput } from '../runtime/ui-delivery/stitch-policy.ts';
import { loadStitchMutationState } from '../runtime/ui-delivery/evidence.ts';

test('fails package activation before registering tools when required enforcement hooks are unavailable', () => {
  const { api, tools, handlers } = extensionApi({ hooks: false });

  assert.throws(() => uiDeliveryPolicy(api), /tool_call.*tool_result|tool_result.*tool_call|enforcement hooks/i);
  assert.deepEqual(tools, []);
  assert.deepEqual([...handlers.keys()], []);
});

test('OMP hooks pass unrelated calls through and enforce the task-bound mcp__stitch_ one-shot mutation/readback flow', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  assert.deepEqual([...handlers.keys()].sort(), ['tool_call', 'tool_result']);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');
  assert.equal(await hook({ toolName: 'read', input: { path: 'x' }, toolCallId: 'native-1' }), undefined);
  const unknown = await hook({ toolName: 'mcp__stitch_unknown', input: {}, toolCallId: 'unknown-1' });
  assert.equal(unknown.block, true);
  assert.match(unknown.reason, /not authorized/i);
  const prematureMutation = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' });
  assert.equal(prematureMutation.block, true);
  assert.match(prematureMutation.reason, /not authorized/i);

  await withApproval(definition, async () => {
    const status = await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' }), undefined);
    const reusedMutation = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-3' });
    assert.equal(reusedMutation.block, true);
    assert.match(reusedMutation.reason, /reconcil|consum/i);
    await handlers.get('tool_result')({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-2', isError: false, details: { projectId: 'project-17' } });
    assert.equal(await hook({ toolName: 'mcp__stitch_get_screen', input: { projectId: 'project-17' }, toolCallId: 'readback-1' }), undefined);
    await handlers.get('tool_result')({
      toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1',
      isError: false, content: [{ type: 'text', text: JSON.stringify({ projectId: 'project-17' }) }],
      details: { projectId: 'project-17' },
    });
  });
});

test('returns unrelated authorized reads while a Stitch mutation awaits its correlated readback', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi();
  api.getAllTools = () => [
    { name: 'mcp__stitch_get_screen', sourceInfo: { source: 'mcp', path: '<mcp:stitch>' }, parameters: { type: 'object' } },
    { name: 'mcp__stitch_get_project', sourceInfo: { source: 'mcp', path: '<mcp:stitch>' }, parameters: { type: 'object' } },
    { name: 'mcp__stitch_generate_screen_from_text', sourceInfo: { source: 'mcp', path: '<mcp:stitch>' }, parameters: { type: 'object' } },
  ];
  uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);

  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    const hook = handlers.get('tool_call');
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
    await handlers.get('tool_result')({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } });
    assert.equal(await hook({ toolName: 'mcp__stitch_get_project', input: { projectId: 'project-17' }, toolCallId: 'unrelated-read-1' }), undefined);
    assert.equal(await handlers.get('tool_result')({
      toolName: 'mcp__stitch_get_project', toolCallId: 'unrelated-read-1', isError: false, details: { projectId: 'project-17' },
    }), undefined);
  });
});

test('surfaces a successful create-project result without project identity and keeps the mutation fail-closed', async () => {
  const creation = { title: 'Bounded project' };
  const definition = task({
    stitch_grant: {
      expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_create_project', input_hash: hashStitchInput(creation), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_project', predictable_fields: { title: 'Bounded project' }, resource_identity: 'project' } }],
      readback_tools: ['mcp__stitch_get_project'],
    },
  });
  const { api, tools, handlers } = extensionApi();
  api.getAllTools = () => ['create_project', 'get_project'].map((name) => ({
    name: `mcp__stitch_${name}`,
    sourceInfo: { source: 'mcp', path: '<mcp:stitch>' },
    parameters: { type: 'object' },
  }));
  uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);

  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    const hook = handlers.get('tool_call');
    assert.equal(await hook({ toolName: 'mcp__stitch_create_project', input: creation, toolCallId: 'create-1' }), undefined);
    await assert.rejects(
      () => handlers.get('tool_result')({ toolName: 'mcp__stitch_create_project', toolCallId: 'create-1', isError: false, details: {} }),
      /cannot be reconciled/i,
    );
    const retry = await hook({ toolName: 'mcp__stitch_create_project', input: creation, toolCallId: 'create-2' });
    assert.equal(retry.block, true);
    assert.match(retry.reason, /reconcil|consum/i);
  });
});

test('reconciles create-project using the resource names returned by the Stitch API', async () => {
  const creation = { title: 'Bounded project' };
  const project = { name: 'projects/12552015941655436857', title: creation.title };
  const result = {
    content: [{ type: 'text', text: JSON.stringify(project) }],
    details: { serverName: 'stitch', mcpToolName: 'create_project', rawContent: [{ type: 'text', text: JSON.stringify(project) }] },
  };
  const definition = task({
    stitch_grant: {
      expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_create_project', input_hash: hashStitchInput(creation), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_project', predictable_fields: { title: creation.title }, resource_identity: 'project' } }],
      readback_tools: ['mcp__stitch_get_project'],
    },
  });
  const { api, tools, handlers } = extensionApi();
  api.getAllTools = () => ['create_project', 'get_project'].map((name) => ({
    name: `mcp__stitch_${name}`,
    sourceInfo: { source: 'mcp', path: '<mcp:stitch>' },
    parameters: { type: 'object' },
  }));
  uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);

  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    const hook = handlers.get('tool_call');
    assert.equal(await hook({ toolName: 'mcp__stitch_create_project', input: creation, toolCallId: 'create-1' }), undefined);
    assert.equal(await handlers.get('tool_result')({ toolName: 'mcp__stitch_create_project', toolCallId: 'create-1', isError: false, ...result }), undefined);
    assert.equal(await hook({ toolName: 'mcp__stitch_get_project', input: { name: project.name }, toolCallId: 'readback-1' }), undefined);
    assert.equal(await handlers.get('tool_result')({ toolName: 'mcp__stitch_get_project', toolCallId: 'readback-1', isError: false, ...result }), undefined);
  });
});

test('surfaces mutation-result persistence failures and keeps the mutation fail-closed', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);

  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    const hook = handlers.get('tool_call');
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
    await writeFile(join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock'), '');
    await assert.rejects(
      () => handlers.get('tool_result')({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } }),
      /exist|state|lock|malformed/i,
    );
    const retry = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' });
    assert.equal(retry.block, true);
    assert.match(retry.reason, /reconcil|consum/i);
  });
});

test('approved status cannot renew a consumed Stitch mutation grant after successful readback', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  const hook = handlers.get('tool_call');

  await withApproval(definition, async () => {
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.approved, true);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
    await handlers.get('tool_result')({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } });
    assert.equal(await hook({ toolName: 'mcp__stitch_get_screen', input: { projectId: 'project-17' }, toolCallId: 'readback-1' }), undefined);
    await handlers.get('tool_result')({
      toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1',
      isError: false, content: [{ type: 'text', text: JSON.stringify({ projectId: 'project-17' }) }],
      details: { projectId: 'project-17' },
    });
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.approved, true);
    const retry = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' });
    assert.equal(retry.block, true);
    assert.match(retry.reason, /consum/i);
  });
});

test('approved status cannot clear a Stitch mutation awaiting readback', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  const hook = handlers.get('tool_call');

  await withApproval(definition, async () => {
    await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.approved, true);
    const retry = await hook({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' });
    assert.equal(retry.block, true);
    assert.match(retry.reason, /reconcil/i);
  });
});

test('a restarted extension loads the protected consumed mutation state before authorizing Stitch', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const first = extensionApi(); uiDeliveryPolicy(first.api);
  const { repo } = await fixture(definition);

  await withApproval(definition, async () => {
    await execute(first.tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await first.handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
  });

  const restarted = extensionApi(); uiDeliveryPolicy(restarted.api);
  await withApproval(definition, async () => {
    await execute(restarted.tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    const replay = await restarted.handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' });
    assert.equal(replay.block, true);
    assert.match(replay.reason, /reconcil|consum/i);
  });
});

test('reviewer accepted status preserves builder mutation replay protection through a transition and restart', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const builder = taskWithStitchGrant(input);
  const first = extensionApi(); uiDeliveryPolicy(first.api);
  const { repo } = await fixture(builder);
  const taskFile = join(repo, '.omp/ui-delivery/tasks/task.json');

  await withApproval(builder, async () => {
    await execute(first.tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await first.handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
  });

  const reviewer = {
    ...builder, state: 'accepted', model_route: '@ui_review', outcome: 'verified',
    candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'],
  };
  await bindCandidate(repo, reviewer);
  const restarted = extensionApi(); uiDeliveryPolicy(restarted.api);
  await withApproval(reviewer, async () => {
    const status = await execute(restarted.tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.authorizationDigest, digest(reviewer));
  });

  await writeFile(taskFile, JSON.stringify(builder));
  await withApproval(builder, async () => {
    await execute(restarted.tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    const replay = await restarted.handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' });
    assert.equal(replay.block, true);
    assert.match(replay.reason, /reconcil|consum/i);
  });
});

test('revalidates the task lifecycle before each Stitch call instead of using an approved status snapshot', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);

  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify({ ...definition, state: 'candidate_ready', candidate_revision: 'git:stale', candidate_hash: `sha256:${'a'.repeat(64)}` }));
    const blocked = await handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' });
    assert.equal(blocked.block, true);
    assert.match(blocked.reason, /stale|authorized/i);
  });
});

test('binds Stitch mutation state to the canonical repository, not just the authorization digest', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = taskWithStitchGrant(input);
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const repoA = await fixture(definition);
  const repoB = await fixture(definition);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  const authDigest = digest(definition);

  await withApproval(definition, async () => {
    await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repoA.repo);
    await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repoB.repo);
    assert.equal(await handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-1' }), undefined);
    await handlers.get('tool_result')({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'edit-1', isError: false, details: { projectId: 'project-17' } });
  });

  const stateB = await loadStitchMutationState({ repo: repoB.repo, taskId: definition.task_id, authorizationDigest: authDigest });
  assert.ok(stateB, 'the second repository must record its own mutation state');
  const stateA = await loadStitchMutationState({ repo: repoA.repo, taskId: definition.task_id, authorizationDigest: authDigest });
  assert.equal(stateA, undefined, 'the first repository must not absorb a mutation issued after the second repository was activated');

  await withApproval(definition, async () => {
    await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repoA.repo);
    const replay = await handlers.get('tool_call')({ toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'edit-2' });
    assert.equal(replay, undefined, 'repository A must still be able to authorize its own untouched mutation grant');
  });
});
