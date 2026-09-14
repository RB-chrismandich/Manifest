import assert from 'node:assert/strict';
import { mkdtemp, mkdir, realpath, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { authorizePath } from './paths.ts';

async function fixture() {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-paths-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await mkdir(join(repo, '.omp/ui-delivery/tasks'), { recursive: true });
  await mkdir(join(repo, '.git'), { recursive: true });
  await mkdir(join(repo, 'design-contract'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export {}');
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), '{}');
  await writeFile(join(repo, 'design-contract/baseline.json'), '{}');
  return { repo, task: { allowed_paths: ['src'], forbidden_policy_paths: ['design-contract/baseline.json'] } };
}

test('authorizes an existing path beneath an allowed task path', async () => {
  const { repo, task } = await fixture();
  assert.equal(await authorizePath({ repo, task, path: 'src/Card.tsx' }), await realpath(join(repo, 'src/Card.tsx')));
});

test('authorizes a new file when its existing ancestor is an allowed path', async () => {
  const { repo, task } = await fixture();
  assert.equal(await authorizePath({ repo, task, path: 'src/NewCard.tsx' }), join(await realpath(repo), 'src/NewCard.tsx'));
});

test('rejects traversal and sibling-prefix confusion outside allowed paths', async () => {
  const { repo, task } = await fixture();
  await assert.rejects(() => authorizePath({ repo, task, path: 'src/../package.json' }));
  await assert.rejects(() => authorizePath({ repo, task, path: 'src-evil/Card.tsx' }));
});

test('rejects noncanonical paths before protected-path comparison', async () => {
  const { repo, task } = await fixture();
  await assert.rejects(() => authorizePath({ repo, task, path: './design-contract/baseline.json' }), /invalid path/i);
});

test('rejects an allowed-looking path whose final symlink escapes the repository', async () => {
  const { repo, task } = await fixture();
  const outside = await mkdtemp(join(tmpdir(), 'ui-delivery-outside-'));
  await writeFile(join(outside, 'secret.txt'), 'secret');
  await symlink(join(outside, 'secret.txt'), join(repo, 'src/escape'));
  await assert.rejects(() => authorizePath({ repo, task, path: 'src/escape' }));
});

test('always rejects task, policy, git, and secret paths even when requested as allowed', async () => {
  const { repo } = await fixture();
  const task = { allowed_paths: ['.omp', '.git', 'design-contract', 'secrets'], forbidden_policy_paths: ['design-contract/baseline.json'] };
  for (const path of ['.omp/ui-delivery/tasks/task.json', '.git/config', 'design-contract/baseline.json', 'secrets/token.txt']) {
    await assert.rejects(() => authorizePath({ repo, task, path }));
  }
});
