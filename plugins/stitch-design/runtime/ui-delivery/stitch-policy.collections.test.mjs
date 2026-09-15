import assert from 'node:assert/strict';
import test from 'node:test';

import { createStitchPolicy, hashStitchInput } from './stitch-policy.ts';

const now = new Date('2026-09-14T00:00:00Z');
const projectId = 'project-17';
const registry = [
  'mcp__stitch_generate_screen_from_text',
  'mcp__stitch_generate_variants',
  'mcp__stitch_create_design_system_from_design_md',
  'mcp__stitch_get_screen',
  'mcp__stitch_list_screens',
  'mcp__stitch_list_design_systems',
].map((name) => ({
  name,
  sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' },
  parameters: { type: 'object' },
}));

function task(mutation, readbackTool) {
  return {
    state: 'approved',
    stitch_grant: {
      project_id: projectId,
      expires_at: '2030-01-01T00:00:00Z',
      mutations: [mutation],
      readback_tools: [readbackTool],
    },
  };
}

test('reconciles generated screens through a persisted learned identity and signed predictable fields', async () => {
  const generation = { projectId, prompt: 'Create a checkout screen' };
  const definition = task({
    tool_name: 'mcp__stitch_generate_screen_from_text',
    input_hash: hashStitchInput(generation),
    max_uses: 1,
    expected_readback: {
      tool_name: 'mcp__stitch_get_screen',
      predictable_fields: { title: 'Checkout' },
      resource_identity: 'screen',
    },
  }, 'mcp__stitch_get_screen');
  let saved;
  const persist = async (state) => {
    saved = structuredClone({ ...state, version: state.version + 1 });
    return saved;
  };
  const policy = createStitchPolicy({ task: definition, registry, now: () => now, persist });

  await policy.authorize({ projectId, toolName: 'mcp__stitch_generate_screen_from_text', input: generation, toolCallId: 'generate-1' });
  await policy.recordMutationResult({
    toolName: 'mcp__stitch_generate_screen_from_text',
    toolCallId: 'generate-1',
    succeeded: true,
    result: { projectId, screenId: 'screen-created' },
  });

  const restarted = createStitchPolicy({ task: definition, registry, now: () => now, state: saved, persist });
  await assert.rejects(
    () => restarted.authorize({ projectId, toolName: 'mcp__stitch_get_screen', input: { projectId, screenId: 'other-screen' }, toolCallId: 'wrong-input' }),
    /reconcil|authorized|identity/i,
  );
  await restarted.authorize({ projectId, toolName: 'mcp__stitch_get_screen', input: { projectId, screenId: 'screen-created' }, toolCallId: 'readback-1' });
  await assert.rejects(
    () => restarted.recordReadback({ projectId, toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screenId: 'other-screen', title: 'Checkout' } }),
    /reconcil/i,
  );
  await assert.rejects(
    () => restarted.recordReadback({ projectId, toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screenId: 'screen-created', title: 'Wrong title' } }),
    /reconcil/i,
  );
  await restarted.recordReadback({ projectId, toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screenId: 'screen-created', title: 'Checkout' } });
});

test('reconciles collection readbacks against one learned resource without input identity', async () => {
  const generation = { projectId, prompt: 'Create a checkout screen' };
  const definition = task({
    tool_name: 'mcp__stitch_generate_screen_from_text',
    input_hash: hashStitchInput(generation),
    max_uses: 1,
    expected_readback: {
      tool_name: 'mcp__stitch_list_screens',
      predictable_fields: { title: 'Checkout' },
      resource_identity: 'screen',
    },
  }, 'mcp__stitch_list_screens');
  const policy = createStitchPolicy({ task: definition, registry, now: () => now });

  await policy.authorize({ projectId, toolName: 'mcp__stitch_generate_screen_from_text', input: generation, toolCallId: 'generate-1' });
  await policy.recordMutationResult({
    toolName: 'mcp__stitch_generate_screen_from_text',
    toolCallId: 'generate-1',
    succeeded: true,
    result: { projectId, screenId: 'screen-created' },
  });
  await policy.authorize({ projectId, toolName: 'mcp__stitch_list_screens', input: { projectId }, toolCallId: 'readback-1' });
  await assert.rejects(
    () => policy.recordReadback({ projectId, toolName: 'mcp__stitch_list_screens', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screens: [{ screenId: 'other-screen', title: 'Checkout' }] } }),
    /reconcil/i,
  );
  await assert.rejects(
    () => policy.recordReadback({ projectId, toolName: 'mcp__stitch_list_screens', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screens: [{ screenId: 'screen-created', title: 'Checkout' }, { screenId: 'screen-created', title: 'Checkout' }] } }),
    /reconcil/i,
  );
  await assert.rejects(
    () => policy.recordReadback({ projectId, toolName: 'mcp__stitch_list_screens', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screens: [{ screenId: 'screen-created', title: 'Wrong title' }] } }),
    /reconcil/i,
  );
  await policy.recordReadback({ projectId, toolName: 'mcp__stitch_list_screens', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screens: [{ screenId: 'screen-created', title: 'Checkout' }] } });
});

test('reconciles learned design systems from collection readbacks', async () => {
  const upload = { projectId, designMd: '# Tokens' };
  const definition = task({
    tool_name: 'mcp__stitch_create_design_system_from_design_md',
    input_hash: hashStitchInput(upload),
    max_uses: 1,
    expected_readback: {
      tool_name: 'mcp__stitch_list_design_systems',
      predictable_fields: { name: 'Tokens' },
      resource_identity: 'design_system',
    },
  }, 'mcp__stitch_list_design_systems');
  const policy = createStitchPolicy({ task: definition, registry, now: () => now });

  await policy.authorize({ projectId, toolName: 'mcp__stitch_create_design_system_from_design_md', input: upload, toolCallId: 'create-1' });
  await policy.recordMutationResult({
    toolName: 'mcp__stitch_create_design_system_from_design_md',
    toolCallId: 'create-1',
    succeeded: true,
    result: { projectId, designSystemId: 'design-system-created' },
  });
  await policy.authorize({ projectId, toolName: 'mcp__stitch_list_design_systems', input: { projectId }, toolCallId: 'readback-1' });
  await policy.recordReadback({ projectId, toolName: 'mcp__stitch_list_design_systems', toolCallId: 'readback-1', reconciled: true, observation: { projectId, designSystems: [{ designSystemId: 'design-system-created', name: 'Tokens' }] } });
});

test('reconciles generated variants through their learned screen identity', async () => {
  const generation = { projectId, selectedScreenIds: ['screen-1'], prompt: 'Create variants' };
  const definition = task({
    tool_name: 'mcp__stitch_generate_variants',
    input_hash: hashStitchInput(generation),
    max_uses: 1,
    expected_readback: {
      tool_name: 'mcp__stitch_get_screen',
      predictable_fields: { title: 'Checkout variant' },
      resource_identity: 'screen',
    },
  }, 'mcp__stitch_get_screen');
  const policy = createStitchPolicy({ task: definition, registry, now: () => now });

  await policy.authorize({ projectId, toolName: 'mcp__stitch_generate_variants', input: generation, toolCallId: 'variants-1' });
  await policy.recordMutationResult({
    toolName: 'mcp__stitch_generate_variants',
    toolCallId: 'variants-1',
    succeeded: true,
    result: { projectId, screenId: 'screen-variant' },
  });
  await policy.authorize({ projectId, toolName: 'mcp__stitch_get_screen', input: { projectId, screenId: 'screen-variant' }, toolCallId: 'readback-1' });
  await policy.recordReadback({ projectId, toolName: 'mcp__stitch_get_screen', toolCallId: 'readback-1', reconciled: true, observation: { projectId, screenId: 'screen-variant', title: 'Checkout variant' } });
});
