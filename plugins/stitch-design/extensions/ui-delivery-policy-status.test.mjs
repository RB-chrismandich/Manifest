import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { appendFile, link, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';
import { appendAttempt, appendCaptureEvidence, bindCandidate, digest, evidenceRecord, execute, extensionApi, fixture, policyWithCheckRunner, success, task, withApproval } from './ui-delivery-policy-helpers.test.mjs';

test('status requires candidate-bound evidence for every approved check and capture before verified', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
    approved_check_recipes: [
      ...task().approved_check_recipes,
      { ...task().approved_check_recipes[0], id: 'visual', result_path: '.ui-results/visual.json', write_paths: ['.ui-results/visual.json'] },
    ],
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await writeFile(join(repo, '.ui-results/visual.json'), '{"prior":true}\n');
  await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
  await appendAttempt(evidenceFile, definition, { attemptId: 'visual-1', operation: 'ui_run_check', checkId: 'visual', outcome: 'verified' });
  const page = await readFile(join(repo, 'evidence/page.png'));
  await appendAttempt(evidenceFile, definition, {
    attemptId: 'capture-1', operation: 'ui_capture', recipeId: 'capture', outcome: 'captured',
    artifacts: [{ path: 'evidence/page.png', hash: `sha256:${createHash('sha256').update(page).digest('hex')}` }],
  });
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
  await appendAttempt(evidenceFile, definition, {
    attemptId: 'unit-2', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified',
    modelRoute: '@ui_review', authorizationDigest: digest(definition),
  });
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
  await appendAttempt(evidenceFile, definition, {
    attemptId: 'unit-3', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified',
    authorizationDigest: digest(definition),
  });
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status invalidates historical check success after the latest rerun is unfinished or failed', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
  await appendCaptureEvidence(evidenceFile, definition, repo);
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId: 'unit-2', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending' }))}\n`);
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId: 'unit-2', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'failed' }))}\n`);
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status fails closed when any nonempty evidence line is malformed', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
  await appendCaptureEvidence(evidenceFile, definition, repo);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
  await appendFile(evidenceFile, '{malformed\n');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status cannot let an older concurrent completion override a later-started failed attempt', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendCaptureEvidence(evidenceFile, definition, repo);
  for (const entry of [
    evidenceRecord(definition, { attemptId: 'unit-old', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending' }),
    evidenceRecord(definition, { attemptId: 'unit-new', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending' }),
    evidenceRecord(definition, { attemptId: 'unit-new', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'failed' }),
    evidenceRecord(definition, { attemptId: 'unit-old', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' }),
  ]) await appendFile(evidenceFile, `${JSON.stringify(entry)}\n`);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status cannot reuse evidence whose authorization digest predates an otherwise identical recipe ID', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
  });
  const oldDigest = digest({ ...definition, approved_check_recipes: [{ ...definition.approved_check_recipes[0], argv: ['node', '--test', 'old.mjs'] }] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendCaptureEvidence(evidenceFile, definition, repo);
  for (const entry of [
    evidenceRecord(definition, { attemptId: 'unit-1', attemptPhase: 'started', operation: 'ui_run_check', checkId: 'unit', outcome: 'pending', authorizationDigest: oldDigest }),
    evidenceRecord(definition, { attemptId: 'unit-1', attemptPhase: 'completed', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified', authorizationDigest: oldDigest }),
  ]) await appendFile(evidenceFile, `${JSON.stringify(entry)}\n`);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false);
});

test('status requires builder checks only for unreferenced recipes and reviewer capture for capture-only recipes', async () => {
  const captureCheck = task().approved_check_recipes.find((recipe) => recipe.id === 'capture-unit');
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
    approved_check_recipes: [captureCheck, { ...captureCheck, id: 'build', result_path: '.ui-results/build.json', write_paths: ['.ui-results/build.json'] }],
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
  await appendAttempt(evidenceFile, definition, { attemptId: 'build-1', operation: 'ui_run_check', checkId: 'build', outcome: 'verified' });
  await appendCaptureEvidence(evidenceFile, definition, repo);
  const status = tools.find((entry) => entry.name === 'ui_delivery_status');
  assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
});

test('rejects ui_run_check for a capture-only recipe before invoking the runner', async () => {
  const captureCheck = task().approved_check_recipes.find((recipe) => recipe.id === 'capture-unit');
  const definition = task({
    state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}`,
    approved_check_recipes: [captureCheck, { ...captureCheck, id: 'build', result_path: '.ui-results/build.json', write_paths: ['.ui-results/build.json'] }],
  });
  const { api, tools } = extensionApi(); let calls = 0;
  const { repo } = await fixture(definition); await bindCandidate(repo, definition);
  policyWithCheckRunner(api, async () => {
    calls += 1;
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), {
    taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'capture-unit',
  }, repo), /capture|review/i));
  assert.equal(calls, 0);
});

test('status requires current regular capture artifacts with exact complete hashes', async () => {
  for (const scenario of ['missing', 'replaced', 'symlinked', 'wrong hash', 'incomplete']) {
    const definition = task({
      state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
      candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
      approved_check_recipes: [{ ...task().approved_check_recipes[0], write_paths: ['.ui-results/unit.json', 'evidence/page.png', 'evidence/other.png'] }],
      capture_recipes: [{ id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }, { path: 'evidence/other.png', type: 'screenshot' }] }],
    });
    const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
    const { repo } = await fixture(definition);
    await writeFile(join(repo, 'evidence/other.png'), 'other capture');
    await bindCandidate(repo, definition);
    const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
    const paths = ['evidence/page.png', 'evidence/other.png'];
    const artifacts = await Promise.all(paths.map(async (path) => ({ path, hash: `sha256:${createHash('sha256').update(await readFile(join(repo, path))).digest('hex')}` })));
    await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
    await appendAttempt(evidenceFile, definition, { attemptId: 'capture-1', operation: 'ui_capture', recipeId: 'capture', outcome: 'captured', artifacts });
    const status = tools.find((entry) => entry.name === 'ui_delivery_status');
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
    if (scenario === 'missing') await rm(join(repo, 'evidence/page.png'));
    if (scenario === 'replaced') await writeFile(join(repo, 'evidence/page.png'), 'replacement capture');
    if (scenario === 'symlinked') {
      await rm(join(repo, 'evidence/page.png'));
      await symlink(join(repo, 'evidence/other.png'), join(repo, 'evidence/page.png'));
    }
    const badArtifacts = scenario === 'wrong hash' ? [{ ...artifacts[0], hash: `sha256:${'0'.repeat(64)}` }, artifacts[1]]
      : scenario === 'incomplete' ? [artifacts[0]] : artifacts;
    await appendAttempt(evidenceFile, definition, { attemptId: 'capture-2', operation: 'ui_capture', recipeId: 'capture', outcome: 'captured', artifacts: badArtifacts });
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false, scenario);
  }
});

test('status refuses symlinked and multiply-linked evidence files even when their records verify', async () => {
  for (const scenario of ['symlink', 'hard-link']) {
    const definition = task({
      state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
      candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://task-17/evidence'], model_route: '@ui_review',
    });
    const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
    const { repo } = await fixture(definition); await bindCandidate(repo, definition);
    const evidenceFile = join(repo, '.omp/ui-delivery/evidence/task-17.jsonl');
    await appendAttempt(evidenceFile, definition, { attemptId: 'unit-1', operation: 'ui_run_check', checkId: 'unit', outcome: 'verified' });
    await appendCaptureEvidence(evidenceFile, definition, repo);
    const status = tools.find((entry) => entry.name === 'ui_delivery_status');
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, true);
    if (scenario === 'symlink') {
      const records = await readFile(evidenceFile, 'utf8');
      const outside = join(repo, 'evidence', 'records.jsonl');
      await writeFile(outside, records);
      await rm(evidenceFile);
      await symlink(outside, evidenceFile);
    } else {
      await link(evidenceFile, join(repo, '.omp/ui-delivery/evidence/task-17-copy.jsonl'));
    }
    assert.equal((await execute(status, { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo)).details.verified, false, scenario);
  }
});

test('status never reports accepted work verified without matching local evidence', async () => {
  const definition = task({
    state: 'accepted', outcome: 'verified', candidate_revision: 'git:abc',
    candidate_hash: `sha256:${'0'.repeat(64)}`, evidence_refs: ['artifact://missing'], model_route: '@ui_review',
  });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const response = await execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task.json' }, repo);
  assert.equal(response.details.outcome, 'evidence_unverified');
  assert.equal(response.details.approved, false);
  assert.match(response.details.authorizationDigest, /^sha256:[a-f0-9]{64}$/);
});
