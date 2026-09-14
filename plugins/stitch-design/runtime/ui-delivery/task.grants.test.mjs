import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { loadTask } from './task.ts';

const SHA256 = (character) => `sha256:${character.repeat(64)}`;

function approvedTask(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    qualification_hash: SHA256('a'), allowed_paths: ['src/Card.tsx'],
    forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [{
      id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
      backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
      write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
      trusted_verifier: { path: '.omp/ui-delivery/verifiers/unit.mjs', sha256: SHA256('b') },
    }],
    capture_recipes: [{
      id: 'capture', check_id: 'unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }],
    }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
    ...overrides,
  };
}

async function taskFile(task) {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-grant-'));
  await mkdir(join(repo, 'src'), { recursive: true });
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  const path = join(repo, '.omp/ui-delivery/tasks/task-17.json');
  await mkdir(join(path, '..'), { recursive: true });
  await writeFile(path, JSON.stringify(task));
  return { repo, path };
}

function standardGrant(overrides = {}) {
  return {
    project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
    mutations: [{
      tool_name: 'mcp__stitch_edit_screens', input_hash: SHA256('c'), max_uses: 1,
      expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: SHA256('a') },
    }],
    readback_tools: ['mcp__stitch_get_screen'],
    ...overrides,
  };
}

async function expectRejectedGrant(stitch_grant, pattern) {
  const { repo, path } = await taskFile(approvedTask({ stitch_grant }));
  await assert.rejects(() => loadTask({ repo, taskFile: path }), pattern);
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

function authorizationDigest(task) {
  const projection = Object.fromEntries([
    'task_id', 'design_revision', 'qualification_hash', 'allowed_paths', 'forbidden_policy_paths',
    'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant', 'repair_authorization',
  ].filter((key) => key in task).map((key) => [key, task[key]]));
  return `sha256:${createHash('sha256').update(JSON.stringify(canonical(projection))).digest('hex')}`;
}

async function withApproval(task, operation) {
  const before = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  const activeBefore = process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = authorizationDigest(task);
  process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = task.qualification_hash;
  try { return await operation(); } finally {
    if (before === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = before;
    if (activeBefore === undefined) delete process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
    else process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = activeBefore;
  }
}

test('rejects malformed grant expiry even for status-facing task loads', async () => {
  const definition = approvedTask({ stitch_grant: { project_id: 'project-17', expires_at: 'not-a-date', mutations: [], readback_tools: [] } });
  const { repo, path } = await taskFile(definition);
  await assert.rejects(() => loadTask({ repo, taskFile: path }), /expiry|date|grant/i);
});

test('rejects normalized calendar dates while accepting a canonical leap-day grant expiry', async () => {
  for (const expires_at of ['2024-02-31T00:00:00Z', '2030-01-01T00:00:00+00:00']) {
    await expectRejectedGrant(standardGrant({ expires_at }), /expiry|date|grant/i);
  }
  const { repo, path } = await taskFile(approvedTask({ stitch_grant: standardGrant({ expires_at: '2024-02-29T00:00:00Z' }) }));
});

test('only Stitch mutation loads reject expired grants while local operations remain available', async () => {
  const stitch_grant = standardGrant({ expires_at: '2020-01-01T00:00:00Z' });
  const patch = approvedTask({ stitch_grant });
  const check = approvedTask({
    stitch_grant, state: 'candidate_ready', candidate_revision: 'git:abc',
    candidate_hash: SHA256('a'), outcome: 'unverified',
  });
  const capture = approvedTask({
    stitch_grant, state: 'reviewing', model_route: '@ui_review', candidate_revision: 'git:abc',
    candidate_hash: SHA256('a'), outcome: 'unverified',
  });
  for (const [definition, operation] of [[patch, 'patch'], [check, 'check'], [capture, 'capture']]) {
    const { repo, path } = await taskFile(definition);
    await withApproval(definition, () => loadTask({ repo, taskFile: path, operation }));
  }
  const { repo, path } = await taskFile(patch);
  await withApproval(patch, () => assert.rejects(
    () => loadTask({ repo, taskFile: path, mutation: true }),
    /Stitch grant expired/i,
  ));
});

test('rejects grants with tools outside the exact supported Stitch inventory', async () => {
  await expectRejectedGrant(standardGrant({
    mutations: [{
      tool_name: 'stitch.edit_screen', input_hash: 'sha256:input', max_uses: 1,
      expected_readback: { tool_name: 'stitch.get_screen', response_hash: SHA256('a') },
    }],
    readback_tools: ['stitch.get_screen'],
  }), /Stitch.*tool|grant/i);
});

test('rejects grants whose readback is ungranted, projectless, or noncanonical', async () => {
  const baseGrant = standardGrant();
  for (const stitch_grant of [
    standardGrant({ mutations: [{ ...baseGrant.mutations[0], expected_readback: { tool_name: 'mcp__stitch_get_project', response_hash: SHA256('a') } }] }),
    standardGrant({ readback_tools: ['mcp__stitch_list_projects'] }),
    standardGrant({ mutations: [{ ...baseGrant.mutations[0], input_hash: SHA256('C') }] }),
    standardGrant({ mutations: [{ ...baseGrant.mutations[0], expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: SHA256('A') } }] }),
    {
      expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_create_project', input_hash: SHA256('c'), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_project', predictable_fields: { projectTitle: 'Checkout' } } }],
      readback_tools: ['mcp__stitch_get_project'],
    },
  ]) await expectRejectedGrant(stitch_grant, /Stitch.*grant|readback/i);
});

test('accepts a predictable readback only with a resource identity', async () => {
  const stitch_grant = standardGrant({
    mutations: [{
      tool_name: 'mcp__stitch_edit_screens', input_hash: SHA256('c'), max_uses: 1,
      expected_readback: {
        tool_name: 'mcp__stitch_get_screen', predictable_fields: { title: 'Checkout' }, resource_identity: 'screen',
      },
    }],
  });
  const { repo, path } = await taskFile(approvedTask({ stitch_grant }));
  await loadTask({ repo, taskFile: path });
});

test('rejects duplicate mutation authorization keys despite different readback entries', async () => {
  const grant = standardGrant();
  await expectRejectedGrant(standardGrant({
    mutations: [
      grant.mutations[0],
      {
        ...grant.mutations[0],
        expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: SHA256('d') },
      },
    ],
  }), /duplicate.*mutation|grant/i);
});

test('rejects project-bound create grants', async () => {
  await expectRejectedGrant(standardGrant({
    mutations: [{
      tool_name: 'mcp__stitch_create_project', input_hash: SHA256('c'), max_uses: 1,
      expected_readback: {
        tool_name: 'mcp__stitch_get_project', predictable_fields: { title: 'Checkout' }, resource_identity: 'project',
      },
    }],
    readback_tools: ['mcp__stitch_get_project'],
  }), /project-bound create/i);
});
