import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, realpath, symlink, writeFile } from 'node:fs/promises';
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

test('writes verifier-declared results only after the sandbox exits without mounting outputs', async () => {
  const repo = await fixture();
  const calls = [];
  await runCheck({ repo, task: task(), checkId: 'unit', executor: executor(calls), backends: mockBackends });
  assert.deepEqual(JSON.parse(await readFile(join(repo, '.ui-results/unit.json'), 'utf8')), {
    schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0,
  });
  assert.equal(calls[0].mounts.some((mount) => !mount.readOnly && mount.target.startsWith('/repo/.ui-results')), false);
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
