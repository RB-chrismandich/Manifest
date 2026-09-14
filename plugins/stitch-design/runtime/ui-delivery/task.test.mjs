import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { candidateHash, loadTask } from './task.ts';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function authorizationDigest(task) {
  const projection = Object.fromEntries([
    'task_id', 'design_revision', 'allowed_paths', 'forbidden_policy_paths',
    'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant',
  ].filter((key) => key in task).map((key) => [key, task[key]]));
  return `sha256:${createHash('sha256').update(JSON.stringify(canonical(projection))).digest('hex')}`;
}

function approvedTask(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [{
      id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
      backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
      write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
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
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = authorizationDigest(task);
  try { return await operation(); } finally {
    if (before === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = before;
  }
}

test('requires an external authorization digest for every mutation and executable task load', async () => {
  const definition = approvedTask();
  const { repo, path } = await taskFile(definition);
  delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: true }));
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = 'sha256:0'.padEnd(71, '0');
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: true }));
  await withApproval(definition, () => loadTask({ repo, taskFile: path, mutation: true }));
});

test('rejects a repository task that self-asserts approved without the parent authorization digest', async () => {
  const definition = approvedTask({ state: 'approved' });
  const { repo, path } = await taskFile(definition);
  delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: true }), /approval/i);
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
});

test('permits candidate lifecycle states for checks while reserving mutation authorization for approved', async () => {
  for (const state of ['candidate_ready', 'reviewing', 'repairing', 'accepted']) {
    const definition = approvedTask({
      state, candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`,
      outcome: state === 'accepted' ? 'verified' : 'unverified',
      ...(state === 'accepted' ? { evidence_refs: ['artifact://task-17/evidence'] } : {}),
    });
    const { repo, path } = await taskFile(definition);
    await loadTask({ repo, taskFile: path });
    await withApproval(definition, () => assert.rejects(() => loadTask({ repo, taskFile: path, mutation: true })));
  }
  const approved = approvedTask();
  const { repo, path } = await taskFile(approved);
  await withApproval(approved, () => loadTask({ repo, taskFile: path, mutation: true }));
});

test('hashes only sorted allowed regular-file bytes, excluding declared result and capture outputs', async () => {
  const definition = approvedTask();
  const { repo } = await taskFile(definition);
  await mkdir(join(repo, '.ui-results'), { recursive: true });
  await mkdir(join(repo, 'evidence'), { recursive: true });
  const before = await candidateHash({ repo, task: definition });
  await writeFile(join(repo, '.ui-results/unit.json'), '{"schema":"ui-delivery-check-v1"}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'fresh capture');
  assert.equal(await candidateHash({ repo, task: definition }), before);
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 2;\n');
  assert.notEqual(await candidateHash({ repo, task: definition }), before);
});

test('hashes path-delimited candidate entries and rejects an intermediate symlink escape', async () => {
  const { repo } = await taskFile({});
  await Promise.all([
    writeFile(join(repo, 'ab'), 'a'),
    writeFile(join(repo, 'a'), 'ab'),
    writeFile(join(repo, 'renamed'), 'same'),
    writeFile(join(repo, 'original'), 'same'),
  ]);
  await writeFile(join(repo, 'c'), 'bc');
  await writeFile(join(repo, 'bc'), 'c');
  const split = await candidateHash({ repo, task: approvedTask({ allowed_paths: ['ab', 'c'] }) });
  const joined = await candidateHash({ repo, task: approvedTask({ allowed_paths: ['a', 'bc'] }) });
  assert.notEqual(split, joined);
  assert.notEqual(
    await candidateHash({ repo, task: approvedTask({ allowed_paths: ['original'] }) }),
    await candidateHash({ repo, task: approvedTask({ allowed_paths: ['renamed'] }) }),
  );
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-candidate-outside-'));
  await symlink(outside, join(repo, 'src/escaped'));
  await assert.rejects(() => candidateHash({ repo, task: approvedTask({ allowed_paths: ['src/escaped'] }) }));
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
