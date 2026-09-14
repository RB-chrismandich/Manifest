import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const cli = new URL('./qualify-models.mjs', import.meta.url).pathname;
const astraExample = new URL('./astra.example.json', import.meta.url).pathname;
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

function model(overrides = {}) {
  return {
    provider: 'openai-codex',
    id: 'gpt-6-astra',
    selector: 'openai-codex/gpt-6-astra',
    input: ['text', 'image'],
    contextWindow: 128000,
    maxTokens: 16000,
    thinking: ['low', 'medium', 'high', 'xhigh', 'max'],
    ...overrides,
  };
}

function catalog(models = [model(), model({
  provider: 'ollama', selector: 'ollama/gpt-6-astra', input: ['text'], thinking: [],
})]) {
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

test('ignores incomplete capabilities on catalog entries unrelated to selected selectors', async () => {
  const candidateCatalog = catalog([
    model(),
    {
      provider: 'openai-codex',
      id: 'text-only',
      selector: 'openai-codex/text-only',
      input: [],
      contextWindow: 8192,
      maxTokens: 1024,
      thinking: null,
    },
    {
      provider: 'ollama',
      id: 'unlisted',
      selector: 'ollama/unlisted',
      thinking: null,
    },
  ]);
  const result = await invoke(qualificationArgs(overlay(), candidateCatalog));
  assert.equal(result.status, 0, failureText(result));
  assert.deepEqual(JSON.parse(result.stdout).roles, overlay().modelRoles);
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
    models: [{
      thinking: ['low', 'medium', 'high', 'xhigh', 'max'], maxTokens: 16000, contextWindow: 128000,
      input: ['text', 'image'], selector: 'openai-codex/gpt-6-astra', id: 'gpt-6-astra', provider: 'openai-codex',
    }, {
      thinking: [], input: ['text'], selector: 'ollama/gpt-6-astra', id: 'gpt-6-astra', provider: 'ollama',
      maxTokens: 16000, contextWindow: 128000,
    }],
  };
  const second = await invoke(qualificationArgs(reorderedOverlay, reorderedCatalog));
  assert.equal(first.status, 0, failureText(first));
  assert.equal(second.status, 0, failureText(second));
  assert.equal(JSON.parse(first.stdout).qualificationHash, JSON.parse(second.stdout).qualificationHash);
});

test('rejects missing role, exact selector, image, thinking, and context requirements', async () => {
  const textOnly = model({ id: 'text-only', selector: 'openai-codex/text-only', input: ['text'] });
  const cases = [
    ['missing designer role', overlay({ modelRoles: { ui_code: 'openai-codex/gpt-6-astra:medium', ui_review: 'openai-codex/gpt-6-astra:high' } }), catalog(), /designer/i],
    ['missing exact selector', overlay({ modelRoles: { designer: 'openai-codex/missing:high', ui_code: 'openai-codex/missing:medium', ui_review: 'openai-codex/missing:high' } }), catalog(), /selector.*missing|missing.*selector/i],
    ['designer image input', overlay({ modelRoles: { ...overlay().modelRoles, designer: 'openai-codex/text-only:high' } }), catalog([model(), textOnly]), /designer.*image|image.*designer/i],
    ['ui review image input', overlay({ modelRoles: { ...overlay().modelRoles, ui_review: 'openai-codex/text-only:high' } }), catalog([model(), textOnly]), /ui.?review.*image|image.*ui.?review/i],
    ['missing configured thinking suffix', overlay(), catalog([model({ thinking: ['low', 'medium'] })]), /high.*thinking|thinking.*high/i],
    ['insufficient context window', overlay(), catalog([model({ contextWindow: 127999 })]), /context/i],
  ];
  for (const [, candidateOverlay, candidateCatalog, reason] of cases) {
    await expectFailure(qualificationArgs(candidateOverlay, candidateCatalog), reason);
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

test('accepts xhigh and max thinking suffixes listed by the exact selector', async () => {
  const qualified = overlay({
    modelRoles: {
      designer: 'openai-codex/gpt-6-astra:xhigh',
      ui_code: 'openai-codex/gpt-6-astra:max',
      ui_review: 'openai-codex/gpt-6-astra:xhigh',
    },
  });
  const result = await invoke(qualificationArgs(qualified));
  assert.equal(result.status, 0, failureText(result));
  assert.deepEqual(JSON.parse(result.stdout).roles, qualified.modelRoles);
});

test('accepts the shipped Astra overlay and a catalog passed by file path', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'qualify-models-catalog-'));
  const catalogFile = join(directory, 'catalog.json');
  try {
    await writeFile(catalogFile, JSON.stringify(catalog()));
    const result = await invoke(['--overlay', astraExample, '--catalog', catalogFile, '--json']);
    assert.equal(result.status, 0, failureText(result));
    assert.deepEqual(JSON.parse(result.stdout).roles, {
      designer: 'openai-codex/gpt-6-astra:high',
      ui_code: 'openai-codex/gpt-6-astra:high',
      ui_review: 'openai-codex/gpt-6-astra:high',
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test('local-only mode rejects cloud selectors and Stitch project configuration', async () => {
  await expectFailure(qualificationArgs(overlay(), catalog(), ['--local-only']), /local-only|cloud|provider/i);
  const localOverlay = overlay({
    modelRoles: { designer: 'ollama/vision:high', ui_code: 'ollama/vision:medium', ui_review: 'ollama/vision:high' },
    enabledProviders: ['ollama'],
    mcp: { enableProjectConfig: true },
  });
  const localCatalog = catalog([model({ id: 'vision', selector: 'ollama/vision', provider: 'ollama' })]);
  await expectFailure(qualificationArgs(localOverlay, localCatalog, ['--local-only']), /enableProjectConfig|stitch|local-only/i);
});

test('qualifies each allowed local provider without cloud fallback', async () => {
  for (const provider of ['ollama', 'lmstudio', 'llamacpp']) {
    const localOverlay = overlay({
      modelRoles: {
        designer: `${provider}/vision:high`,
        ui_code: `${provider}/vision:medium`,
        ui_review: `${provider}/vision:high`,
      },
      enabledProviders: [provider],
      mcp: { enableProjectConfig: false },
    });
    const localCatalog = catalog([model({ id: 'vision', selector: `${provider}/vision`, provider })]);
    const result = await invoke(qualificationArgs(localOverlay, localCatalog, ['--local-only']));
    assert.equal(result.status, 0, failureText(result));
    const report = JSON.parse(result.stdout);
    assert.deepEqual(report.roles, localOverlay.modelRoles);
    assert.match(report.qualificationHash, /^sha256:[a-f0-9]{64}$/);
  }
});
