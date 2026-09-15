import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';
import { bindCandidate, digest, execute, extensionApi, fixture, policyWithCheckRunner, success, task } from './ui-delivery-policy-helpers.test.mjs';

test('accepts a legitimate deterministic check rerun that reproduces identical successful bytes', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  const resultPath = join(repo, '.ui-results/unit.json');
  const deterministic = JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 });
  policyWithCheckRunner(api, async () => {
    await writeFile(resultPath, deterministic);
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  const run = () => execute(
    tools.find((entry) => entry.name === 'ui_run_check'),
    { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' },
    repo,
  );
  await run();
  const rerun = await run();
  assert.equal(rerun.details.exitCode, 0);
});

test('still rejects a runner that reports success without writing a fresh result', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
  policyWithCheckRunner(api, async () => success());
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(
    tools.find((entry) => entry.name === 'ui_run_check'),
    { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' },
    repo,
  ), /fresh|stale|result/i);
});
