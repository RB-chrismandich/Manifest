import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { chmod, mkdir, mkdtemp, readFile, readdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import { runCheck } from './checks.ts';
import { loadTask } from './task.ts';
const execFileAsync = promisify(execFile);
const verifier = {
  path: '.omp/ui-delivery/verifiers/verify.mjs',
  sha256: 'sha256:f9974862b9b6c9cbb2ef52e20d18eec093825ec2b8fb7dde84abe593d480ed3f',
};
const recipe = {
  id: 'unit', argv: ['node', verifier.path], cwd: '.', timeout_ms: 500,
  backend: 'sandbox-exec', sandbox_image: 'registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
  result_path: '.ui-results/unit.json', write_paths: ['.ui-results/unit.json'], trusted_verifier: verifier,
};

function task(overrides = {}) {
  return { allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'], approved_check_recipes: [recipe], ...overrides };
}

function verifierOutput({ result = { schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }, artifacts = [] } = {}) {
  return `${JSON.stringify({ schema: 'ui-delivery-verifier-output-v1', result, artifacts })}\n`;
}
const mockBackends = { 'sandbox-exec': true, docker: true };
function executor(calls, stdout = verifierOutput()) {
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
  await mkdir(join(repo, '.omp/ui-delivery/verifiers'), { recursive: true });
  await writeFile(join(repo, verifier.path), 'trusted verifier\n');
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  return repo;
}

test('runs a file-allowlisted check from the read-only repository cwd with fixed argv', async () => {
  const repo = await fixture();
  const calls = [];
  const result = await runCheck({
    repo, task: task(), checkId: 'unit', environment: { HOME: '/ambient', TOKEN: 'secret', CI: '1' },
    executor: executor(calls), backends: mockBackends,
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, 'sandbox-exec');
  assert.deepEqual(calls[0].recipeArgv, recipe.argv);
  assert.ok(calls[0].argv.includes(verifier.path));
  assert.ok(!calls[0].argv.includes('sh'));
  const canonicalRepo = await realpath(repo);
  assert.equal(calls[0].cwd, canonicalRepo);
  assert.equal(calls[0].env.TOKEN, undefined);
  assert.notEqual(calls[0].env.HOME, '/ambient');
  assert.equal(calls[0].env.HOME, calls[0].env.TMPDIR);
  assert.ok(!calls[0].mounts.some((mount) => mount.source === join(canonicalRepo, '.ui-results/unit.json') && !mount.readOnly));
  assert.ok(!calls[0].mounts.some((mount) => mount.source === join(canonicalRepo, 'src/Card.tsx') && !mount.readOnly));
  assert.deepEqual(result.argv, recipe.argv);
});

test('resolves the approved node runtime from the extension process PATH', async () => {
  const repo = await fixture();
  const manager = await mkdtemp(join(tmpdir(), 'ui-delivery-nvm-'));
  const node = join(manager, 'node');
  await writeFile(node, '#!/bin/sh\n');
  await chmod(node, 0o755);
  const previousPath = process.env.PATH;
  process.env.PATH = manager;
  try {
    const calls = [];
    await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends });
    assert.ok(calls[0].argv.includes(`EXEC=${await realpath(node)}`));
  } finally {
    process.env.PATH = previousPath;
    await rm(manager, { recursive: true, force: true });
  }
});

test('skips a repository PATH shadow for the approved node runtime', async () => {
  const repo = await fixture();
  const shadow = join(repo, 'node');
  const manager = await mkdtemp(join(tmpdir(), 'ui-delivery-asdf-'));
  const node = join(manager, 'node');
  await Promise.all([
    writeFile(shadow, '#!/bin/sh\n'),
    writeFile(node, '#!/bin/sh\n'),
  ]);
  await Promise.all([chmod(shadow, 0o755), chmod(node, 0o755)]);
  const previousPath = process.env.PATH;
  process.env.PATH = `${repo}:${manager}`;
  try {
    const calls = [];
    await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends });
    assert.ok(calls[0].argv.includes(`EXEC=${await realpath(node)}`));
  } finally {
    process.env.PATH = previousPath;
    await rm(manager, { recursive: true, force: true });
  }
});

test('rejects unapproved sandbox executable basenames', async () => {
  const repo = await fixture();
  await assert.rejects(
    () => runCheck({
      repo, task: task({ approved_check_recipes: [{ ...recipe, argv: ['evil', verifier.path] }] }),
      checkId: 'unit', executor: executor([]), backends: mockBackends,
    }),
    /approved executable/,
  );
});

test('grants the sandbox read and write access to its scratch directory', async () => {
  const repo = await fixture();
  const calls = [];
  await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends });
  const profile = calls[0].argv[calls[0].argv.indexOf('-p') + 1];
  assert.equal(profile.match(/\(subpath \(param "SCRATCH"\)\)/g)?.length, 2);
  assert.match(profile, /\(allow file-write\* \(literal "\/dev\/null"\) \(subpath \(param "SCRATCH"\)\)\)/);
});

test('allows only the digest-checked verifier beneath protected .omp state', async () => {
  const repo = await fixture();
  const sibling = join(repo, '.omp/ui-delivery/sibling-state.txt');
  await writeFile(sibling, 'protected sibling\n');
  const calls = [];
  await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends });
  const command = calls[0];
  const profileIndex = command.argv.indexOf('-p');
  const executable = command.argv.find((argument) => argument.startsWith('EXEC='))?.slice('EXEC='.length);
  assert.ok(executable);
  const script = 'const { readFileSync } = require("node:fs"); const verifier = readFileSync(process.argv[1], "utf8"); try { readFileSync(process.argv[2], "utf8"); process.exitCode = 2; } catch (error) { if (!["EACCES", "EPERM"].includes(error.code)) throw error; } process.stdout.write(verifier);';
  const { stdout } = await execFileAsync('sandbox-exec', [
    ...command.argv.slice(0, profileIndex + 2),
    executable,
    '-e',
    script,
    join(repo, verifier.path),
    sibling,
  ]);
  assert.equal(stdout, 'trusted verifier\n');
});

test('parameterizes SBPL paths and permits required runtime and system reads without network access', async () => {
  const repo = await fixture();
  const crafted = 'src/evil") (allow network*) (';
  await mkdir(join(repo, crafted), { recursive: true });
  const calls = [];
  await runCheck({
    repo, task: task({ allowed_paths: [crafted] }), checkId: 'unit', executor: executor(calls), backends: mockBackends,
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
      backends: mockBackends,
    }));
  }
  await assert.rejects(() => runCheck({ repo, task: task(), checkId: 'unit', command: 'node --test; touch owned', executor: executor([]), backends: mockBackends }));
});

test('rejects a candidate executable even when its recipe claims a trusted verifier', async () => {
  const repo = await fixture();
  const calls = [];
  await assert.rejects(
    () => runCheck({
      repo,
      task: task({ approved_check_recipes: [{ ...recipe, argv: ['node', 'src/Card.tsx'] }] }),
      checkId: 'unit',
      executor: executor(calls),
      backends: mockBackends,
    }),
    /trusted verifier/,
  );
  assert.equal(calls.length, 0);
});

test('rejects a candidate entrypoint placed before the trusted verifier', async () => {
  const repo = await fixture();
  const calls = [];
  await assert.rejects(
    () => runCheck({
      repo,
      task: task({ approved_check_recipes: [{ ...recipe, argv: ['node', 'src/Card.tsx', verifier.path] }] }),
      checkId: 'unit',
      executor: executor(calls),
      backends: mockBackends,
    }),
    /trusted verifier/,
  );
  assert.equal(calls.length, 0);
});

test('rejects verifier bytes that differ from its approved digest', async () => {
  const repo = await fixture();
  await writeFile(join(repo, verifier.path), 'tampered verifier\n');
  const calls = [];
  await assert.rejects(
    () => runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends }),
    /trusted verifier digest/,
  );
  assert.equal(calls.length, 0);
});

test('rejects a verifier directory symlink that escapes the repository', async () => {
  const repo = await fixture();
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-verifier-outside-'));
  await writeFile(join(outside, 'verify.mjs'), 'trusted verifier\n');
  await rm(join(repo, '.omp/ui-delivery/verifiers'), { recursive: true, force: true });
  await symlink(outside, join(repo, '.omp/ui-delivery/verifiers'));
  await assert.rejects(
    () => runCheck({ repo, task: task(), checkId: 'unit', executor: executor([]), backends: mockBackends }),
    /trusted verifier/,
  );
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
  assert.ok(command.argv.includes('--rm'));
  assert.ok(!command.argv.includes('AWS_SECRET_ACCESS_KEY=secret'));
  assert.ok(!command.argv.includes('CI=attacker-selected'));
});

test('uses Docker lifecycle cleanup for ordinary nonzero check results', async () => {
  const repo = await fixture();
  const calls = [];
  const result = await runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, backend: 'docker' }] }),
    checkId: 'unit', backends: { 'sandbox-exec': true, docker: true },
    executor: async (command) => {
      calls.push(command);
      return { exitCode: 1, stdout: '', stderr: 'failed' };
    },
  });
  assert.equal(result.exitCode, 1);
  assert.ok(calls[0].argv.includes('--rm'));
});

test('passes fixed Docker workload argv through without resolving its container executable on the host', async () => {
  const repo = await fixture();
  const calls = [];
  const containerArgv = ['ui-check-in-container', `/repo/${verifier.path}`];
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
    repo, task: task(), checkId: 'unit', signal: controller.signal, scratchRoot, executor: executor(calls), backends: mockBackends,
  }));
  assert.equal(calls.length, 0);
  await assert.rejects(() => runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, timeout_ms: 1 }] }), checkId: 'unit', scratchRoot, backends: mockBackends,
    executor: async (command) => {
      calls.push(command);
      await new Promise((resolve) => setTimeout(resolve, 10));
      return { exitCode: 0, stdout: '', stderr: '' };
    },
  }));
  assert.deepEqual(await readdir(scratchRoot), []);
});

test('cleans injected-executor timeout and abort resources after it settles', async () => {
  const repo = await fixture();
  const listeners = new Set();
  const signal = {
    aborted: false,
    addEventListener(type, listener) { if (type === 'abort') listeners.add(listener); },
    removeEventListener(type, listener) { if (type === 'abort') listeners.delete(listener); },
  };
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const timers = [];
  globalThis.setTimeout = ((callback, delay) => {
    const timer = { callback, delay, cleared: false };
    timers.push(timer);
    return timer;
  });
  globalThis.clearTimeout = ((timer) => { timer.cleared = true; });
  try {
    await runCheck({
      repo, task: task(), checkId: 'unit', signal, executor: executor([]), backends: mockBackends,
    });
    await assert.rejects(() => runCheck({
      repo, task: task(), checkId: 'unit', signal, executor: async () => { throw new Error('injected failure'); }, backends: mockBackends,
    }), /injected failure/);
    assert.equal(listeners.size, 0);
    assert.equal(timers.length, 2);
    assert.ok(timers.every((timer) => timer.cleared));
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test('writes verifier-declared results only after the sandbox exits without mounting outputs', async () => {
  const repo = await fixture();
  const calls = [];
  await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends });
  assert.deepEqual(JSON.parse(await readFile(join(repo, '.ui-results/unit.json'), 'utf8')), {
    schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0,
  });
  assert.equal(calls[0].mounts.some((mount) => !mount.readOnly && mount.target.startsWith('/repo/.ui-results')), false);
});

test('rejects overlapping host-output attempts without cross-attributing verifier envelopes', async () => {
  const repo = await fixture();
  const shared = '.ui-results/shared.json';
  const firstOnly = '.ui-results/first.json';
  const secondOnly = '.ui-results/second.json';
  const firstRecipe = { ...recipe, id: 'first', result_path: shared, write_paths: [shared, firstOnly] };
  const secondRecipe = { ...recipe, id: 'second', result_path: shared, write_paths: [shared, secondOnly] };
  let entered;
  const firstEntered = new Promise((resolve) => { entered = resolve; });
  let release;
  const firstRelease = new Promise((resolve) => { release = resolve; });
  const first = runCheck({
    repo, task: task({ approved_check_recipes: [firstRecipe] }), checkId: 'first', backends: mockBackends,
    executor: async () => {
      entered();
      await firstRelease;
      return { exitCode: 0, stdout: verifierOutput({ result: { attempt: 'first' } }), stderr: '' };
    },
  });
  await firstEntered;
  try {
    await assert.rejects(
      () => runCheck({
        repo, task: task({ approved_check_recipes: [secondRecipe] }), checkId: 'second', backends: mockBackends,
        executor: async () => ({ exitCode: 0, stdout: verifierOutput({ result: { attempt: 'second' } }), stderr: '' }),
      }),
      /output|lock|concurrent/i,
    );
  } finally {
    release();
  }
  await first;
  await runCheck({
    repo, task: task({ approved_check_recipes: [secondRecipe] }), checkId: 'second', backends: mockBackends,
    executor: async () => ({ exitCode: 0, stdout: verifierOutput({ result: { attempt: 'second' } }), stderr: '' }),
  });
  assert.deepEqual(JSON.parse(await readFile(join(repo, shared), 'utf8')), { attempt: 'second' });
  assert.equal((await readdir(join(repo, '.ui-results'))).some((path) => path.endsWith('.ui-delivery.lock')), false);
});

test('does not remove an output lock it did not create', async () => {
  const repo = await fixture();
  let entered;
  const enteredPromise = new Promise((resolve) => { entered = resolve; });
  let release;
  const releasePromise = new Promise((resolve) => { release = resolve; });
  const running = runCheck({
    repo, task: task(), checkId: 'unit', backends: mockBackends,
    executor: async () => {
      entered();
      await releasePromise;
      return { exitCode: 0, stdout: verifierOutput(), stderr: '' };
    },
  });
  await enteredPromise;
  const lock = join(repo, '.ui-results/unit.json.ui-delivery.lock');
  await writeFile(lock, 'replacement', 'utf8');
  release();
  await running;
  assert.equal(await readFile(lock, 'utf8'), 'replacement');
  await rm(lock);
});

test('keeps comma-bearing declared outputs out of Docker mount options', async () => {
  const repo = await fixture();
  const calls = [];
  const resultPath = '.ui-results/unit,ro=false.json';

  await runCheck({
    repo,
    task: task({ approved_check_recipes: [{ ...recipe, backend: 'docker', result_path: resultPath, write_paths: [resultPath] }] }),
    checkId: 'unit',
    executor: executor(calls),
    backends: mockBackends,
  });
  assert.equal(calls[0].argv.filter((argument) => argument.includes(resultPath)).length, 0);
});

test('prepares a qualified pilot task with approval and active-runtime handoff', async () => {
  const { stdout } = await execFileAsync(process.execPath, ['tests/fixtures/ui-delivery-consumer/prepare.mjs', tmpdir()]);
  const prepared = JSON.parse(stdout);
  const priorApproval = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  const priorQualification = process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
  try {
    for (const launch of prepared.cases) {
      const preparedTask = JSON.parse(await readFile(launch.task, 'utf8'));
      assert.equal(preparedTask.approved_check_recipes[0].argv[0], 'node');
      assert.equal(preparedTask.qualification_hash, launch.active_qualification_sha256);
      process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = launch.external_approval_sha256;
      process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = launch.active_qualification_sha256;
      await loadTask({ repo: launch.repo, taskFile: launch.task, operation: 'patch' });
    }
  } finally {
    if (priorApproval === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = priorApproval;
    if (priorQualification === undefined) delete process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
    else process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = priorQualification;
    await rm(dirname(prepared.cases[0].repo), { recursive: true, force: true });
  }
});
