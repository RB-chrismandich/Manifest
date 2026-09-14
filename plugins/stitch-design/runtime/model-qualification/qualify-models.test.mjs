import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const cli = new URL('./qualify-models.mjs', import.meta.url).pathname;
const secret = 'sk-qualification-test-secret-9Kp3Vb7Lm2Qa';

function overlay(overrides = {}) {
  return {
    modelRoles: {
      designer: 'openai-codex/gpt-6-astra:high',
      ui_code: 'openai-codex/gpt-6-astra:medium',
      ui_review: 'openai-codex/gpt-6-astra:high',
    },
    retry: { modelFallback: false },
    enabledProviders: ['openai-codex'],
    mcp: { enableProjectConfig: true },
    ...overrides,
  };
}

function catalog(models = [
  {
    id: 'openai-codex/gpt-6-astra',
    provider: 'openai-codex',
    modalities: ['text', 'image'],
    contextWindow: 128000,
    maxTokens: 16000,
    thinkingLevels: ['low', 'medium', 'high'],
  },
]) {
  return { models };
}

async function invoke(args = []) {
  const home = await mkdtemp(join(tmpdir(), 'qualify-models-home-'));
  try {
    const result = spawnSync(process.execPath, [cli, ...args], {
      encoding: 'utf8',
      env: { ...process.env, HOME: home, XDG_CONFIG_HOME: join(home, '.config'), XDG_STATE_HOME: join(home, '.state') },
    });
    return { status: result.status, stdout: result.stdout ?? '', stderr: result.stderr ?? '' };
  } finally {
    await rm(home, { recursive: true, force: true });
  }
}

function qualificationArgs(candidateOverlay = overlay(), candidateCatalog = catalog(), extra = []) {
  return ['--overlay', JSON.stringify(candidateOverlay), '--catalog', JSON.stringify(candidateCatalog), '--json', ...extra];
}

function failureText(result) {
  return `${result.stdout}\n${result.stderr}`;
}

async function expectFailure(args, reason) {
  const result = await invoke(args);
  assert.notEqual(result.status, 0, failureText(result));
  assert.match(failureText(result), reason);
}

test('prints help from an empty HOME before reading config or state', async () => {
  const result = await invoke(['--help']);
  assert.equal(result.status, 0, failureText(result));
  assert.match(result.stdout, /usage/i);
  assert.ok(result.stdout.trim().split('\n').length <= 15, result.stdout);
  assert.equal(result.stderr, '');
});

test('qualifies exact Astra selectors and reports their catalog capabilities', async () => {
  const result = await invoke(qualificationArgs());
  assert.equal(result.status, 0, failureText(result));
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.roles, overlay().modelRoles);
  assert.match(report.qualificationHash, /^sha256:[a-f0-9]{64}$/);
  assert.match(JSON.stringify(report.capabilities), /"contextWindow":128000/);
  assert.match(JSON.stringify(report.capabilities), /"maxTokens":16000/);
  assert.doesNotMatch(failureText(result), /sk-[A-Za-z0-9-]{20,}/);
});

test('produces the same qualification hash for equivalent JSON key orderings', async () => {
  const first = await invoke(qualificationArgs());
  const reorderedOverlay = {
    mcp: { enableProjectConfig: true },
    enabledProviders: ['openai-codex'],
    retry: { modelFallback: false },
    modelRoles: { ui_review: 'openai-codex/gpt-6-astra:high', ui_code: 'openai-codex/gpt-6-astra:medium', designer: 'openai-codex/gpt-6-astra:high' },
  };
  const reorderedCatalog = {
    models: [{ thinkingLevels: ['low', 'medium', 'high'], maxTokens: 16000, contextWindow: 128000, modalities: ['text', 'image'], provider: 'openai-codex', id: 'openai-codex/gpt-6-astra' }],
  };
  const second = await invoke(qualificationArgs(reorderedOverlay, reorderedCatalog));
  assert.equal(first.status, 0, failureText(first));
  assert.equal(second.status, 0, failureText(second));
  assert.equal(JSON.parse(first.stdout).qualificationHash, JSON.parse(second.stdout).qualificationHash);
});

test('rejects missing role, model, image, thinking, and context requirements', async () => {
  const cases = [
    ['missing designer role', overlay({ modelRoles: { ui_code: 'openai-codex/gpt-6-astra:medium', ui_review: 'openai-codex/gpt-6-astra:high' } }), catalog(), /designer/i],
    ['missing catalog model', overlay({ modelRoles: { designer: 'openai-codex/missing:high', ui_code: 'openai-codex/missing:medium', ui_review: 'openai-codex/missing:high' } }), catalog(), /model.*missing|missing.*model/i],
    ['missing image modality', overlay(), catalog([{ ...catalog().models[0], modalities: ['text'] }]), /designer.*image|image.*designer/i],
    ['missing configured thinking suffix', overlay(), catalog([{ ...catalog().models[0], thinkingLevels: ['low', 'medium'] }]), /high.*thinking|thinking.*high/i],
    ['insufficient context window', overlay(), catalog([{ ...catalog().models[0], contextWindow: 127999 }]), /context/i],
  ];
  for (const [name, candidateOverlay, candidateCatalog, reason] of cases) {
    await expectFailure(qualificationArgs(candidateOverlay, candidateCatalog), reason, name);
  }
});

test('rejects enabled model fallback and provider constraints that drift from selectors', async () => {
  await expectFailure(qualificationArgs(overlay({ retry: { modelFallback: true } })), /modelFallback|fallback/i);
  await expectFailure(qualificationArgs(overlay({ enabledProviders: ['openai-codex', 'ollama'] })), /enabledProviders|provider/i);
});

test('never echoes secret-shaped overlay input on a qualification failure', async () => {
  const result = await invoke(qualificationArgs(overlay({ credential: secret, retry: { modelFallback: true } })));
  assert.notEqual(result.status, 0, failureText(result));
  assert.match(failureText(result), /fallback/i);
  assert.doesNotMatch(failureText(result), new RegExp(secret));
});

test('local-only mode rejects cloud selectors and Stitch project configuration', async () => {
  await expectFailure(qualificationArgs(overlay(), catalog(), ['--local-only']), /local-only|cloud|provider/i);
  const localOverlay = overlay({
    modelRoles: { designer: 'ollama/vision:high', ui_code: 'ollama/vision:medium', ui_review: 'ollama/vision:high' },
    enabledProviders: ['ollama'],
    mcp: { enableProjectConfig: true },
  });
  const localCatalog = catalog([{ ...catalog().models[0], id: 'ollama/vision', provider: 'ollama' }]);
  await expectFailure(qualificationArgs(localOverlay, localCatalog, ['--local-only']), /enableProjectConfig|stitch|local-only/i);
});

test('qualifies a complete local-only overlay without cloud fallback', async () => {
  const localOverlay = overlay({
    modelRoles: { designer: 'ollama/vision:high', ui_code: 'ollama/vision:medium', ui_review: 'ollama/vision:high' },
    enabledProviders: ['ollama'],
    mcp: { enableProjectConfig: false },
  });
  const localCatalog = catalog([{ ...catalog().models[0], id: 'ollama/vision', provider: 'ollama' }]);
  const result = await invoke(qualificationArgs(localOverlay, localCatalog, ['--local-only']));
  assert.equal(result.status, 0, failureText(result));
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.roles, localOverlay.modelRoles);
  assert.match(report.qualificationHash, /^sha256:[a-f0-9]{64}$/);
});
