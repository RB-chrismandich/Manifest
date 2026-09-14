import assert from 'node:assert/strict';
import { link, mkdtemp, mkdir, readFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { appendEvidence, canonicalJsonHash } from './evidence.ts';

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

test('appends an evidence record bound to task, approved design, candidate, model, operation, and hashes', async () => {
  const { repo, evidenceFile } = await fixture();
  await appendEvidence({ repo, evidenceFile, record: binding });
  const [record] = (await readFile(evidenceFile, 'utf8')).trim().split('\n').map(JSON.parse);
  assert.deepEqual(record, binding);
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
