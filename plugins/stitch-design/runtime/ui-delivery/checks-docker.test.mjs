import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
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

function verifierOutput() {
  return `${JSON.stringify({ schema: 'ui-delivery-verifier-output-v1', result: { schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }, artifacts: [] })}\n`;
}

function executor(calls) {
  return async (command) => {
    calls.push(command);
    return { exitCode: 0, stdout: verifierOutput(), stderr: 'stderr' };
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

test('keeps comma-bearing declared outputs out of Docker mount options', async () => {
  const repo = await fixture();
  const calls = [];
  const resultPath = '.ui-results/unit,ro=false.json';
  await runCheck({
    repo,
    task: task({ approved_check_recipes: [{ ...recipe, backend: 'docker', result_path: resultPath, write_paths: [resultPath] }] }),
    checkId: 'unit', executor: executor(calls), backends: { 'sandbox-exec': true, docker: true },
  });
  assert.equal(calls[0].argv.filter((argument) => argument.includes(resultPath)).length, 0);
});
