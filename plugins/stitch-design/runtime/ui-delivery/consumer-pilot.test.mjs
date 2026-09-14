import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import { loadTask } from './task.ts';

const execFileAsync = promisify(execFile);

test('prepares a qualified pilot task with approval and active-runtime handoff', async () => {
  const { stdout } = await execFileAsync(process.execPath, ['tests/fixtures/ui-delivery-consumer/prepare.mjs', tmpdir()]);
  const prepared = JSON.parse(stdout);
  const priorApproval = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  const priorQualification = process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
  try {
    for (const launch of prepared.cases) {
      const preparedTask = JSON.parse(await readFile(launch.task, 'utf8'));
      assert.equal(preparedTask.approved_check_recipes[0].argv[0], 'node');
      assert.equal(preparedTask.approved_check_recipes[1].backend, 'docker');
      assert.equal(preparedTask.approved_check_recipes[1].argv[0], 'python3');
      assert.match(preparedTask.approved_check_recipes[1].sandbox_image, /@sha256:[a-f0-9]{64}$/);
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
