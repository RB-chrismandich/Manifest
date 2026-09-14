import assert from 'node:assert/strict';
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
