import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { loadTask } from './task.ts';

function approvedTask(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    qualification_hash: `sha256:${'a'.repeat(64)}`, allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [{
      id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
      backend: 'docker', sandbox_image: `registry.example/ui-check@sha256:${'c'.repeat(64)}`, result_path: '.ui-results/unit.json',
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

async function taskFile(task) {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-repair-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  const path = join(repo, '.omp/ui-delivery/tasks/task-17.json');
  await mkdir(join(path, '..'), { recursive: true });
  await writeFile(path, JSON.stringify(task));
  return { repo, path };
}

test('rejects repair authorization present outside the repairing state', async () => {
  const definition = approvedTask({
    state: 'approved',
    repair_authorization: { cycle: 1, nonce: 'preapproved' },
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /repair.*authoriz|repairing/i);
});

test('rejects repair authorization surviving into a terminal accepted state', async () => {
  const definition = approvedTask({
    state: 'accepted', outcome: 'verified', model_route: '@ui_review',
    candidate_revision: 'git:abc', candidate_hash: `sha256:${'a'.repeat(64)}`,
    evidence_refs: ['evidence/page.png'],
    repair_authorization: { cycle: 1, nonce: 'stale' },
  });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /repair.*authoriz|repairing/i);
});
