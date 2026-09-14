import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { appendFile, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { hashStitchInput } from '../runtime/ui-delivery/stitch-policy.ts';
import uiDeliveryPolicy, { registerUiDeliveryPolicy } from './ui-delivery-policy.ts';
import { candidateHash as calculateCandidateHash } from '../runtime/ui-delivery/task.ts';

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
    approved_check_recipes: [
      {
        id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
        backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
        write_paths: ['.ui-results/unit.json'],
      },
      {
        id: 'capture-unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
        backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
        write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
      },
    ],
    capture_recipes: [{ id: 'capture', check_id: 'capture-unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }] }],
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

async function withApproval(definition, operation) {
  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
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
  for (const [name, args, definition] of [
    ['ui_apply_patch', { taskFile: '.omp/ui-delivery/tasks/task.json', patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-x\n+y\n' }, task()],
    ['ui_run_check', { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` })],
    ['ui_capture', { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'capture' }, task({ state: 'reviewing', model_route: '@ui_review', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` })],
  ]) {
    const { repo } = await fixture(definition);
    if (name !== 'ui_apply_patch') {
      definition.candidate_hash = await calculateCandidateHash({ repo, task: definition });
      await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify(definition));
    }
    const tool = tools.find((entry) => entry.name === name);
    await withoutApproval(() => assert.rejects(() => execute(tool, args, repo), /approval/i));
  }
});

test('fails closed on every unparseable, alternate, destructive, or symlink diff entry', async () => {
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo, definition } = await fixture();
  const tool = tools.find((entry) => entry.name === 'ui_apply_patch');
  await withApproval(definition, async () => {
    for (const patch of [
      'diff --git x/src/Card.tsx y/.omp/ui-delivery/tasks/task.json\n--- x/src/Card.tsx\n+++ y/.omp/ui-delivery/tasks/task.json\n',
      'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ /dev/null\n',
      'diff --git a/src/Card.tsx b/src/Card.tsx\nnew mode 120000\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n',
      'diff --git a/src/Card.tsx b/src/Renamed.tsx\nsimilarity index 100%\nrename from src/Card.tsx\nrename to src/Renamed.tsx\n',
    ]) await assert.rejects(
      () => execute(tool, { taskFile: '.omp/ui-delivery/tasks/task.json', patch }, repo),
      /unsafe|unparseable|destructive|symlink|diff policy/i,
    );
  });
});

test('applies a same-path regular diff with standard index metadata', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\nindex 1111111111111111111111111111111111111111..2222222222222222222222222222222222222222 100644\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/Card.tsx'), 'utf8'), 'export const Card = 2;\n');
});

test('applies same-file hunks whose payload lines resemble unified-diff file headers', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await writeFile(join(repo, 'src/Card.tsx'), '-- example\n');
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n--- example\n+++ example\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/Card.tsx'), 'utf8'), '++ example\n');
});

test('rejects a same-file hunk whose declared line count does not match its payload', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1,2 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo), /malformed|unparseable|hunk/i));
});

test('applies an absolute task file patch and updates that validated task', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const taskFile = join(repo, '.omp/ui-delivery/tasks/task.json');
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile,
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo));
  assert.equal(JSON.parse(await readFile(taskFile, 'utf8')).state, 'candidate_ready');
});

test('applies a standard new regular-file diff', async () => {
  const definition = task({ allowed_paths: ['src/New.tsx'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/New.tsx b/src/New.tsx\nnew file mode 100644\nindex 0000000000000000000000000000000000000000..2222222222222222222222222222222222222222\n--- /dev/null\n+++ b/src/New.tsx\n@@ -0,0 +1 @@\n+export const New = 1;\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/New.tsx'), 'utf8'), 'export const New = 1;\n');
});

test('accepts a safe new regular-file diff without optional index metadata', async () => {
  const definition = task({ allowed_paths: ['src/NoIndex.tsx'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/NoIndex.tsx b/src/NoIndex.tsx\nnew file mode 100644\n--- /dev/null\n+++ b/src/NoIndex.tsx\n@@ -0,0 +1 @@\n+export const NoIndex = 1;\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/NoIndex.tsx'), 'utf8'), 'export const NoIndex = 1;\n');
});

test('rejects malformed present index metadata on a new regular-file diff', async () => {
  const definition = task({ allowed_paths: ['src/Malformed.tsx'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Malformed.tsx b/src/Malformed.tsx\nnew file mode 100644\nindex not-an-index\n--- /dev/null\n+++ b/src/Malformed.tsx\n@@ -0,0 +1 @@\n+export const Malformed = 1;\n',
  }, repo), /malformed|unparseable/i));
});

test('creates a missing trusted evidence directory before recording a patch and check', async () => {
  const definition = task();
  const { api, tools } = extensionApi();
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  const { repo } = await fixture(definition);
  await rm(join(repo, '.omp/ui-delivery/evidence'), { recursive: true });
  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
      taskFile: '.omp/ui-delivery/tasks/task.json',
      patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
    }, repo);
    await execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo);
  });
  assert.match(await readFile(join(repo, '.omp/ui-delivery/evidence/task-17.jsonl'), 'utf8'), /ui_run_check/);
});

test('rejects an unsafe evidence directory before updating the candidate task', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-evidence-outside-'));
  await rm(join(repo, '.omp/ui-delivery/evidence'), { recursive: true });
  await symlink(outside, join(repo, '.omp/ui-delivery/evidence'));
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo), /symlink|evidence|policy/i));
  const persisted = JSON.parse(await readFile(join(repo, '.omp/ui-delivery/tasks/task.json'), 'utf8'));
  assert.equal(persisted.state, 'approved');
  assert.equal(persisted.candidate_hash, undefined);
});

async function bindCandidate(repo, definition) {
  definition.candidate_hash = await calculateCandidateHash({ repo, task: definition });
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify(definition));
}

function policyWithCheckRunner(api, runCheck) {
  return registerUiDeliveryPolicy(api, { runCheck });
}

function success() {
  return { exitCode: 0, stdout: { hash: 'sha256:stdout' }, stderr: { hash: 'sha256:stderr' } };
}

function evidenceRecord(definition, { attemptId, attemptPhase, operation = 'ui_run_check', outcome, artifacts = [], ...extra }) {
  const evidenceTask = operation === 'ui_run_check' ? { ...definition, model_route: '@ui_code' } : definition;
  return {
    taskId: definition.task_id, approvedDesignHash: definition.design_revision,
    candidateRevision: definition.candidate_revision, candidateHash: definition.candidate_hash,
    modelRoute: evidenceTask.model_route, authorizationDigest: digest(evidenceTask),
    attemptId, attemptPhase, operation, outcome, elapsedMs: 0, artifacts,
    stdoutHash: 'sha256:stdout', stderrHash: 'sha256:stderr', ...extra,
  };
}

async function appendAttempt(evidenceFile, definition, { attemptId, operation, outcome, artifacts = [], ...extra }) {
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId, attemptPhase: 'started', operation, outcome: 'pending', ...extra }))}\n`);
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId, attemptPhase: 'completed', operation, outcome, artifacts, ...extra }))}\n`);
}

async function appendCaptureEvidence(evidenceFile, definition, repo, attemptId = 'capture-1') {
  const page = await readFile(join(repo, 'evidence/page.png'));
  await appendAttempt(evidenceFile, definition, {
    attemptId, operation: 'ui_capture', recipeId: 'capture', outcome: 'captured',
    artifacts: [{ path: 'evidence/page.png', hash: `sha256:${createHash('sha256').update(page).digest('hex')}` }],
  });
}

test('patch atomically binds the candidate, preserves authorization, records evidence, and enables its check', async () => {
  const definition = task();
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  try {
    const patch = 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n';
    const applied = await execute(tools.find((entry) => entry.name === 'ui_apply_patch'), { taskFile: '.omp/ui-delivery/tasks/task.json', patch }, repo);
    assert.equal(applied.details.state, 'candidate_ready');
    assert.match(applied.details.candidateRevision, /^git:/);
    assert.match(applied.details.candidateHash, /^sha256:[a-f0-9]{64}$/);
    assert.equal(applied.details.authorizationDigest, digest(definition));
    const updated = JSON.parse(await readFile(join(repo, '.omp/ui-delivery/tasks/task.json'), 'utf8'));
    assert.equal(updated.state, 'candidate_ready');
    assert.equal(updated.candidate_hash, applied.details.candidateHash);
    assert.match(await readFile(join(repo, '.omp/ui-delivery/evidence', 'task-17.jsonl'), 'utf8'), /ui_apply_patch/);
    await execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo);
  } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256; else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
  }
});

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
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 0, failed: 0, skipped: 1 }));
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /skipped|unverified/i);
});

test('rejects a zero-exit runner that leaves a pre-existing successful result unchanged', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
  policyWithCheckRunner(api, async () => success());
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /fresh|stale|result/i);
});

test('rejects capture when a successful check leaves its nonempty artifact unchanged', async () => {
  const definition = task({ state: 'reviewing', model_route: '@ui_review', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_capture'), { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'capture' }, repo), /stale|fresh|artifact/i);
});

test('status requires candidate-bound evidence for every approved check and capture before verified', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
    approved_check_recipes: [
      ...task().approved_check_recipes,
      { ...task().approved_check_recipes[0], id: 'visual', result_path: '.ui-results/visual.json', write_paths: ['.ui-results/visual.json'] },
    ],
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await writeFile(join(repo, '.ui-results/visual.json'), '{"prior":true}\n');
  await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
  await appendAttempt(evidenceFile, definition, { attemptId: 'visual-1', operation: 'ui_run_check', checkId: 'visual', outcome: 'verified' });
  const page = await readFile(join(repo, 'evidence/page.png'));
  await appendAttempt(evidenceFile, definition, {
    attemptId: 'capture-1', operation: 'ui_capture', recipeId: 'capture', outcome: 'captured',
    artifacts: [{ path: 'evidence/page.png', hash: `sha256:${createHash('sha256').update(page).digest('hex')}` }],
  });
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
  await appendAttempt(evidenceFile, definition, {
    attemptId: 'unit-2', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified',
    modelRoute: '@ui_review', authorizationDigest: digest(definition),
  });
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
  await appendAttempt(evidenceFile, definition, {
    attemptId: 'unit-3', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified',
    authorizationDigest: digest(definition),
  });
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status invalidates historical check success after the latest rerun is unfinished or failed', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
  await appendCaptureEvidence(evidenceFile, definition, repo);
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId: 'unit-2', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending' }))}\n`);
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId: 'unit-2', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'failed' }))}\n`);
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status cannot let an older concurrent completion override a later-started failed attempt', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendCaptureEvidence(evidenceFile, definition, repo);
  for (const entry of [
    evidenceRecord(definition, { attemptId: 'unit-old', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending' }),
    evidenceRecord(definition, { attemptId: 'unit-new', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending' }),
    evidenceRecord(definition, { attemptId: 'unit-new', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'failed' }),
    evidenceRecord(definition, { attemptId: 'unit-old', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' }),
  ]) await appendFile(evidenceFile, `${JSON.stringify(entry)}\n`);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status cannot reuse evidence whose authorization digest predates an otherwise identical recipe ID', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const oldDigest = digest({ ...definition, approved_check_recipes: [{ ...definition.approved_check_recipes[0], argv: ['node', '--test', 'old.mjs'] }] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendCaptureEvidence(evidenceFile, definition, repo);
  for (const entry of [
    evidenceRecord(definition, { attemptId: 'unit-1', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending', authorizationDigest: oldDigest }),
    evidenceRecord(definition, { attemptId: 'unit-1', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified', authorizationDigest: oldDigest }),
  ]) await appendFile(evidenceFile, `${JSON.stringify(entry)}\n`);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status requires builder checks only for unreferenced recipes and reviewer capture for capture-only recipes', async () => {
  const captureCheck = task().approved_check_recipes.find((recipe) => recipe.id === 'capture-unit');
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
    approved_check_recipes: [captureCheck, { ...captureCheck, id: 'build', result_path: '.ui-results/build.json', write_paths: ['.ui-results/build.json'] }],
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendAttempt(evidenceFile, definition, { attemptId: 'build-1', operation: 'ui_run_check', checkId: 'build', outcome: 'verified' });
  await appendCaptureEvidence(evidenceFile, definition, repo);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
});

test('rejects ui_run_check for a capture-only recipe before invoking the runner', async () => {
  const captureCheck = task().approved_check_recipes.find((recipe) => recipe.id === 'capture-unit');
  const definition = task({
    state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}`,
    approved_check_recipes: [captureCheck, { ...captureCheck, id: 'build', result_path: '.ui-results/build.json', write_paths: ['.ui-results/build.json'] }],
  });
  const { api, tools } = extensionApi(); let calls = 0;
  policyWithCheckRunner(api, async () => {
    calls += 1;
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), {
    taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'capture-unit',
  }, repo), /capture|review/i));
  assert.equal(calls, 0);
});

test('status requires current regular capture artifacts with exact complete hashes', async () => {
  for (const scenario of ['missing', 'replaced', 'symlinked', 'wrong hash', 'incomplete']) {
    const definition = task({
      state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
      candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
      approved_check_recipes: [{ ...task().approved_check_recipes[0], write_paths: ['.ui-results/unit.json', 'evidence/page.png', 'evidence/other.png'] }],
      capture_recipes: [{ id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }, { path: 'evidence/other.png', type: 'screenshot' }] }],
    });
    const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
    const { repo } = await fixture(definition);
    await writeFile(join(repo, 'evidence/other.png'), 'other capture');
    await bindCandidate(repo, definition);
    const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
    const paths = ['evidence/page.png', 'evidence/other.png'];
    const artifacts = await Promise.all(paths.map(async (path) => ({ path, hash: `sha256:${createHash('sha256').update(await readFile(join(repo, path))).digest('hex')}` })));
    await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
    await appendAttempt(evidenceFile, definition, { attemptId: 'capture-1', operation: 'ui_capture', recipeId: 'capture', outcome: 'captured', artifacts });
    const status = tools.find((entry) => entry.name === 'ui_delivery_status');
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
    if (scenario === 'missing') await rm(join(repo, 'evidence/page.png'));
    if (scenario === 'replaced') await writeFile(join(repo, 'evidence/page.png'), 'replacement capture');
    if (scenario === 'symlinked') {
      await rm(join(repo, 'evidence/page.png'));
      await symlink(join(repo, 'evidence/other.png'), join(repo, 'evidence/page.png'));
    }
    const badArtifacts = scenario === 'wrong hash' ? [{ ...artifacts[0], hash: `sha256:${'0'.repeat(64)}` }, artifacts[1]]
      : scenario === 'incomplete' ? [artifacts[0]] : artifacts;
    await appendAttempt(evidenceFile, definition, { attemptId: 'capture-2', operation: 'ui_capture', recipeId: 'capture', outcome: 'captured', artifacts: badArtifacts });
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false, scenario);
  }
});

test('status never reports accepted work verified without matching local evidence', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://missing'], model_route: '@ui_review',
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

test('approved status cannot renew a consumed Stitch mutation grant after successful readback', async () => {
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
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  const hook = handlers.get('tool_call');

  await withApproval(definition, async () => {
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.approved, true);
    assert.equal(await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-1' }), undefined);
    await handlers.get('tool_result')({
      toolName: 'mcp__stitch__get_screen',
      isError: false,
      content: [{ type: 'text', text: JSON.stringify({ screenId: 'screen-17' }) }],
      details: { projectId: 'project-17' },
    });
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.approved, true);
    const retry = await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-2' });
    assert.equal(retry.block, true);
    assert.match(retry.reason, /consum/i);
  });
});

test('approved status cannot clear a Stitch mutation awaiting readback', async () => {
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
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  const hook = handlers.get('tool_call');

  await withApproval(definition, async () => {
    await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
    assert.equal(await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-1' }), undefined);
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.approved, true);
    const retry = await hook({ toolName: 'mcp__stitch__edit_screen', input, toolCallId: 'edit-2' });
    assert.equal(retry.block, true);
    assert.match(retry.reason, /reconcil/i);
  });
});
