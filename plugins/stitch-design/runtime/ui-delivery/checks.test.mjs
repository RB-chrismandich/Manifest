import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readdir, realpath, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { runCheck } from './checks.ts';

const recipe = {
  id: 'unit', argv: ['node', '--test', 'test.mjs'], cwd: '.', timeout_ms: 500,
  backend: 'sandbox-exec', sandbox_image: 'registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
  result_path: '.ui-results/unit.json', write_paths: ['.ui-results/unit.json'],
};

function task(overrides = {}) {
  return { allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'], approved_check_recipes: [recipe], ...overrides };
}

function executor(calls, stdout = 'x'.repeat(64)) {
  return async (command) => {
    calls.push(command);
    return { exitCode: 0, stdout, stderr: 'stderr' };
  };
}

async function fixture() {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-check-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await mkdir(join(repo, '.ui-results'), { recursive: true });
  await mkdir(join(repo, 'policy'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  return repo;
}

test('runs a file-allowlisted check from the read-only repository cwd with fixed argv', async () => {
  const repo = await fixture();
  const calls = [];
  const result = await runCheck({
    repo, task: task(), checkId: 'unit', environment: { HOME: '/ambient', TOKEN: 'secret', CI: '1' },
    executor: executor(calls),
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, 'sandbox-exec');
  assert.deepEqual(calls[0].recipeArgv, recipe.argv);
  assert.ok(calls[0].argv.includes('--test'));
  assert.ok(!calls[0].argv.includes('sh'));
  const canonicalRepo = await realpath(repo);
  assert.equal(calls[0].cwd, canonicalRepo);
  assert.equal(calls[0].env.TOKEN, undefined);
  assert.equal(calls[0].env.HOME, undefined);
  assert.ok(calls[0].mounts.some((mount) => mount.source === join(canonicalRepo, '.ui-results/unit.json') && !mount.readOnly));
  assert.ok(!calls[0].mounts.some((mount) => mount.source === join(canonicalRepo, 'src/Card.tsx') && !mount.readOnly));
  assert.deepEqual(result.argv, recipe.argv);
});

test('parameterizes SBPL paths and permits required runtime and system reads without network access', async () => {
  const repo = await fixture();
  const crafted = 'src/evil") (allow network*) (';
  await mkdir(join(repo, crafted), { recursive: true });
  const calls = [];
  await runCheck({
    repo, task: task({ allowed_paths: [crafted] }), checkId: 'unit', executor: executor(calls),
  });
  const [command] = calls;
  assert.ok(command.argv.includes('-D'));
  assert.ok(command.argv.some((argument) => argument.includes('network*') && argument.includes('deny')));
  assert.ok(command.argv.some((argument) => argument.includes('/usr') || argument.includes('/System')));
  assert.ok(!command.argv.some((argument) => argument.includes(crafted)));
});

test('rejects raw command input, unknown recipes, symlinked writes, and writable protected roots', async () => {
  const repo = await fixture();
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-outside-'));
  await symlink(outside, join(repo, 'src/linked'));
  for (const writePaths of [
    ['.git'],
    ['.'],
    ['policy'],
    ['src/linked'],
    [],
  ]) {
    await assert.rejects(() => runCheck({
      repo,
      task: task({ approved_check_recipes: [{ ...recipe, write_paths: writePaths }] }),
      checkId: 'unit',
      executor: executor([]),
    }));
  }
  await assert.rejects(() => runCheck({ repo, task: task(), checkId: 'unit', command: 'node --test; touch owned', executor: executor([]) }));
});

test('constructs Docker with fixed non-secret environment forwarded to the workload', async () => {
  const repo = await fixture();
  const calls = [];
  await runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, backend: 'docker' }] }),
    checkId: 'unit', environment: { AWS_SECRET_ACCESS_KEY: 'secret', CI: 'attacker-selected' },
    backends: { 'sandbox-exec': true, docker: true }, executor: executor(calls),
  });
  const [command] = calls;
  assert.equal(command.executable, 'docker');
  assert.ok(command.argv.includes('--network'));
  assert.ok(command.argv.includes('none'));
  assert.ok(command.argv.includes('--read-only'));
  assert.ok(command.argv.includes('--env'));
  assert.ok(!command.argv.includes('AWS_SECRET_ACCESS_KEY=secret'));
  assert.ok(!command.argv.includes('CI=attacker-selected'));
});

test('passes fixed Docker workload argv through without resolving its container executable on the host', async () => {
  const repo = await fixture();
  const calls = [];
  const containerArgv = ['ui-check-in-container', '--verify'];
  await runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, argv: containerArgv, backend: 'docker' }] }),
    checkId: 'unit', backends: { 'sandbox-exec': true, docker: true }, executor: executor(calls),
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, 'docker');
  assert.deepEqual(calls[0].recipeArgv, containerArgv);
  assert.deepEqual(calls[0].argv.slice(-containerArgv.length), containerArgv);
});

test('terminates the workload and removes scratch on timeout or abort before returning', async () => {
  const repo = await fixture();
  const scratchRoot = await mkdtemp(join(tmpdir(), 'ui-delivery-scratch-root-'));
  const controller = new AbortController();
  const calls = [];
  controller.abort();
  await assert.rejects(() => runCheck({
    repo, task: task(), checkId: 'unit', signal: controller.signal, scratchRoot, executor: executor(calls),
  }));
  assert.equal(calls.length, 0);
  await assert.rejects(() => runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, timeout_ms: 1 }] }), checkId: 'unit', scratchRoot,
    executor: async (command) => {
      calls.push(command);
      await new Promise((resolve) => setTimeout(resolve, 10));
      return { exitCode: 0, stdout: '', stderr: '' };
    },
  }));
  assert.deepEqual(await readdir(scratchRoot), []);
});
