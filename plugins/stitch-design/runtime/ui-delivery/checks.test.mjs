import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { access, chmod, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import { runCheck } from './checks.ts';
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
const sandboxExecAvailable = process.platform === 'darwin' && await access('/usr/bin/sandbox-exec', constants.X_OK).then(() => true, () => false);
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

test('allows only the digest-checked verifier beneath protected .omp state', { skip: !sandboxExecAvailable }, async () => {
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

test('preserves a verifier envelope split within a UTF-8 scalar', { skip: !sandboxExecAvailable }, async () => {
  const repo = await fixture();
  const output = verifierOutput({ result: { label: 'é' } });
  const script = `const output = Buffer.from(${JSON.stringify(output)}); const split = output.indexOf(Buffer.from('é')) + 1; process.stdout.write(output.subarray(0, split)); setTimeout(() => process.stdout.write(output.subarray(split)), 10);`;
  await writeFile(join(repo, verifier.path), script);
  const sha256 = `sha256:${createHash('sha256').update(script).digest('hex')}`;
  await runCheck({
    repo,
    task: task({ approved_check_recipes: [{ ...recipe, trusted_verifier: { ...verifier, sha256 } }] }),
    checkId: 'unit',
  });
  assert.deepEqual(JSON.parse(await readFile(join(repo, '.ui-results/unit.json'), 'utf8')), { label: 'é' });
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


