import assert from 'node:assert/strict';
import test from 'node:test';

import { createStitchPolicy, hashStitchInput } from './stitch-policy.ts';

const now = new Date('2026-09-14T00:00:00Z');
const input = { screenId: 'screen-1', prompt: 'make the header compact' };
const inputHash = hashStitchInput(input);

function task(overrides = {}) {
  return {
    state: 'approved',
    stitch_grant: {
      project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: inputHash, max_uses: 1 }],
      readback_tools: ['mcp__stitch_get_screen'],
    },
    ...overrides,
  };
}

const registry = [
  'get_screen',
  'list_screens',
  'get_project',
  'list_projects',
  'list_design_systems',
  'read_url_content',
  'create_project',
  'generate_screen_from_text',
  'edit_screens',
  'generate_variants',
  'upload_design_md',
  'create_design_system_from_design_md',
  'update_design_system',
  'apply_design_system',
].map((name) => ({
  name: `mcp__stitch_${name}`,
  sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' },
  parameters: { type: 'object' },
}));

test('allows a registered read tool and the exact one-shot approved mutation', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  assert.equal(policy.classify('mcp__stitch_get_screen'), 'read');
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input });
});

test('allows account discovery and a one-shot input-bound project creation followed by readback', async () => {
  const creation = { title: 'Bounded project' };
  const policy = createStitchPolicy({
    task: task({
      stitch_grant: {
        expires_at: '2030-01-01T00:00:00Z',
        mutations: [{ tool_name: 'mcp__stitch_create_project', input_hash: hashStitchInput(creation), max_uses: 1 }],
        readback_tools: ['mcp__stitch_get_project'],
      },
    }),
    registry,
    now: () => now,
  });

  await policy.authorize({ toolName: 'mcp__stitch_list_projects', input: {} });
  await policy.authorize({ toolName: 'mcp__stitch_create_project', input: creation });
  await assert.rejects(() => policy.authorize({ toolName: 'mcp__stitch_create_project', input: creation }), /reconcil|consum/i);
  await policy.recordMutationResult({ toolName: 'mcp__stitch_create_project', projectId: 'project-created', succeeded: true });
  await policy.authorize({ projectId: 'project-created', toolName: 'mcp__stitch_get_project', input: { projectId: 'project-created' } });
  await policy.recordReadback({ projectId: 'project-created', toolName: 'mcp__stitch_get_project', reconciled: true });
  assert.equal(policy.state(), 'reconciled');
});

test('classifies every Stitch tool used by bundled design workflows and rejects unknown tools', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });

  for (const tool of ['get_screen', 'list_screens', 'get_project', 'list_projects', 'list_design_systems', 'read_url_content']) {
    assert.equal(policy.classify(`mcp__stitch_${tool}`), 'read');
  }
  for (const tool of ['create_project', 'generate_screen_from_text', 'edit_screens', 'generate_variants', 'upload_design_md', 'create_design_system_from_design_md', 'update_design_system', 'apply_design_system']) {
    assert.equal(policy.classify(`mcp__stitch_${tool}`), 'mutation');
  }
  assert.equal(policy.classify('mcp__stitch_unknown'), 'unknown');
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_unknown', input }));
});
test('denies unknown tools and schemas that do not establish a read or mutation classification', async () => {
  const policy = createStitchPolicy({
    task: task(),
    registry: [{ name: 'mcp__stitch_unknown', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: {} }],
    now: () => now,
  });
  assert.equal(policy.classify('mcp__stitch_unknown'), 'unknown');
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_unknown', input }));
});

test('denies missing, expired, wrong-project, and wrong-input mutation grants', async () => {
  for (const candidate of [
    task({ stitch_grant: undefined }),
    task({ stitch_grant: { ...task().stitch_grant, expires_at: '2020-01-01T00:00:00Z' } }),
    task({ stitch_grant: { ...task().stitch_grant, expires_at: 'not-a-date' } }),
  ]) {
    const policy = createStitchPolicy({ task: candidate, registry, now: () => now });
    await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input }));
  }
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await assert.rejects(() => policy.authorize({ projectId: 'other-project', toolName: 'mcp__stitch_generate_screen_from_text', input }));
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: { ...input, prompt: 'different' } }));
});
test('reconciles a failed entry without allowing its replay and permits a separately approved entry after restart', async () => {
  const first = { screenId: 'screen-1', prompt: 'make the header compact' };
  const second = { screenId: 'screen-2', prompt: 'add a footer' };
  const definition = task({
    stitch_grant: {
      ...task().stitch_grant,
      mutations: [
        { tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: hashStitchInput(first), max_uses: 1 },
        { tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: hashStitchInput(second), max_uses: 1 },
      ],
    },
  });
  let saved;
  const policy = createStitchPolicy({
    task: definition,
    registry,
    now: () => now,
    persist: async (state) => {
      saved = { ...state, entries: { ...state.entries }, version: state.version + 1 };
      return saved;
    },
  });

  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: first });
  await policy.recordDispatchFailed();
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: first }), /reconcil|consum/i);
  await assert.rejects(() => policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', reconciled: false }), /reconcil/i);
  await policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', reconciled: true });

  const restarted = createStitchPolicy({
    task: definition,
    registry,
    now: () => now,
    state: saved,
    persist: async (state) => {
      saved = { ...state, entries: { ...state.entries }, version: state.version + 1 };
      return saved;
    },
  });
  await restarted.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: second });
  await assert.rejects(() => restarted.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: second }), /reconcil|consum/i);
});

test('binds Stitch reads and readback reconciliation to the approved project', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {} });
  await assert.rejects(() => policy.authorize({ projectId: 'other-project', toolName: 'mcp__stitch_get_screen', input: {} }), /not authorized/i);
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input });
  await assert.rejects(() => policy.recordReadback({ projectId: 'other-project', toolName: 'mcp__stitch_get_screen', reconciled: true }), /reconcil/i);
  assert.equal(policy.state(), 'mutation_unknown');
  await policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', reconciled: true });
  assert.equal(policy.state(), 'reconciled');
});

test('checks mutation grant expiry against an injected clock at authorization time', async () => {
  let clock = new Date('2026-09-14T00:00:00Z');
  const policy = createStitchPolicy({
    task: task({ stitch_grant: { ...task().stitch_grant, expires_at: '2026-09-14T00:01:00Z' } }),
    registry,
    now: () => clock,
  });
  clock = new Date('2026-09-14T00:01:01Z');

  await assert.rejects(
    () => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input }),
    /not authorized/i,
  );
});
