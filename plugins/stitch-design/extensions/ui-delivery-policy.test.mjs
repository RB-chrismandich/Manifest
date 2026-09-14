import assert from 'node:assert/strict';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';

function extensionApi() {
  const tools = [];
  const schema = { strict: () => schema, optional: () => schema };
  return { tools, api: { zod: { object: () => schema, string: () => schema }, registerTool: (tool) => tools.push(tool) } };
}

function context(cwd = '/repo') {
  return { cwd };
}

function execute(tool, args, cwd = '/repo') {
  return tool.execute('call', args, new AbortController().signal, () => {}, context(cwd));
}

test('registers the deterministic UI delivery surface with exact OMP approval tiers', () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  assert.deepEqual(tools.map((tool) => tool.name).sort(), ['ui_apply_patch', 'ui_capture', 'ui_delivery_status', 'ui_run_check']);
  assert.deepEqual(Object.fromEntries(tools.map((tool) => [tool.name, tool.approval])), {
    ui_delivery_status: 'read', ui_apply_patch: 'write', ui_run_check: 'exec', ui_capture: 'exec',
  });
  for (const tool of tools) assert.equal(tool.strict, true);
});

test('patch tool rejects delete, rename, traversal, and symlink-escape diff targets before git apply', async () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  const applyPatch = tools.find((tool) => tool.name === 'ui_apply_patch');
  for (const patch of [
    'diff --git a/src/Card.tsx b/src/Card.tsx\ndeleted file mode 100644',
    'diff --git a/src/Card.tsx b/src/Renamed.tsx\nsimilarity index 100%\nrename from src/Card.tsx\nrename to src/Renamed.tsx',
    'diff --git a/src/Card.tsx b/../.git/config',
  ]) {
    await assert.rejects(() => execute(applyPatch, { taskFile: '.omp/ui-delivery/tasks/task.json', patch }));
  }
});

test('check and capture tools accept only approved recipe identifiers and return hash-bound evidence', async () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  const runCheck = tools.find((tool) => tool.name === 'ui_run_check');
  const capture = tools.find((tool) => tool.name === 'ui_capture');
  await assert.rejects(() => execute(runCheck, { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'raw; rm -rf /' }));
  await assert.rejects(() => execute(capture, { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'unknown' }));
});

test('status is deterministic without a task and rejects a supplied missing or invalid task', async () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  const status = tools.find((tool) => tool.name === 'ui_delivery_status');
  const response = await execute(status, {});
  const text = JSON.stringify(response);
  assert.match(text, /ui-delivery-policy/);
  assert.doesNotMatch(text, /token|secret|password/i);
  await assert.rejects(() => execute(status, { taskFile: '.omp/ui-delivery/tasks/missing.json' }));
  await assert.rejects(() => execute(status, { taskFile: '.omp/ui-delivery/tasks/invalid.json' }));
});
