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
      mutations: [{ tool_name: 'mcp__stitch__edit_screen', input_hash: inputHash, max_uses: 1 }],
      readback_tools: ['mcp__stitch__get_screen'],
    },
    ...overrides,
  };
}

const registry = [
  {
    name: 'mcp__stitch__get_screen',
    sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' },
    parameters: { type: 'object' },
  },
  {
    name: 'mcp__stitch__edit_screen',
    sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' },
    parameters: { type: 'object' },
  },
];

test('allows a registered read tool and the exact one-shot approved mutation', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  assert.equal(policy.classify('mcp__stitch__get_screen'), 'read');
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input });
});

test('denies unknown tools and schemas that do not establish a read or mutation classification', async () => {
  const policy = createStitchPolicy({
    task: task(),
    registry: [{ name: 'mcp__stitch__unknown', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: {} }],
    now: () => now,
  });
  assert.equal(policy.classify('mcp__stitch__unknown'), 'unknown');
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__unknown', input }));
});

test('denies missing, expired, wrong-project, and wrong-input mutation grants', async () => {
  for (const candidate of [
    task({ stitch_grant: undefined }),
    task({ stitch_grant: { ...task().stitch_grant, expires_at: '2020-01-01T00:00:00Z' } }),
  ]) {
    const policy = createStitchPolicy({ task: candidate, registry, now: () => now });
    await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input }));
  }
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await assert.rejects(() => policy.authorize({ projectId: 'other-project', toolName: 'mcp__stitch__edit_screen', input }));
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input: { ...input, prompt: 'different' } }));
});

test('blocks reuse and retries after an interrupted mutation until permitted readback reconciles it', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input });
  policy.recordDispatchInterrupted();
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input }));
  assert.throws(() => policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch__get_screen', reconciled: false }));
  policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch__get_screen', reconciled: true });
  assert.equal(policy.state(), 'reconciled');
});

test('does not automatically retry a failed mutation and permits no second use after successful readback', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input });
  policy.recordDispatchFailed(new Error('timeout'));
  policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch__get_screen', reconciled: true });
  await assert.rejects(() => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input }));
});

test('binds Stitch reads and readback reconciliation to the approved project', async () => {
  const policy = createStitchPolicy({ task: task(), registry, now: () => now });
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__get_screen', input: {} });
  await assert.rejects(
    () => policy.authorize({ projectId: 'other-project', toolName: 'mcp__stitch__get_screen', input: {} }),
    /not authorized/i,
  );
  await policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input });
  assert.throws(
    () => policy.recordReadback({ projectId: 'other-project', toolName: 'mcp__stitch__get_screen', reconciled: true }),
    /cannot reconcile/i,
  );
  assert.equal(policy.state(), 'mutation_unknown');
  policy.recordReadback({ projectId: 'project-17', toolName: 'mcp__stitch__get_screen', reconciled: true });
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
    () => policy.authorize({ projectId: 'project-17', toolName: 'mcp__stitch__edit_screen', input }),
    /not authorized/i,
  );
});
