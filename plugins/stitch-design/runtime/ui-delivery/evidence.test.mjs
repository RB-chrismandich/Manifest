import assert from 'node:assert/strict';
import { chmod, link, mkdtemp, mkdir, open, readFile, readdir, rename, rm, symlink, unlink, writeFile } from 'node:fs/promises';
import { hostname, tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { appendEvidence, canonicalJsonHash, loadStitchMutationState, readEvidence, updateStitchMutationState } from './evidence.ts';

const binding = {
  taskId: 'task-17', approvedDesignHash: 'sha256:design', candidateRevision: 'git:abc123',
  candidateHash: 'sha256:candidate', modelRoute: '@ui_code', operation: 'ui_run_check',
  checkId: 'unit', outcome: 'verified', elapsedMs: 42,
  artifacts: [{ path: 'evidence/page.png', hash: 'sha256:artifact' }],
  stdoutHash: 'sha256:stdout', stderrHash: 'sha256:stderr',
};

async function fixture() {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-evidence-'));
  const evidenceDirectory = join(repo, '.omp/ui-delivery/evidence');
  await mkdir(evidenceDirectory, { recursive: true });
  return { repo, evidenceFile: join(evidenceDirectory, 'task-17.jsonl') };
}

test('hashes semantically identical JSON canonically regardless of object key order', () => {
  assert.equal(canonicalJsonHash({ b: [2, 1], a: { y: true, x: null } }), canonicalJsonHash({ a: { x: null, y: true }, b: [2, 1] }));
});

test('hashes composed and decomposed keys by deterministic Unicode code-unit order', () => {
  const composed = '\u00e9';
  const decomposed = 'e\u0301';
  assert.equal(
    canonicalJsonHash({ [composed]: 'composed', [decomposed]: 'decomposed' }),
    canonicalJsonHash({ [decomposed]: 'decomposed', [composed]: 'composed' }),
  );
});

test('appends an evidence record bound to task, approved design, candidate, model, operation, and hashes', async () => {
  const { repo, evidenceFile } = await fixture();
  await appendEvidence({ repo, evidenceFile, record: binding });
  const [record] = (await readFile(evidenceFile, 'utf8')).trim().split('\n').map(JSON.parse);
  assert.deepEqual(record, binding);
});

test('reads authorized regular evidence and treats a missing evidence file as absent', async () => {
  const { repo, evidenceFile } = await fixture();
  await writeFile(evidenceFile, '{"record":true}\n');
  assert.equal(await readEvidence({ repo, evidenceFile }), '{"record":true}\n');
  await unlink(evidenceFile);
  assert.equal(await readEvidence({ repo, evidenceFile }), undefined);
});

test('rejects a group- or world-writable evidence file even with expected type and link count', async () => {
  const { repo, evidenceFile } = await fixture();
  await appendEvidence({ repo, evidenceFile, record: binding });
  await chmod(evidenceFile, 0o666);
  await assert.rejects(() => readEvidence({ repo, evidenceFile }), /unsafe/i);
});

test('refuses evidence missing any required identity or bounded-output hash', async () => {
  const { repo, evidenceFile } = await fixture();
  await assert.rejects(() => appendEvidence({ repo, evidenceFile, record: { ...binding, candidateHash: undefined } }));
  await assert.rejects(() => appendEvidence({ repo, evidenceFile, record: { ...binding, stderrHash: undefined } }));
});

test('rejects evidence-file traversal and a final symlink escaping the task evidence directory', async () => {
  const { repo, evidenceFile } = await fixture();
  await assert.rejects(() => appendEvidence({ repo, evidenceFile: join(repo, '.omp/ui-delivery/evidence/../tasks/task.jsonl'), record: binding }));
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-evidence-outside-'));
  const escaped = join(repo, '.omp/ui-delivery/evidence/escaped.jsonl');
  await symlink(join(outside, 'escaped.jsonl'), escaped);
  await assert.rejects(() => appendEvidence({ repo, evidenceFile: escaped, record: binding }));
});

test('rejects a symlinked policy-directory component and a multiply-linked evidence file', async () => {
  const { repo, evidenceFile } = await fixture();
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-evidence-outside-'));
  const policyRoot = join(repo, '.omp/ui-delivery');
  await rm(policyRoot, { recursive: true });
  await mkdir(join(outside, 'evidence'), { recursive: true });
  await symlink(outside, policyRoot);
  await assert.rejects(() => appendEvidence({ repo, evidenceFile, record: binding }));

  const second = await fixture();
  await appendEvidence({ repo: second.repo, evidenceFile: second.evidenceFile, record: binding });
  await link(second.evidenceFile, join(second.repo, 'linked.jsonl'));
  await assert.rejects(() => appendEvidence({ repo: second.repo, evidenceFile: second.evidenceFile, record: binding }));
});

test('preserves append-only JSONL history rather than rewriting an earlier record', async () => {
  const { repo, evidenceFile } = await fixture();
  await appendEvidence({ repo, evidenceFile, record: binding });
  await appendEvidence({ repo, evidenceFile, record: { ...binding, operation: 'ui_capture', elapsedMs: 84 } });
  const lines = (await readFile(evidenceFile, 'utf8')).trim().split('\n');
  assert.equal(lines.length, 2);
  assert.equal(JSON.parse(lines[0]).operation, 'ui_run_check');
  assert.equal(JSON.parse(lines[1]).operation, 'ui_capture');
});

test('rejects malformed existing mutation state instead of treating it as absent', async () => {
  const { repo } = await fixture();
  const stateFile = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json');
  await writeFile(stateFile, '{"version":"invalid"}');
  await assert.rejects(
    () => loadStitchMutationState({ repo, taskId: 'task-17', authorizationDigest: 'sha256:approved' }),
    /malformed/i,
  );
});

test('treats mutation state left under a superseded authorization digest as absent and safely reinitializes it under the newly approved digest', async () => {
  const { repo } = await fixture();
  await updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:previous', expectedVersion: 0,
    state: { entries: { mutation: 'consumed' }, projectId: 'project-17' },
  });
  const stale = await loadStitchMutationState({ repo, taskId: 'task-17', authorizationDigest: 'sha256:reapproved' });
  assert.equal(stale, undefined);
  const next = await updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:reapproved', expectedVersion: 0,
    state: { entries: {}, projectId: 'project-17' },
  });
  assert.equal(next.authorizationDigest, 'sha256:reapproved');
  assert.equal(next.version, 1);
  assert.deepEqual(next.entries, {});
});

test('does not unlink a mutation lock owned by a failed contender', async () => {
  const { repo } = await fixture();
  const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
  const owner = await open(lock, 'wx', 0o600);
  try {
    await assert.rejects(() => updateStitchMutationState({
      repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
      state: { entries: {}, projectId: 'project-17' },
    }));
    await owner.stat();
  } finally {
    await owner.close();
    await rm(lock);
  }
});

const deadProcess = () => false;
const liveProcess = () => true;
function lockOwner({ host = hostname(), bootId = 'test-boot', pid = 987_654, nonce = '00000000-0000-4000-8000-000000000001' } = {}) {
  return JSON.stringify({ pid, host, bootId, nonce });
}
const testLockEnvironment = { host: hostname(), bootId: 'test-boot', processExists: deadProcess };

test('recovers a same-boot mutation lock after its owner process terminates', async () => {
  const { repo } = await fixture();
  const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
  await writeFile(lock, lockOwner(), { mode: 0o600 });
  const state = await updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: {}, projectId: 'project-17' }, lockEnvironment: testLockEnvironment,
  });
  assert.equal(state.version, 1);
  await assert.rejects(() => readFile(lock), { code: 'ENOENT' });
});

test('recovers a prior-boot mutation lock on this host', async () => {
  const { repo } = await fixture();
  const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
  await writeFile(lock, lockOwner({ bootId: 'prior-boot' }), { mode: 0o600 });
  const state = await updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: {}, projectId: 'project-17' }, lockEnvironment: testLockEnvironment,
  });
  assert.equal(state.version, 1);
});

test('denies a live mutation lock and preserves its owner metadata', async () => {
  const { repo } = await fixture();
  const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
  const owner = lockOwner();
  await writeFile(lock, owner, { mode: 0o600 });
  await assert.rejects(() => updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: {}, projectId: 'project-17' }, lockEnvironment: { ...testLockEnvironment, processExists: liveProcess },
  }), /concurrently|busy/i);
  assert.equal(await readFile(lock, 'utf8'), owner);
});

test('denies a same-host live mutation lock despite a differing boot identity', async () => {
  const { repo } = await fixture();
  const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
  const owner = lockOwner({ bootId: 'different-boot' });
  await writeFile(lock, owner, { mode: 0o600 });
  await assert.rejects(() => updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: {}, projectId: 'project-17' }, lockEnvironment: { ...testLockEnvironment, processExists: liveProcess },
  }), /concurrently|busy/i);
  assert.equal(await readFile(lock, 'utf8'), owner);
});

test('denies malformed and foreign-host mutation locks', async () => {
  for (const owner of ['not-json', lockOwner({ host: 'another-host' })]) {
    const { repo } = await fixture();
    const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
    await writeFile(lock, owner, { mode: 0o600 });
    await assert.rejects(() => updateStitchMutationState({
      repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
      state: { entries: {}, projectId: 'project-17' }, lockEnvironment: testLockEnvironment,
    }), /malformed|concurrently|busy/i);
    assert.equal(await readFile(lock, 'utf8'), owner);
  }
});

test('preserves a contender lock that replaces its acquired mutation lock', async () => {
  const { repo } = await fixture();
  const lock = join(repo, '.omp/ui-delivery/evidence/task-17.stitch-state.json.lock');
  const contender = lockOwner({ nonce: '00000000-0000-4000-8000-000000000002' });
  const persistence = {
    async open(path, flags, mode) { return open(path, flags, mode); },
    async rename(source, target) {
      await rename(source, target);
      await unlink(lock);
      await writeFile(lock, contender, { mode: 0o600 });
    },
    unlink,
  };
  await updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: {}, projectId: 'project-17' }, persistence, lockEnvironment: testLockEnvironment,
  });
  assert.equal(await readFile(lock, 'utf8'), contender);
});

test('syncs consumed mutation state before rename and its directory after rename', async () => {
  const { repo } = await fixture();
  const evidenceDirectory = join(repo, '.omp/ui-delivery/evidence');
  const events = [];
  const persistence = {
    async open(path, flags, mode) {
      const handle = await open(path, flags, mode);
      return {
        write: (...args) => handle.write(...args),
        sync: async () => { events.push(`sync:${path}`); await handle.sync(); },
        close: async () => { events.push(`close:${path}`); await handle.close(); },
      };
    },
    async rename(from, to) { events.push(`rename:${from}:${to}`); await rename(from, to); },
    unlink,
  };

  await updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: { mutation: 'consumed' }, projectId: 'project-17' },
    persistence,
  });

  const temporary = events.find((event) => event.startsWith('sync:') && event.includes('.tmp'));
  const renamed = events.find((event) => event.startsWith('rename:'));
  const directorySync = events.find((event) => event.startsWith('sync:') && !event.includes('.tmp') && !event.endsWith('.lock'));
  assert.ok(temporary);
  assert.ok(renamed);
  assert.ok(directorySync);
  assert.ok(events.indexOf(temporary) < events.indexOf(renamed));
  assert.ok(events.indexOf(renamed) < events.indexOf(directorySync));
  assert.ok(events.includes(`close:${directorySync.slice('sync:'.length)}`));
});

test('cleans up a synced temporary mutation state when rename fails', async () => {
  const { repo } = await fixture();
  const closed = [];
  const persistence = {
    async open(path, flags, mode) {
      const handle = await open(path, flags, mode);
      return {
        write: (...args) => handle.write(...args),
        sync: (...args) => handle.sync(...args),
        close: async () => { closed.push(path); await handle.close(); },
      };
    },
    async rename() { throw new Error('rename failed'); },
    unlink,
  };

  await assert.rejects(() => updateStitchMutationState({
    repo, taskId: 'task-17', authorizationDigest: 'sha256:approved', expectedVersion: 0,
    state: { entries: { mutation: 'consumed' }, projectId: 'project-17' },
    persistence,
  }), /rename failed/);
  const evidenceDirectory = join(repo, '.omp/ui-delivery/evidence');
  const entries = await readdir(evidenceDirectory);
  assert.equal(entries.filter((entry) => entry.includes('.tmp')).length, 0);
  assert.ok(closed.some((path) => path.includes('.tmp')));
});
