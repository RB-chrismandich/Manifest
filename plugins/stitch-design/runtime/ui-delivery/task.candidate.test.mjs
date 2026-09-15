import assert from 'node:assert/strict';
import { execFile as executeFile } from 'node:child_process';
import { chmod, mkdtemp, mkdir, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import { candidateHash } from './task.ts';

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

async function candidateWorkspace() {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-candidate-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await mkdir(join(repo, '.ui-results'), { recursive: true });
  await mkdir(join(repo, 'evidence'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'prior capture');
  return repo;
}

const execFile = promisify(executeFile);

test('binds the candidate identity to all non-host-owned worktree inputs', async () => {
  const definition = approvedTask();
  const repo = await candidateWorkspace();
  const before = await candidateHash({ repo, task: definition });
  await writeFile(join(repo, '.ui-results/unit.json'), '{"schema":"ui-delivery-check-v1"}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'fresh capture');
  assert.equal(await candidateHash({ repo, task: definition }), before);
  await writeFile(join(repo, 'package-lock.json'), '{"dependency":"changed"}\n');
  assert.notEqual(await candidateHash({ repo, task: definition }), before);
});

test('rejects a symlink anywhere in the candidate worktree', async () => {
  const repo = await candidateWorkspace();
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-candidate-outside-'));
  await symlink(outside, join(repo, 'src/escaped'));
  await assert.rejects(() => candidateHash({ repo, task: approvedTask() }));
});

test('rejects a FIFO anywhere in the candidate worktree without opening it for reads', async () => {
  const repo = await candidateWorkspace();
  const fifo = join(repo, 'src/untrusted.fifo');
  await execFile('mkfifo', [fifo]);
  await assert.rejects(() => candidateHash({ repo, task: approvedTask() }), /unsupported/i);
});

test('rejects repository-root candidate scope before candidate hashing', async () => {
  const definition = approvedTask({ allowed_paths: ['.'] });
  const repo = await candidateWorkspace();
  await assert.rejects(() => candidateHash({ repo, task: definition }), /scope|path|invalid/i);
});

test('hashes large candidate files deterministically with permission framing', async () => {
  const definition = approvedTask();
  const repo = await candidateWorkspace();
  const source = Buffer.alloc(16 * 1024 * 1024, 0x5a);
  const file = join(repo, 'src/large.bin');
  await writeFile(file, source);
  await chmod(file, 0o640);
  const expected = await candidateHash({ repo, task: definition });
  assert.equal(await candidateHash({ repo, task: definition }), expected);
  await chmod(file, 0o600);
  assert.notEqual(await candidateHash({ repo, task: definition }), expected);
});

test('binds special permission bits such as setgid to the framed candidate identity', async () => {
  const definition = approvedTask();
  const repo = await candidateWorkspace();
  await chmod(join(repo, 'src'), 0o750);
  const before = await candidateHash({ repo, task: definition });
  await chmod(join(repo, 'src'), 0o2750);
  assert.notEqual(await candidateHash({ repo, task: definition }), before);
});

test('binds non-delivery .omp content to candidate identity while excluding protected ui-delivery state', async () => {
  const definition = approvedTask();
  const repo = await candidateWorkspace();
  await mkdir(join(repo, '.omp/ui-delivery/tasks'), { recursive: true });
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task-17.json'), JSON.stringify(definition));
  const before = await candidateHash({ repo, task: definition });
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task-17.json'), JSON.stringify({ ...definition, state: 'accepted' }));
  assert.equal(await candidateHash({ repo, task: definition }), before, 'protected ui-delivery state must stay excluded');
  await mkdir(join(repo, '.omp/agent'), { recursive: true });
  await writeFile(join(repo, '.omp/agent/config.json'), '{"changed":true}\n');
  assert.notEqual(await candidateHash({ repo, task: definition }), before, 'non-delivery .omp content must bind to candidate identity');
});
