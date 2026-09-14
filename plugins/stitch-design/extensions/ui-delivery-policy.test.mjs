import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { hashStitchInput } from '../runtime/ui-delivery/stitch-policy.ts';
import uiDeliveryPolicy, { registerUiDeliveryPolicy } from './ui-delivery-policy.ts';

function extensionApi() {
  const tools = []; const handlers = new Map();
  const schema = { strict: () => schema, optional: () => schema };
  return {
    tools, handlers,
    api: {
      zod: { object: () => schema, string: () => schema },
      registerTool: (tool) => tools.push(tool),
      on: (event, handler) => handlers.set(event, handler),
      getAllTools: () => [
        { name: 'mcp__stitch__get_screen', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: { type: 'object' } },
        { name: 'mcp__stitch__edit_screen', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: { type: 'object' } },
      ],
    },
  };
}

function execute(tool, args, cwd, signal = new AbortController().signal) {
  return tool.execute('call', args, signal, () => {}, { cwd });
}

function task(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [{
      id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
      backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
      write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
    }],
    capture_recipes: [{ id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }] }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
    ...overrides,
  };
}

function digest(value) {
  const canonical = (entry) => Array.isArray(entry) ? entry.map(canonical)
    : entry && typeof entry === 'object' ? Object.fromEntries(Object.keys(entry).sort().map((key) => [key, canonical(entry[key])])) : entry;
  const projection = Object.fromEntries(['task_id', 'design_revision', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant']
    .filter((key) => key in value).map((key) => [key, value[key]]));
  return `sha256:${createHash('sha256').update(JSON.stringify(canonical(projection))).digest('hex')}`;
}

async function fixture(definition = task()) {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-policy-'));
  await Promise.all(['src', '.ui-results', 'evidence', '.omp/ui-delivery/tasks', '.omp/ui-delivery/evidence'].map((path) => mkdir(join(repo, path), { recursive: true })));
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'prior capture');
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify(definition));
  return { repo, definition };
}

async function withoutApproval(operation) {
  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  try { return await operation(); } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
  }
}

test('registers the deterministic UI delivery surface with exact OMP approval tiers', () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  assert.deepEqual(tools.map((tool) => tool.name).sort(), ['ui_apply_patch', 'ui_capture', 'ui_delivery_status', 'ui_run_check']);
  assert.deepEqual(Object.fromEntries(tools.map((tool) => [tool.name, tool.approval])), {
    ui_delivery_status: 'read', ui_apply_patch: 'write', ui_run_check: 'exec', ui_capture: 'exec',
  });
});

test('requires the external digest for patch, check, and capture even when repository JSON self-approves', async () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  const { repo } = await fixture();
  for (const [name, args] of [
    ['ui_apply_patch', { taskFile: '.omp/ui-delivery/tasks/task.json', patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-x\n+y\n' }],
    ['ui_run_check', { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }],
    ['ui_capture', { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'capture' }],
  ]) {
    const tool = tools.find((entry) => entry.name === name);
    await withoutApproval(() => assert.rejects(() => execute(tool, args, repo), /approval/i));
  }
});

test('fails closed on every unparseable, alternate, destructive, or symlink diff entry', async () => {
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo, definition } = await fixture();
  const tool = tools.find((entry) => entry.name === 'ui_apply_patch');
  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  try {
    for (const patch of [
      'diff --git x/src/Card.tsx y/.omp/ui-delivery/tasks/task.json\n--- x/src/Card.tsx\n+++ y/.omp/ui-delivery/tasks/task.json\n',
      'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ /dev/null\n',
      'diff --git a/src/Card.tsx b/src/Card.tsx\nnew mode 120000\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n',
      'diff --git a/src/Card.tsx b/src/Renamed.tsx\nsimilarity index 100%\nrename from src/Card.tsx\nrename to src/Renamed.tsx\n',
    ]) await assert.rejects(
      () => execute(tool, { taskFile: '.omp/ui-delivery/tasks/task.json', patch }, repo),
      /unsafe|unparseable|destructive|symlink|diff policy/i,
    );
  } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256; else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
  }
});

function candidateHash() {
  return `sha256:${createHash('sha256').update('export const Card = 1;\n').digest('hex')}`;
}

function policyWithCheckRunner(api, runCheck) {
  return registerUiDeliveryPolicy(api, { runCheck });
}

function success() {
  return { exitCode: 0, stdout: { hash: 'sha256:stdout' }, stderr: { hash: 'sha256:stderr' } };
}

test('rejects a wrong candidate hash before executing an approved check', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi(); let calls = 0;
  policyWithCheckRunner(api, async () => { calls += 1; return success(); });
  const { repo } = await fixture(definition);
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /candidate/i);
  assert.equal(calls, 0);
});

test('rejects a fresh zero-exit check result that reports skipped required checks', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: candidateHash() });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 0, failed: 0, skipped: 1 }));
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /skipped|unverified/i);
});

test('rejects capture when a successful check leaves its nonempty artifact unchanged', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: candidateHash() });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_capture'), { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'capture' }, repo), /stale|fresh|artifact/i);
});

test('status never reports accepted work verified without matching local evidence', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://missing'],
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const response = await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
  assert.equal(response.details.outcome, 'evidence_unverified');
  assert.equal(response.details.approved, false);
  assert.match(response.details.authorizationDigest, /^sha256:[a-f0-9]{64}$/);
});
test('OMP hooks pass unrelated calls through and enforce the task-bound mcp__stitch__ one-shot mutation/readback flow', async () => {
  const input = { screenId: 'screen-17', projectId: 'project-17', prompt: 'compact header' };
  const definition = task({
    stitch_grant: {
      project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch__edit_screen', input_hash: hashStitchInput(input), max_uses: 1 }],
      readback_tools: ['mcp__stitch__get_screen'],
    },
  });
  const { api, tools, handlers } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const hook = handlers.get('tool_call');
  assert.equal(await hook({ toolName: 'read', input: { path: 'x' }, toolCallId: 'native-1' }), undefined);
  const unknown = await hook({ toolName: 'mcp__stitch__unknown', input: {}, toolCallId: 'unknown-1' });
  assert.equal(unknown.block, true);
  assert.match(unknown.reason, /not authorized/i);
  const prematureMutation = await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-1' });
  assert.equal(prematureMutation.block, true);
  assert.match(prematureMutation.reason, /not authorized/i);

  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  try {
    const status = await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(status.details.approved, true);
    assert.equal(await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-2' }), undefined);
    const reusedMutation = await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-3' });
    assert.equal(reusedMutation.block, true);
    assert.match(reusedMutation.reason, /reconcil|consum/i);
    await handlers.get('tool_result')({
      toolName: 'mcp__stitch__get_screen',
      isError: false,
      content: [{ type: 'text', text: JSON.stringify({ screenId: 'screen-17' }) }],
      details: { projectId: 'project-17' },
    });
  } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256; else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
  }
});
