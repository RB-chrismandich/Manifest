import assert from 'node:assert/strict';
import { execFile as executeFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmod, mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import { beginPatchJournal, candidateHash, loadTask, releasePatchJournal } from './task.ts';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function authorizationDigest(task) {
  const projection = Object.fromEntries([
    'task_id', 'design_revision', 'qualification_hash', 'allowed_paths', 'forbidden_policy_paths',
    'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant', 'repair_authorization',
  ].filter((key) => key in task).map((key) => [key, task[key]]));
  return `sha256:${createHash('sha256').update(JSON.stringify(canonical(projection))).digest('hex')}`;
}

function approvedTask(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    qualification_hash: `sha256:${'a'.repeat(64)}`, allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [{
      id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
      backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
      write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
      trusted_verifier: { path: '.omp/ui-delivery/verifiers/unit.mjs', sha256: `sha256:${'b'.repeat(64)}` },
    }],
    capture_recipes: [{
      id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }],
    }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
    ...overrides,
  };
}

async function taskFile(task, relative = '.omp/ui-delivery/tasks/task-17.json') {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-task-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await mkdir(join(repo, '.ui-results'), { recursive: true });
  await mkdir(join(repo, 'evidence'), { recursive: true });
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'prior capture');
  const path = join(repo, relative);
  await mkdir(join(path, '..'), { recursive: true });
  await writeFile(path, JSON.stringify(approvedTask(task)));
  return { repo, path };
}

async function withApproval(task, operation) {
  const before = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  const activeBefore = process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = authorizationDigest(task);
  process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = task.qualification_hash;
  try { return await operation(); } finally {
    if (before === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = before;
    if (activeBefore === undefined) delete process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
    else process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = activeBefore;
  }
}

const execFile = promisify(executeFile);

test('requires an external authorization digest for every mutation and executable task load', async () => {
  const definition = approvedTask();
  const { repo, path } = await taskFile(definition);
  delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }));
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = 'sha256:0'.padEnd(71, '0');
  await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }));
  await withApproval(definition, () => loadTask({ repo, taskFile: path, operation: 'patch' }));
});

test('rejects a repository task that self-asserts approved without the parent authorization digest', async () => {
  const definition = approvedTask({ state: 'approved' });
  const { repo, path } = await taskFile(definition);
  delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }), /approval/i);
});

test('preserves authorization digest across lifecycle changes and invalidates recipes paths or grants', () => {
  const task = approvedTask({
    state: 'candidate_ready', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'a'.repeat(64)}`, outcome: 'unverified',
    evidence_refs: ['artifact://task-17/evidence.json'],
  });
  const digest = authorizationDigest(task);
  assert.equal(digest, authorizationDigest({ ...task, state: 'reviewing', repair_cycles: 1, outcome: 'unverified', evidence_refs: ['artifact://new'] }));
  assert.notEqual(digest, authorizationDigest({ ...task, allowed_paths: ['src/Other.tsx'] }));
  assert.notEqual(digest, authorizationDigest({ ...task, approved_check_recipes: [{ ...task.approved_check_recipes[0], argv: ['evil'] }] }));
  assert.notEqual(digest, authorizationDigest({ ...task, stitch_grant: { project_id: 'different' } }));
  assert.notEqual(digest, authorizationDigest({ ...task, qualification_hash: `sha256:${'b'.repeat(64)}` }));
});

test('requires the approved qualification hash to equal the trusted active runtime hash', async () => {
  const definition = approvedTask();
  const { repo, path } = await taskFile(definition);
  await withApproval(definition, async () => {
    delete process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
    await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }), /qualification|runtime/i);
    process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = `sha256:${'0'.repeat(64)}`;
    await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }), /qualification|runtime/i);
    process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = definition.qualification_hash;
    await loadTask({ repo, taskFile: path, operation: 'patch' });
  });
});

test('permits candidate lifecycle checks while reserving patches for approved or renewed repairing tasks', async () => {
  for (const state of ['candidate_ready', 'reviewing', 'repairing']) {
    const definition = approvedTask({
      state, candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`,
      outcome: 'unverified',
      ...(state === 'repairing' ? { repair_cycles: 1, repair_authorization: { cycle: 1, nonce: 'renewed-repair' } } : {}),
    });
    const { repo, path } = await taskFile(definition);
    await withApproval(definition, async () => {
      await loadTask({ repo, taskFile: path, operation: 'check' });
      if (state === 'repairing') await loadTask({ repo, taskFile: path, operation: 'patch' });
      else await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }));
    });
  }
  const accepted = approvedTask({
    state: 'accepted', model_route: '@ui_review', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'a'.repeat(64)}`, outcome: 'verified', evidence_refs: ['artifact://task-17/evidence'],
  });
  const { repo: acceptedRepo, path: acceptedPath } = await taskFile(accepted);
  await withApproval(accepted, () => loadTask({ repo: acceptedRepo, taskFile: acceptedPath }));
  const approved = approvedTask();
  const { repo, path } = await taskFile(approved);
  await withApproval(approved, () => loadTask({ repo, taskFile: path, operation: 'patch' }));
});

test('binds patch and check to builders while reserving reviewer capture for review lifecycle', async () => {
  const candidate = approvedTask({
    state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`, outcome: 'unverified',
  });
  const reviewer = { ...candidate, state: 'reviewing', model_route: '@ui_review' };
  const acceptedReviewer = { ...reviewer, state: 'accepted', outcome: 'verified', evidence_refs: ['artifact://task-17/evidence'] };
  for (const [definition, operation, allowed] of [
    [approvedTask(), 'patch', true],
    [{ ...approvedTask(), model_route: '@ui_review' }, 'patch', false],
    [candidate, 'check', true],
    [{ ...candidate, model_route: '@ui_review' }, 'check', false],
    [reviewer, 'capture', true],
    [acceptedReviewer, 'capture', true],
    [{ ...reviewer, model_route: '@ui_code' }, 'capture', false],
    [candidate, 'capture', false],
  ]) {
    const { repo, path } = await taskFile(definition);
    await withApproval(definition, async () => {
      if (allowed) await loadTask({ repo, taskFile: path, operation });
      else await assert.rejects(() => loadTask({ repo, taskFile: path, operation }));
    });
  }
});

test('requires renewed reviewer authorization after coordinator transitions a candidate to review', async () => {
  const builder = approvedTask({
    state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`, outcome: 'unverified',
  });
  const reviewer = { ...builder, state: 'reviewing', model_route: '@ui_review' };
  const { repo, path } = await taskFile(builder);
  const previous = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = authorizationDigest(builder);
  try {
    await writeFile(path, JSON.stringify(reviewer));
    await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'capture' }), /approval/i);
  } finally {
    if (previous === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = previous;
  }

  await withApproval(reviewer, () => loadTask({ repo, taskFile: path, operation: 'capture' }));
});

test('requires a fresh cycle-bound nonce before a repairing task can apply a patch', async () => {
  const repair = approvedTask({
    state: 'repairing', repair_cycles: 1,
    repair_authorization: { cycle: 1, nonce: 'repair-cycle-1' },
    candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`,
  });
  const prior = { ...repair, repair_authorization: { cycle: 1, nonce: 'old-approval' } };
  const { repo, path } = await taskFile(repair);
  const before = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = authorizationDigest(prior);
  try {
    await assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }), /approval/i);
  } finally {
    if (before === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = before;
  }
  await withApproval(repair, () => loadTask({ repo, taskFile: path, operation: 'patch' }));
  const malformed = { ...repair, repair_authorization: { cycle: 2, nonce: 'wrong-cycle' } };
  await writeFile(path, JSON.stringify(malformed));
  await withApproval(malformed, () => assert.rejects(() => loadTask({ repo, taskFile: path, operation: 'patch' }), /repairing|cycle/i));
});

test('rejects malformed grant expiry even for status-facing task loads', async () => {
  const definition = approvedTask({ stitch_grant: { project_id: 'project-17', expires_at: 'not-a-date', mutations: [], readback_tools: [] } });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /expiry|date|grant/i);
});

test('rejects unsafe task IDs, repository-root candidate scope, and noncanonical paths before any operation', async () => {
  for (const override of [
    { task_id: '../task-17' },
    { task_id: 'task 17' },
    { allowed_paths: ['.'] },
    { allowed_paths: ['src/Card View.tsx'] },
    { forbidden_policy_paths: ['policy/baseline file.json'] },
    { forbidden_policy_paths: ['./policy/baseline.json'] },
    { allowed_paths: ['src//Card.tsx'] },
  ]) {
    const { repo, path } = await taskFile(override);
    await assert.rejects(() => loadTask({ repo, taskFile: path }), /task_id|path|scope|invalid/i);
  }
});

test('requires every check recipe to declare a protected, exact SHA-256 trusted verifier', async () => {
  const definition = approvedTask();
  const { trusted_verifier, ...withoutVerifier } = definition.approved_check_recipes[0];
  const { repo, path } = await taskFile({ ...definition, approved_check_recipes: [withoutVerifier] });
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /trusted verifier/i);
  void trusted_verifier;
});

test('binds the candidate identity to all non-host-owned worktree inputs', async () => {
  const definition = approvedTask();
  const { repo } = await taskFile(definition);
  const before = await candidateHash({ repo, task: definition });
  await writeFile(join(repo, '.ui-results/unit.json'), '{"schema":"ui-delivery-check-v1"}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'fresh capture');
  assert.equal(await candidateHash({ repo, task: definition }), before);
  await writeFile(join(repo, 'package-lock.json'), '{"dependency":"changed"}\n');
  assert.notEqual(await candidateHash({ repo, task: definition }), before);
});

test('rejects a symlink anywhere in the candidate worktree', async () => {
  const { repo } = await taskFile({});
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-candidate-outside-'));
  await symlink(outside, join(repo, 'src/escaped'));
  await assert.rejects(() => candidateHash({ repo, task: approvedTask() }));
});

test('rejects a FIFO anywhere in the candidate worktree without opening it for reads', async () => {
  const { repo } = await taskFile({});
  const fifo = join(repo, 'src/untrusted.fifo');
  await execFile('mkfifo', [fifo]);
  await assert.rejects(() => candidateHash({ repo, task: approvedTask() }), /unsupported/i);
});

test('accepts a schema-valid building task and rejects policy-directory escapes', async () => {
  const definition = approvedTask({ state: 'building' });
  const { repo, path } = await taskFile(definition);
  const task = await loadTask({ repo, taskFile: path });
  assert.equal(task.state, 'building');
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-task-outside-'));
  const escaped = join(repo, '.omp/ui-delivery/tasks/escaped.json');
  await writeFile(join(outside, 'task.json'), JSON.stringify(definition));
  await symlink(join(outside, 'task.json'), escaped);
  await assert.rejects(() => loadTask({ repo, taskFile: escaped }));
});

test('rejects malformed recipes and empty capture evidence before an operation starts', async () => {
  for (const override of [
    { approved_check_recipes: [{ ...approvedTask().approved_check_recipes[0], result_path: undefined }] },
    { approved_check_recipes: [{ ...approvedTask().approved_check_recipes[0], write_paths: [] }] },
    { approved_check_recipes: [{ ...approvedTask().approved_check_recipes[0], write_paths: ['.ui-results/unit.json'] }] },
    { capture_recipes: [{ id: 'capture', check_id: 'unit', artifacts: [] }] },
  ]) {
    const { repo, path } = await taskFile(override);
    await assert.rejects(() => loadTask({ repo, taskFile: path }));
  }
});

test('rejects whitespace-bearing capture artifact paths using the runtime path contract', async () => {
  const definition = approvedTask({
    capture_recipes: [{ id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page capture.png', type: 'screenshot' }] }],
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /capture artifact|path/i);
});

test('rejects repository-root candidate scope before candidate hashing', async () => {
  const definition = approvedTask({ allowed_paths: ['.'] });
  const { repo } = await taskFile(definition);
  await assert.rejects(() => candidateHash({ repo, task: definition }), /scope|path|invalid/i);
});

test('streams large candidate files into a deterministic permission-framed hash', async () => {
  const definition = approvedTask();
  const { repo } = await taskFile(definition);
  const source = Buffer.alloc(16 * 1024 * 1024, 0x5a);
  await writeFile(join(repo, 'src/large.bin'), source);
  await chmod(join(repo, 'src/large.bin'), 0o640);
  const expected = createHash('sha256')
    .update(`src/Card.tsx\0${Buffer.byteLength('export const Card = 1;\n')}\0${0o644}\0`)
    .update('export const Card = 1;\n')
    .update(`src/large.bin\0${source.length}\0${0o640}\0`)
    .update(source)
    .digest('hex');
  assert.equal(await candidateHash({ repo, task: definition }), `sha256:${expected}`);
  await chmod(join(repo, 'src/large.bin'), 0o600);
  assert.notEqual(await candidateHash({ repo, task: definition }), `sha256:${expected}`);
});

test('requires the reviewer route for accepted tasks', async () => {
  const definition = approvedTask({
    state: 'accepted', candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`,
    evidence_refs: ['artifact://task-17/evidence'], outcome: 'verified',
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /route|review/i);
});

test('rejects duplicate artifact paths within and across capture recipes', async () => {
  for (const capture_recipes of [
    [{ id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }, { path: 'evidence/page.png', type: 'image/png' }] }],
    [
      { id: 'capture-a', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }] },
      { id: 'capture-b', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'image/png' }] },
    ],
  ]) {
    const { repo, path } = await taskFile({ capture_recipes });
    await assert.rejects(() => loadTask({ repo, taskFile: path }), /duplicate|capture artifact/i);
  }
});

test('rejects grants with tools outside the exact supported Stitch inventory', async () => {
  const definition = approvedTask({
    stitch_grant: {
      project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'stitch.edit_screen', input_hash: 'sha256:input', max_uses: 1, expected_readback: { tool_name: 'stitch.get_screen', response_hash: `sha256:${'a'.repeat(64)}` } }],
      readback_tools: ['stitch.get_screen'],
    },
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /Stitch.*tool|grant/i);
});

test('rejects grants whose readback is ungranted, projectless, or noncanonical', async () => {
  const baseGrant = {
    project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
    mutations: [{
      tool_name: 'mcp__stitch_edit_screens', input_hash: `sha256:${'c'.repeat(64)}`, max_uses: 1,
      expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: `sha256:${'a'.repeat(64)}` },
    }],
    readback_tools: ['mcp__stitch_get_screen'],
  };
  for (const stitch_grant of [
    { ...baseGrant, mutations: [{ ...baseGrant.mutations[0], expected_readback: { tool_name: 'mcp__stitch_get_project', response_hash: `sha256:${'a'.repeat(64)}` } }] },
    { ...baseGrant, readback_tools: ['mcp__stitch_list_projects'] },
    { ...baseGrant, mutations: [{ ...baseGrant.mutations[0], input_hash: `sha256:${'C'.repeat(64)}` }] },
  ]) {
    const { repo, path } = await taskFile({ stitch_grant });
    await assert.rejects(() => loadTask({ repo, taskFile: path }), /Stitch.*grant|readback/i);
  }
});

test('does not settle patch journal creation before syncing the file and parent directory', async () => {
  const { repo } = await taskFile({});
  await mkdir(join(repo, '.omp/ui-delivery/evidence'), { recursive: true });
  const calls = [];
  const persistence = {
    async open(path) {
      const label = path.endsWith('.json') ? 'journal' : 'directory';
      calls.push(`open:${label}`);
      return {
        async writeFile() { calls.push('write:journal'); },
        async sync() { calls.push(`sync:${label}`); },
        async close() { calls.push(`close:${label}`); },
      };
    },
  };
  await beginPatchJournal({
    repo, taskId: 'task-17', taskFile: '.omp/ui-delivery/tasks/task-17.json', patchHash: 'sha256:pending',
    persistence,
  });
  assert.deepEqual(calls, [
    'open:journal', 'write:journal', 'sync:journal', 'close:journal',
    'open:directory', 'sync:directory', 'close:directory',
  ]);
});
test('admits only one task ID to the repository patch transaction', async () => {
  const { repo } = await taskFile({});
  await mkdir(join(repo, '.omp/ui-delivery/evidence'), { recursive: true });
  const attempts = await Promise.allSettled([
    beginPatchJournal({ repo, taskId: 'task-17', taskFile: '.omp/ui-delivery/tasks/task-17.json', patchHash: 'sha256:first' }),
    beginPatchJournal({ repo, taskId: 'task-18', taskFile: '.omp/ui-delivery/tasks/task-18.json', patchHash: 'sha256:second' }),
  ]);
  assert.equal(attempts.filter((attempt) => attempt.status === 'fulfilled').length, 1);
  assert.equal(attempts.filter((attempt) => attempt.status === 'rejected').length, 1);
  await releasePatchJournal(repo);
});
