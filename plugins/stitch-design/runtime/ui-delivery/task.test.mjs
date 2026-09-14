import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { chmod, mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { beginPatchJournal, candidateHash, loadTask, releasePatchJournal, replaceTaskFile } from './task.ts';

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


test('binds candidate identity to traversed directory modes', async () => {
  const definition = approvedTask();
  const { repo } = await taskFile(definition);
  const before = await candidateHash({ repo, task: definition });
  await chmod(join(repo, 'src'), 0o700);
  const after = await candidateHash({ repo, task: definition });
  assert.notEqual(after, before);
});

test('rejects uppercase candidate hashes', async () => {
  const definition = approvedTask({
    state: 'candidate_ready',
    candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'A'.repeat(64)}`,
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /candidate binding/i);
});


test('rejects Docker checks that do not start an approved image runtime', async () => {
  const definition = approvedTask({
    approved_check_recipes: [{
      ...approvedTask().approved_check_recipes[0],
      backend: 'docker',
      sandbox_image: `registry.example/ui-check@sha256:${'a'.repeat(64)}`,
      argv: ['.omp/ui-delivery/verifiers/unit.mjs'],
    }],
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /approved image runtime/i);
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

test('does not settle patch journal removal before unlinking and syncing its parent directory', async () => {
  const { repo } = await taskFile({});
  const calls = [];
  const persistence = {
    async unlink() { calls.push('unlink:journal'); },
    async open() {
      calls.push('open:directory');
      return {
        async sync() { calls.push('sync:directory'); },
        async close() { calls.push('close:directory'); },
      };
    },
  };
  await releasePatchJournal(repo, persistence);
  assert.deepEqual(calls, ['unlink:journal', 'open:directory', 'sync:directory', 'close:directory']);
});

test('syncs replacement task data and directory before releasing the patch journal', async () => {
  const { repo, path } = await taskFile({});
  const calls = [];
  const persistence = {
    async open(file) {
      const label = file.endsWith('.tmp') ? 'temporary' : 'directory';
      calls.push(`open:${label}`);
      return {
        async writeFile() { calls.push('write:temporary'); },
        async sync() { calls.push(`sync:${label}`); },
        async close() { calls.push(`close:${label}`); },
      };
    },
    async rename() { calls.push('rename:task'); },
  };
  await replaceTaskFile({ repo, taskFile: path, task: { state: 'candidate_ready' }, persistence });
  assert.deepEqual(calls, [
    'open:temporary', 'write:temporary', 'sync:temporary', 'close:temporary',
    'rename:task', 'open:directory', 'sync:directory', 'close:directory',
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
