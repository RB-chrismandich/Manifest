import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';
import { execute, extensionApi, fixture, taskWithStitchGrant, withApproval } from './ui-delivery-policy-helpers.test.mjs';

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
      isError: false, content: [{ type: 'text', text: JSON.stringify({ screenId: 'screen-17' }) }],
      details: { projectId: 'project-17' },
    });
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
      isError: false, content: [{ type: 'text', text: JSON.stringify({ screenId: 'screen-17' }) }],
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
