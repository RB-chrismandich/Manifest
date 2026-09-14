import assert from 'node:assert/strict';
import test from 'node:test';

import { createStitchPolicy, hashStitchInput } from './stitch-policy.ts';

const now = new Date('2026-09-14T00:00:00Z');
const input = { screenId: 'screen-1', prompt: 'make the header compact' };
const inputHash = hashStitchInput(input);
const readback = { screen: { id: 'screen-1' } };

function task(overrides = {}) {
  return {
    state: 'approved',
    stitch_grant: {
      project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: inputHash, max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: hashStitchInput(readback) } }],
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
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'mutation-1' });
});

test('binds approved mutations to the project discovered by create-project readback without changing the grant', async () => {
  const creation = { title: 'Bounded project' };
  const generation = { projectId: 'project-created', prompt: 'Create the home screen' };
  const definition = task({
    stitch_grant: {
      expires_at: '2030-01-01T00:00:00Z',
      mutations: [
        { tool_name: 'mcp__stitch_create_project', input_hash: hashStitchInput(creation), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_project', response_hash: hashStitchInput({ projectId: 'project-created' }) } },
        { tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: hashStitchInput(generation), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: hashStitchInput({ screen: { id: 'screen-created' } }) } },
      ],
      readback_tools: ['mcp__stitch_get_project', 'mcp__stitch_get_screen'],
    },
  });
  const policy = createStitchPolicy({ task: definition, registry, now: () => now });

  await policy.authorize({ toolName: 'mcp__stitch_list_projects', input: {}, toolCallId: 'discovery-1' });
  await policy.authorize({ toolName: 'mcp__stitch_create_project', input: creation, toolCallId: 'create-1' });
  await assert.rejects(() => policy.authorize({ toolName: 'mcp__stitch_create_project', input: creation, toolCallId: 'create-2' }), /reconcil|consum/i);
  await policy.recordMutationResult({ toolName: 'mcp__stitch_create_project', toolCallId: 'create-1', projectId: 'project-created', succeeded: true });
  await policy.authorize({ projectId: 'project-created', toolName: 'mcp__stitch_get_project', input: { projectId: 'project-created' }, toolCallId: 'readback-1' });
  await policy.recordReadback({ projectId: 'project-created', toolName: 'mcp__stitch_get_project', toolCallId: 'readback-1', reconciled: true, observation: { projectId: 'project-created' } });
  await policy.authorize({ projectId: 'project-created', toolName: 'mcp__stitch_generate_screen_from_text', input: generation, toolCallId: 'generate-1' });
  assert.equal(definition.stitch_grant.project_id, undefined);
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

test('allows the URL-based read without project identity but keeps scoped reads project-bound', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });

  await policy.authorize({ toolName: 'mcp__stitch_read_url_content', input: { url: 'https://example.test/screen.html' }, toolCallId: 'url-read-1' });
  await assert.rejects(
    () => policy.authorize({ toolName: 'mcp__stitch_get_screen', input: { screenId: 'screen-1' }, toolCallId: 'scoped-read-1' }),
    /not authorized/i,
  );
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
        { tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: hashStitchInput(first), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: hashStitchInput(readback) } },
        { tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: hashStitchInput(second), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: hashStitchInput(readback) } },
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

  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: first, toolCallId: 'mutation-1' });
  await policy.recordDispatchFailed({ toolCallId: 'mutation-1' });
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: first, toolCallId: 'mutation-2' }), /reconcil|consum/i);
  await assert.rejects(() => policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: false, observation: readback }), /reconcil/i);
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'readback-1' });
  await policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: readback });

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
  await restarted.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: second, toolCallId: 'mutation-2' });
  await assert.rejects(() => restarted.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input: second, toolCallId: 'mutation-3' }), /reconcil|consum/i);
});

test('binds Stitch reads and readback reconciliation to the approved project', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'before-mutation' });
  await assert.rejects(() => policy.authorize({ projectId: 'other-project', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'wrong-project' }), /not authorized/i);
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'mutation-1' });
  await policy.recordMutationResult({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'mutation-1', succeeded: true });
  await assert.rejects(() => policy.recordReadback({ projectId: 'other-project', toolName: 'mcp__stitch_get_screen', toolCallId: 'before-mutation', reconciled: true, observation: readback }), /reconcil/i);
  assert.equal(policy.state(), 'mutation_unknown');
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'readback-1' });
  await policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: readback });
  assert.equal(policy.state(), 'reconciled');
});
test('only the exact read dispatched after the matching mutation result can reconcile', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'stale-read' });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'mutation-1' });
  await policy.recordMutationResult({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'mutation-1', succeeded: true });
  await assert.rejects(
    () => policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'stale-read', reconciled: true, observation: readback }),
    /reconcil/i,
  );
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'readback-1' });
  await assert.rejects(
    () => policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'other-read', reconciled: true, observation: readback }),
    /reconcil/i,
  );
  await policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: readback });
  assert.equal(policy.state(), 'reconciled');
});
test('reconciles only a readback whose observed payload matches the grant-bound digest', async () => {
  const expected = { screen: { id: 'screen-1', title: 'Compact header' } };
  const definition = task({
    stitch_grant: {
      ...task().stitch_grant,
      mutations: [{
        ...task().stitch_grant.mutations[0],
        expected_readback: {
          tool_name: 'mcp__stitch_get_screen',
          response_hash: hashStitchInput(expected),
        },
      }],
    },
  });
  const policy = createStitchPolicy({ task: definition, registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_generate_screen_from_text', input, toolCallId: 'mutation-1' });
  await policy.recordMutationResult({ toolName: 'mcp__stitch_generate_screen_from_text', toolCallId: 'mutation-1', succeeded: true });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', input: {}, toolCallId: 'readback-1' });
  await assert.rejects(
    () => policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: { screen: { id: 'screen-1', title: 'Stale header' } } }),
    /reconcil/i,
  );
  assert.equal(policy.state(), 'mutation_unknown');
  await policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: expected });
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
