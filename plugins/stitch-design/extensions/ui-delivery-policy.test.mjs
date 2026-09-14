import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import uiDeliveryPolicy from './ui-delivery-policy.ts';
import { bindCandidate, digest, execute, extensionApi, fixture, policyWithCheckRunner, success, task, withoutApproval, withApproval } from './ui-delivery-policy-helpers.test.mjs';

test('registers the deterministic UI delivery surface with exact OMP approval tiers', () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  assert.deepEqual(tools.map((tool) => tool.name).sort(), ['ui_apply_patch', 'ui_capture', 'ui_delivery_status', 'ui_run_check']);
  assert.deepEqual(Object.fromEntries(tools.map((tool) => [tool.name, tool.approval])), {
    ui_delivery_status: 'read', ui_apply_patch: 'write', ui_run_check: 'exec', ui_capture: 'exec',
  });
});

test('requires the external digest for patch, check, and capture even when repository JSON self-approves', async () => {
  const { api, tools } = extensionApi();
  uiDeliveryPolicy(api);
  for (const [name, args, definition] of [
    ['ui_apply_patch', { taskFile: '.omp/ui-delivery/tasks/task.json', patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-x\n+y\n' }, task()],
    ['ui_run_check', { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` })],
    ['ui_capture', { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'capture' }, task({ state: 'reviewing', model_route: '@ui_review', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` })],
  ]) {
    const { repo } = await fixture(definition);
    if (name !== 'ui_apply_patch') {
      await bindCandidate(repo, definition);
    }
    const tool = tools.find((entry) => entry.name === name);
    await withoutApproval(() => assert.rejects(() => execute(tool, args, repo), /approval/i));
  }
});

test('fails closed on every unparseable, alternate, destructive, or symlink diff entry', async () => {
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo, definition } = await fixture();
  const tool = tools.find((entry) => entry.name === 'ui_apply_patch');
  await withApproval(definition, async () => {
    for (const patch of [
      'diff --git x/src/Card.tsx y/.omp/ui-delivery/tasks/task.json\n--- x/src/Card.tsx\n+++ y/.omp/ui-delivery/tasks/task.json\n',
      'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ /dev/null\n',
      'diff --git a/src/Card.tsx b/src/Card.tsx\nnew mode 120000\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n',
      'diff --git a/src/Card.tsx b/src/Renamed.tsx\nsimilarity index 100%\nrename from src/Card.tsx\nrename to src/Renamed.tsx\n',
    ]) await assert.rejects(
      () => execute(tool, { taskFile: '.omp/ui-delivery/tasks/task.json', patch }, repo),
      /unsafe|unparseable|destructive|symlink|diff policy/i,
    );
  });
});

test('rejects Git-quoted paths with spaces before patch mutation', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git "a/src/Card View.tsx" "b/src/Card View.tsx"\n--- "a/src/Card View.tsx"\n+++ "b/src/Card View.tsx"\n@@ -0,0 +1 @@\n+x\n',
  }, repo), /unsafe|unparseable|path/i));
});

test('rejects .omp verifier mutations even when a broad allowed path grants the repository root', async () => {
  const definition = task({ allowed_paths: ['.'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/.omp/ui-delivery/verifiers/unit.mjs b/.omp/ui-delivery/verifiers/unit.mjs\n--- a/.omp/ui-delivery/verifiers/unit.mjs\n+++ b/.omp/ui-delivery/verifiers/unit.mjs\n@@ -1 +1 @@\n-x\n+y\n',
  }, repo), /protected|path/i));
});

test('applies a same-path regular diff with standard index metadata', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\nindex 1111111111111111111111111111111111111111..2222222222222222222222222222222222222222 100644\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/Card.tsx'), 'utf8'), 'export const Card = 2;\n');
});

test('applies same-file hunks whose payload lines resemble unified-diff file headers', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await writeFile(join(repo, 'src/Card.tsx'), '-- example\n');
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n--- example\n+++ example\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/Card.tsx'), 'utf8'), '++ example\n');
});

test('rejects a same-file hunk whose declared line count does not match its payload', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1,2 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo), /malformed|unparseable|hunk/i));
});

test('applies an absolute task file patch and updates that validated task', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const taskFile = join(repo, '.omp/ui-delivery/tasks/task.json');
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile,
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo));
  assert.equal(JSON.parse(await readFile(taskFile, 'utf8')).state, 'candidate_ready');
});

test('applies a standard new regular-file diff', async () => {
  const definition = task({ allowed_paths: ['src/New.tsx'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/New.tsx b/src/New.tsx\nnew file mode 100644\nindex 0000000000000000000000000000000000000000..2222222222222222222222222222222222222222\n--- /dev/null\n+++ b/src/New.tsx\n@@ -0,0 +1 @@\n+export const New = 1;\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/New.tsx'), 'utf8'), 'export const New = 1;\n');
});

test('accepts a safe new regular-file diff without optional index metadata', async () => {
  const definition = task({ allowed_paths: ['src/NoIndex.tsx'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/NoIndex.tsx b/src/NoIndex.tsx\nnew file mode 100644\n--- /dev/null\n+++ b/src/NoIndex.tsx\n@@ -0,0 +1 @@\n+export const NoIndex = 1;\n',
  }, repo));
  assert.equal(await readFile(join(repo, 'src/NoIndex.tsx'), 'utf8'), 'export const NoIndex = 1;\n');
});

test('rejects malformed present index metadata on a new regular-file diff', async () => {
  const definition = task({ allowed_paths: ['src/Malformed.tsx'] });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Malformed.tsx b/src/Malformed.tsx\nnew file mode 100644\nindex not-an-index\n--- /dev/null\n+++ b/src/Malformed.tsx\n@@ -0,0 +1 @@\n+export const Malformed = 1;\n',
  }, repo), /malformed|unparseable/i));
});

test('creates a missing trusted evidence directory before recording a patch and check', async () => {
  const definition = task();
  const { api, tools } = extensionApi();
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  const { repo } = await fixture(definition);
  await rm(join(repo, '.omp/ui-delivery/evidence'), { recursive: true });
  await withApproval(definition, async () => {
    await execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
      taskFile: '.omp/ui-delivery/tasks/task.json',
      patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
    }, repo);
    await execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo);
  });
  assert.match(await readFile(join(repo, '.omp/ui-delivery/evidence/task-17.jsonl'), 'utf8'), /ui_run_check/);
});

test('rejects an unsafe evidence directory before updating the candidate task', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-evidence-outside-'));
  await rm(join(repo, '.omp/ui-delivery/evidence'), { recursive: true });
  await symlink(outside, join(repo, '.omp/ui-delivery/evidence'));
  await withApproval(definition, () => assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_apply_patch'), {
    taskFile: '.omp/ui-delivery/tasks/task.json',
    patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n',
  }, repo), /symlink|evidence|policy/i));
  const persisted = JSON.parse(await readFile(join(repo, '.omp/ui-delivery/tasks/task.json'), 'utf8'));
  assert.equal(persisted.state, 'approved');
  assert.equal(persisted.candidate_hash, undefined);
});

test('fails closed on a durable pending patch journal', async () => {
  const definition = task();
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(definition);
  await writeFile(join(repo, '.omp/ui-delivery/evidence/repository.patch-pending.json'), '{"state":"pending"}');
  await withApproval(definition, async () => {
    for (const toolName of ['ui_delivery_status', 'ui_apply_patch']) {
      const args = toolName === 'ui_delivery_status'
        ? { taskFile: '.omp/ui-delivery/tasks/task.json' }
        : { taskFile: '.omp/ui-delivery/tasks/task.json', patch: 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n' };
      await assert.rejects(() => execute(tools.find((entry) => entry.name === toolName), args, repo), /recovery|pending/i);
    }
  });
  assert.equal(await readFile(join(repo, 'src/Card.tsx'), 'utf8'), 'export const Card = 1;\n');
});

test('blocks a second task when another task leaves repository patch recovery uncertain', async () => {
  const first = task();
  const second = task({ task_id: 'task-18' });
  const { api, tools } = extensionApi(); uiDeliveryPolicy(api);
  const { repo } = await fixture(first);
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task-18.json'), JSON.stringify(second));
  await writeFile(join(repo, '.omp/ui-delivery/evidence/repository.patch-pending.json'), JSON.stringify({ taskId: first.task_id, state: 'pending' }));
  await withApproval(second, () => assert.rejects(
    () => execute(tools.find((entry) => entry.name === 'ui_delivery_status'), { taskFile: '.omp/ui-delivery/tasks/task-18.json' }, repo),
    /recovery|pending/i,
  ));
});

test('patch atomically binds the candidate, preserves authorization, records evidence, and enables its check', async () => {
  const definition = task();
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  await withApproval(definition, async () => {
    const patch = 'diff --git a/src/Card.tsx b/src/Card.tsx\n--- a/src/Card.tsx\n+++ b/src/Card.tsx\n@@ -1 +1 @@\n-export const Card = 1;\n+export const Card = 2;\n';
    const applied = await execute(tools.find((entry) => entry.name === 'ui_apply_patch'), { taskFile: '.omp/ui-delivery/tasks/task.json', patch }, repo);
    assert.equal(applied.details.state, 'candidate_ready');
    assert.match(applied.details.candidateRevision, /^git:/);
    assert.match(applied.details.candidateHash, /^sha256:[a-f0-9]{64}$/);
    assert.equal(applied.details.authorizationDigest, digest(definition));
    const updated = JSON.parse(await readFile(join(repo, '.omp/ui-delivery/tasks/task.json'), 'utf8'));
    assert.equal(updated.state, 'candidate_ready');
    assert.equal(updated.candidate_hash, applied.details.candidateHash);
    assert.match(await readFile(join(repo, '.omp/ui-delivery/evidence', 'task-17.jsonl'), 'utf8'), /ui_apply_patch/);
    await execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo);
  });
});

test('rejects a wrong candidate hash before executing an approved check', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi(); let calls = 0;
  policyWithCheckRunner(api, async () => { calls += 1; return success(); });
  const { repo } = await fixture(definition);
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /candidate/i);
  assert.equal(calls, 0);
});

test('rejects a fresh zero-exit check result that reports skipped required checks', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 0, failed: 0, skipped: 1 }));
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /skipped|unverified/i);
});

test('rejects a zero-exit runner that leaves a pre-existing successful result unchanged', async () => {
  const definition = task({ state: 'candidate_ready', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
  policyWithCheckRunner(api, async () => success());
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_run_check'), { taskFile: '.omp/ui-delivery/tasks/task.json', checkId: 'unit' }, repo), /fresh|stale|result/i);
});

test('rejects capture when a successful check leaves its nonempty artifact unchanged', async () => {
  const definition = task({ state: 'reviewing', model_route: '@ui_review', candidate_revision: 'git:abc', candidate_hash: `sha256:${'0'.repeat(64)}` });
  const { api, tools } = extensionApi();
  const { repo } = await fixture(definition);
  await bindCandidate(repo, definition);
  policyWithCheckRunner(api, async () => {
    await writeFile(join(repo, '.ui-results/unit.json'), JSON.stringify({ schema: 'ui-delivery-check-v1', required: 1, passed: 1, failed: 0, skipped: 0 }));
    return success();
  });
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  await assert.rejects(() => execute(tools.find((entry) => entry.name === 'ui_capture'), { taskFile: '.omp/ui-delivery/tasks/task.json', recipeId: 'capture' }, repo), /stale|fresh|artifact/i);
});
