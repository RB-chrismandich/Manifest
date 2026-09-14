import assert from 'node:assert/strict';
import { mkdir, mkdtemp, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { runCheck } from './checks.ts';

const recipe = {
  id: 'unit', argv: ['node', '--test', 'test.mjs'], cwd: 'src', timeout_ms: 500,
  backend: 'sandbox-exec', sandbox_image: 'registry.example/ui-check@sha256:0123456789abcdef', env: ['CI'],
};

function task(overrides = {}) {
  return { allowed_paths: ['src'], approved_check_recipes: [recipe], ...overrides };
}

function executor(calls, stdout = 'x'.repeat(64)) {
  return async (command) => {
    calls.push(command);
    return { exitCode: 0, stdout, stderr: 'stderr' };
  };
}

test('runs only a named recipe through sandbox-exec with scrubbed environment and fixed argv', async () => {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  await mkdir(join(repo, 'src'));
  const calls = [];
  const result = await runCheck({
    repo, task: task(), checkId: 'unit', environment: { CI: '1', HOME: '/ambient', TOKEN: 'secret' },
    executor: executor(calls),
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, 'sandbox-exec');
  assert.deepEqual(calls[0].recipeArgv, recipe.argv);
  assert.ok(calls[0].argv.includes('--test'));
  assert.ok(!calls[0].argv.includes('sh'));
  assert.equal(calls[0].cwd, join(await realpath(repo), 'src'));
  assert.deepEqual(calls[0].env, { CI: '1' });
  assert.equal(calls[0].timeoutMs, 500);
  assert.deepEqual(result.argv, recipe.argv);
});

test('rejects raw command input and unknown recipe identifiers', async () => {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  await mkdir(join(repo, 'src'));
  await assert.rejects(() => runCheck({ repo, task: task(), checkId: 'missing', executor: executor([]) }));
  await assert.rejects(() => runCheck({ repo, task: task(), checkId: 'unit', command: 'node --test; touch owned', executor: executor([]) }));
});

test('rejects a recipe cwd that escapes the repository', async () => {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  await mkdir(join(repo, 'src'));
  await assert.rejects(() => runCheck({ repo, task: task({ approved_check_recipes: [{ ...recipe, cwd: '../outside' }] }), checkId: 'unit', executor: executor([]) }));
});

test('fails closed when the selected sandbox backend is unavailable', async () => {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  await mkdir(join(repo, 'src'));
  await assert.rejects(() => runCheck({ repo, task: task(), checkId: 'unit', backends: { 'sandbox-exec': false, docker: true }, executor: executor([]) }));
});

test('constructs an isolated digest-pinned Docker invocation and bounds captured output', async () => {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  await mkdir(join(repo, 'src'));
  const calls = [];
  const result = await runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, backend: 'docker' }] }),
    checkId: 'unit', outputLimitBytes: 32, backends: { 'sandbox-exec': true, docker: true }, executor: executor(calls),
  });
  const [command] = calls;
  assert.equal(command.executable, 'docker');
  assert.ok(command.argv.includes('--network'));
  assert.ok(command.argv.includes('none'));
  assert.ok(command.argv.includes('--read-only'));
  const canonicalRepo = await realpath(repo);
  assert.ok(command.argv.includes('--mount'));
  assert.ok(command.argv.includes(recipe.sandbox_image));
  assert.deepEqual(command.recipeArgv, recipe.argv);
  assert.ok(command.mounts.some((mount) => mount.source === canonicalRepo && mount.readOnly));
  assert.ok(command.mounts.some((mount) => mount.source === join(canonicalRepo, 'src') && !mount.readOnly));
  assert.equal(result.stdout.truncated, true);
  assert.equal(result.stdout.bytes, 32);
  assert.equal(result.stderr.truncated, false);
});
