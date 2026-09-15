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
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-task-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  const path = join(repo, '.omp/ui-delivery/tasks/task-17.json');
  await mkdir(join(path, '..'), { recursive: true });
  await writeFile(path, JSON.stringify(approvedTask(task)));
  return { repo, path };
}

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

test('requires Docker recipes and rejects option-shaped digest-pinned images', async () => {
  for (const recipe of [
    { ...approvedTask().approved_check_recipes[0], backend: 'sandbox-exec' },
    { ...approvedTask().approved_check_recipes[0], backend: 'docker', sandbox_image: `-image@sha256:${'a'.repeat(64)}` },
  ]) {
    const { repo, path } = await taskFile({ approved_check_recipes: [recipe] });
    await assert.rejects(() => loadTask({ repo, taskFile: path }), /check recipe|docker/i);
  }
});
