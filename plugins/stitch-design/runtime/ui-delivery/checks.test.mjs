import assert from 'node:assert/strict';
import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from 'node:fs/promises';
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

function task(overrides = {}) {
  return { allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'], approved_check_recipes: [recipe], ...overrides };
}

function verifierOutput({ result = { schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }, artifacts = [] } = {}) {
  return `${JSON.stringify({ schema: 'ui-delivery-verifier-output-v1', result, artifacts })}\n`;
}
const mockBackends = { docker: true };
const nonRootHostIdentity = { getuid: () => 501, getgid: () => 20 };
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
    executor: executor(calls), backends: mockBackends, hostIdentity: nonRootHostIdentity,
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, 'docker');
  assert.deepEqual(calls[0].recipeArgv, recipe.argv);
  assert.ok(calls[0].argv.includes('/trusted-verifier'));
  assert.ok(!calls[0].argv.includes('sh'));
  const canonicalRepo = await realpath(repo);
  assert.equal(calls[0].cwd, canonicalRepo);
  assert.equal(calls[0].env.TOKEN, undefined);
  assert.equal(calls[0].env.HOME, undefined);
  assert.equal(calls[0].env.TMPDIR, undefined);
  assert.ok(!calls[0].mounts.some((mount) => mount.source === join(canonicalRepo, '.ui-results/unit.json') && !mount.readOnly));
  assert.ok(!calls[0].mounts.some((mount) => mount.source === join(canonicalRepo, 'src/Card.tsx') && !mount.readOnly));
  assert.deepEqual(result.argv, recipe.argv);
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
      backends: mockBackends, hostIdentity: nonRootHostIdentity,
    }));
  }
  await assert.rejects(() => runCheck({ repo, task: task(), checkId: 'unit', command: 'node --test; touch owned', executor: executor([]), backends: mockBackends, hostIdentity: nonRootHostIdentity }));
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
      backends: mockBackends, hostIdentity: nonRootHostIdentity,
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
      backends: mockBackends, hostIdentity: nonRootHostIdentity,
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
    () => runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends, hostIdentity: nonRootHostIdentity }),
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
    () => runCheck({ repo, task: task(), checkId: 'unit', executor: executor([]), backends: mockBackends, hostIdentity: nonRootHostIdentity }),
    /trusted verifier/,
  );
});
