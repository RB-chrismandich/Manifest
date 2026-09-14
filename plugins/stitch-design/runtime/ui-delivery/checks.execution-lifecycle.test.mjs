import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, open, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { runCheck } from './checks.ts';

const verifier = {
  path: '.omp/ui-delivery/verifiers/verify.mjs',
  sha256: 'sha256:f9974862b9b6c9cbb2ef52e20d18eec093825ec2b8fb7dde84abe593d480ed3f',
};
const recipe = {
  id: 'unit', argv: ['node', verifier.path], cwd: '.', timeout_ms: 500,
  backend: 'docker', sandbox_image: 'registry.example/ui-check@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
  result_path: '.ui-results/unit.json', write_paths: ['.ui-results/unit.json'], trusted_verifier: verifier,
};
const mockBackends = { docker: true };
const nonRootHostIdentity = { getuid: () => 501, getgid: () => 20 };

function task(overrides = {}) {
  return { allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'], approved_check_recipes: [recipe], ...overrides };
}

function verifierOutput({ result = { schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }, artifacts = [] } = {}) {
  return `${JSON.stringify({ schema: 'ui-delivery-verifier-output-v1', result, artifacts })}\n`;
}

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
  await mkdir(join(repo, '.omp/ui-delivery/verifiers'), { recursive: true });
  await writeFile(join(repo, verifier.path), 'trusted verifier\n');
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  return repo;
}

test('terminates the workload and removes scratch on timeout or abort before returning', async () => {
  const repo = await fixture();
  const scratchRoot = await mkdtemp(join(tmpdir(), 'ui-delivery-scratch-root-'));
  const controller = new AbortController();
  const calls = [];
  controller.abort();
  await assert.rejects(() => runCheck({
    repo, task: task(), checkId: 'unit', signal: controller.signal, scratchRoot, executor: executor(calls), backends: mockBackends, hostIdentity: nonRootHostIdentity,
  }));
  assert.equal(calls.length, 0);
  await assert.rejects(() => runCheck({
    repo, task: task({ approved_check_recipes: [{ ...recipe, timeout_ms: 1 }] }), checkId: 'unit', scratchRoot, backends: mockBackends, hostIdentity: nonRootHostIdentity,
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
      repo, task: task(), checkId: 'unit', signal, executor: executor([]), backends: mockBackends, hostIdentity: nonRootHostIdentity,
    });
    await assert.rejects(() => runCheck({
      repo, task: task(), checkId: 'unit', signal, executor: async () => { throw new Error('injected failure'); }, backends: mockBackends, hostIdentity: nonRootHostIdentity,
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
  await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends, hostIdentity: nonRootHostIdentity });
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
    repo, task: task({ approved_check_recipes: [firstRecipe] }), checkId: 'first', backends: mockBackends, hostIdentity: nonRootHostIdentity,
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
        repo, task: task({ approved_check_recipes: [secondRecipe] }), checkId: 'second', backends: mockBackends, hostIdentity: nonRootHostIdentity,
        executor: async () => ({ exitCode: 0, stdout: verifierOutput({ result: { attempt: 'second' } }), stderr: '' }),
      }),
      /output|lock|concurrent/i,
    );
  } finally {
    release();
  }
  await first;
  await runCheck({
    repo, task: task({ approved_check_recipes: [secondRecipe] }), checkId: 'second', backends: mockBackends, hostIdentity: nonRootHostIdentity,
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
    repo, task: task(), checkId: 'unit', backends: mockBackends, hostIdentity: nonRootHostIdentity,
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

test('removes a lock created before its owner token write fails', async () => {
  const repo = await fixture();
  const handle = await open(join(repo, 'prototype-probe'), 'w');
  const prototype = Object.getPrototypeOf(handle);
  await handle.close();
  const originalWriteFile = prototype.writeFile;
  prototype.writeFile = async function (data, ...args) {
    if (String(data).length === 36) throw new Error('owner write failed');
    return originalWriteFile.call(this, data, ...args);
  };
  try {
    await assert.rejects(
      () => runCheck({ repo, task: task(), checkId: 'unit', executor: executor([]), backends: mockBackends, hostIdentity: nonRootHostIdentity }),
      /owner write failed/,
    );
    await assert.rejects(() => readFile(join(repo, '.ui-results/unit.json.ui-delivery.lock'), 'utf8'), { code: 'ENOENT' });
  } finally {
    prototype.writeFile = originalWriteFile;
  }
});
