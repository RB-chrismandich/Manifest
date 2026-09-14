import assert from 'node:assert/strict';
import { mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { loadTask } from './task.ts';

async function approvedTask(repo, overrides = {}) {
  return {
    task_id: 'task-17',
    state: 'approved',
    design_revision: 'stitch-r17',
    allowed_paths: ['src/Card.tsx'],
    forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [{
      id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
      backend: 'sandbox-exec',
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
  const path = join(repo, relative);
  await mkdir(join(path, '..'), { recursive: true });
  await writeFile(path, JSON.stringify(await approvedTask(repo, task)));
  return { repo, path };
}

test('loads a schema-valid approved task from the repository task directory', async () => {
  const { repo, path } = await taskFile({});
  const task = await loadTask({ repo, taskFile: path, mutation: true, now: new Date('2026-09-14T00:00:00Z') });
  assert.equal(task.task_id, 'task-17');
});

test('rejects a task outside the repository policy task directory', async () => {
  const { repo, path } = await taskFile({}, 'tasks/task-17.json');
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: false }));
});

test('rejects a policy task filename whose symlink resolves outside the repository', async () => {
  const { repo } = await taskFile({});
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-task-outside-'));
  const outsideTask = join(outside, 'task.json');
  await writeFile(outsideTask, JSON.stringify(await approvedTask(repo)));
  const path = join(repo, '.omp/ui-delivery/tasks/escaped.json');
  await symlink(outsideTask, path);
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: false }));
});

test('rejects a schema-invalid task before executing a policy operation', async () => {
  const { repo, path } = await taskFile({ allowed_paths: [] });
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: false }));
});

test('rejects mutations when the task is not approved', async () => {
  const { repo, path } = await taskFile({ state: 'draft' });
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: true }));
});

test('rejects an approved task whose Stitch mutation grant is expired', async () => {
  const { repo, path } = await taskFile({
    stitch_grant: {
      project_id: 'project-17',
      expires_at: '2020-01-01T00:00:00Z',
      mutations: [{ tool_name: 'stitch.edit_screen', input_hash: 'sha256:input', max_uses: 1 }],
      readback_tools: ['stitch.get_screen'],
    },
  });
  await assert.rejects(() => loadTask({ repo, taskFile: path, mutation: true, now: new Date('2026-09-14T00:00:00Z') }));
});
