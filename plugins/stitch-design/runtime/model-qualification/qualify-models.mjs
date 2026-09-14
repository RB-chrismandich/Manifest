#!/usr/bin/env node
import { createHash } from 'node:crypto';

const ROLE_NAMES = ['designer', 'ui_code', 'ui_review'];
const THINKING_LEVELS = new Set(['low', 'medium', 'high']);
const LOCAL_PROVIDERS = new Set(['ollama']);
const MIN_CONTEXT_WINDOW = 128000;
const MIN_MAX_TOKENS = 16000;

function usage() {
  return [
    'Usage: qualify-models.mjs --overlay <json> --catalog <json> --json [--local-only]',
    '',
    'Qualify explicit model-role selectors against a supplied model catalog.',
    'Required:',
    '  --overlay <json>   Model overlay JSON object',
    '  --catalog <json>   Model catalog JSON object',
    '  --json             Write the qualification report as JSON',
    'Optional:',
    '  --local-only       Permit only local providers and disable project MCP',
  ].join('\n');
}

function fail(field, reason) {
  throw new Error(`${field}: ${reason}`);
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseArgs(args) {
  if (args.includes('--help') || args.includes('-h')) {
    if (args.length === 1) return { help: true };
    fail('arguments', 'help cannot be combined with other flags');
  }

  const parsed = { localOnly: false, json: false };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--json') {
      if (parsed.json) fail('arguments', 'duplicate --json flag');
      parsed.json = true;
      continue;
    }
    if (arg === '--local-only') {
      if (parsed.localOnly) fail('arguments', 'duplicate --local-only flag');
      parsed.localOnly = true;
      continue;
    }
    if (arg === '--overlay' || arg === '--catalog') {
      const name = arg.slice(2);
      if (parsed[name] !== undefined) fail('arguments', `duplicate --${name} flag`);
      const value = args[index + 1];
      if (value === undefined || value.startsWith('--')) fail(`--${name}`, 'requires JSON input');
      parsed[name] = value;
      index += 1;
      continue;
    }
    fail('arguments', 'unknown flag or positional input');
  }

  for (const name of ['overlay', 'catalog']) {
    if (parsed[name] === undefined) fail(`--${name}`, 'is required');
  }
  if (!parsed.json) fail('--json', 'is required');
  return parsed;
}

function parseJson(input, field) {
  try {
    const value = JSON.parse(input);
    if (!isObject(value)) fail(field, 'must be a JSON object');
    return value;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith(`${field}:`)) throw error;
    fail(field, 'must contain valid JSON');
  }
}

function requireObject(value, field) {
  if (!isObject(value)) fail(field, 'must be an object');
  return value;
}

function requireString(value, field) {
  if (typeof value !== 'string' || value.length === 0) fail(field, 'must be a nonempty string');
  return value;
}

function requireStringArray(value, field) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || item.length === 0)) {
    fail(field, 'must be an array of nonempty strings');
  }
  return value;
}

function parseSelector(selector, field) {
  const value = requireString(selector, field);
  const separator = value.lastIndexOf(':');
  const suffix = separator === -1 ? undefined : value.slice(separator + 1);
  if (suffix !== undefined && THINKING_LEVELS.has(suffix)) {
    return { modelId: value.slice(0, separator), thinking: suffix };
  }
  return { modelId: value, thinking: undefined };
}

function validateOverlay(overlay) {
  const modelRoles = requireObject(overlay.modelRoles, 'overlay.modelRoles');
  const keys = Object.keys(modelRoles);
  for (const role of ROLE_NAMES) {
    if (!(role in modelRoles)) fail(`overlay.modelRoles.${role}`, 'is required');
  }
  if (keys.some((role) => !ROLE_NAMES.includes(role))) fail('overlay.modelRoles', 'contains an unsupported role');

  const roles = {};
  for (const role of ROLE_NAMES) roles[role] = parseSelector(modelRoles[role], `overlay.modelRoles.${role}`);

  const retry = requireObject(overlay.retry, 'overlay.retry');
  if (retry.modelFallback !== false) fail('overlay.retry.modelFallback', 'must be false; model fallback is not permitted');

  const enabledProviders = requireStringArray(overlay.enabledProviders, 'overlay.enabledProviders');
  if (enabledProviders.length === 0 || new Set(enabledProviders).size !== enabledProviders.length) {
    fail('overlay.enabledProviders', 'must contain a nonempty exact provider set without duplicates');
  }

  const mcp = requireObject(overlay.mcp, 'overlay.mcp');
  if (typeof mcp.enableProjectConfig !== 'boolean') fail('overlay.mcp.enableProjectConfig', 'must be boolean');

  return { roles, enabledProviders, enableProjectConfig: mcp.enableProjectConfig };
}

function validateCatalog(catalog) {
  if (!Array.isArray(catalog.models) || catalog.models.length === 0) fail('catalog.models', 'must be a nonempty array');
  const models = new Map();
  for (let index = 0; index < catalog.models.length; index += 1) {
    const model = requireObject(catalog.models[index], `catalog.models[${index}]`);
    const id = requireString(model.id, `catalog.models[${index}].id`);
    if (models.has(id)) fail('catalog.models', 'contains duplicate model identifiers');
    const provider = requireString(model.provider, `catalog.models[${index}].provider`);
    const modalities = requireStringArray(model.modalities, `catalog.models[${index}].modalities`);
    const thinkingLevels = requireStringArray(model.thinkingLevels, `catalog.models[${index}].thinkingLevels`);
    if (!Number.isInteger(model.contextWindow) || model.contextWindow < 0) fail(`catalog.models[${index}].contextWindow`, 'must be a nonnegative integer');
    if (!Number.isInteger(model.maxTokens) || model.maxTokens < 0) fail(`catalog.models[${index}].maxTokens`, 'must be a nonnegative integer');
    models.set(id, { id, provider, modalities: [...modalities].sort(), contextWindow: model.contextWindow, maxTokens: model.maxTokens, thinkingLevels: [...thinkingLevels].sort() });
  }
  return models;
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (isObject(value)) {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return value;
}

function qualify(overlay, catalog, localOnly) {
  const configuration = validateOverlay(overlay);
  const models = validateCatalog(catalog);
  const selectedProviders = new Set();
  const capabilities = {};

  for (const role of ROLE_NAMES) {
    const selector = configuration.roles[role];
    if (!selector.thinking) fail(`overlay.modelRoles.${role}`, 'must end with a configured thinking level');
    const model = models.get(selector.modelId);
    if (!model) fail(`overlay.modelRoles.${role}`, 'references a catalog model that is missing');
    if (!model.thinkingLevels.includes(selector.thinking)) fail(`overlay.modelRoles.${role}`, `requires ${selector.thinking} thinking support`);
    if (model.contextWindow < MIN_CONTEXT_WINDOW) fail(`catalog model for ${role}`, 'context window is below the qualification floor');
    if (model.maxTokens < MIN_MAX_TOKENS) fail(`catalog model for ${role}`, 'max tokens are below the qualification floor');
    if (role === 'designer' && !model.modalities.includes('image')) fail(`catalog model for ${role}`, 'image modality is required');
    if (localOnly && !LOCAL_PROVIDERS.has(model.provider)) fail(`overlay.modelRoles.${role}`, 'cloud provider is not permitted in local-only mode');
    selectedProviders.add(model.provider);
    capabilities[role] = {
      id: model.id,
      provider: model.provider,
      modalities: model.modalities,
      contextWindow: model.contextWindow,
      maxTokens: model.maxTokens,
      thinkingLevel: selector.thinking,
    };
  }

  const configuredProviders = new Set(configuration.enabledProviders);
  if (configuredProviders.size !== selectedProviders.size || [...configuredProviders].some((provider) => !selectedProviders.has(provider))) {
    fail('overlay.enabledProviders', 'must exactly match the providers selected by model roles');
  }
  if (localOnly && configuration.enableProjectConfig) fail('overlay.mcp.enableProjectConfig', 'must be false in local-only mode because Stitch project configuration is not permitted');

  const roles = Object.fromEntries(ROLE_NAMES.map((role) => [role, overlay.modelRoles[role]]));
  const report = { roles, capabilities };
  const canonicalReport = JSON.stringify(canonicalize(report));
  return { ...report, qualificationHash: `sha256:${createHash('sha256').update(canonicalReport).digest('hex')}` };
}

try {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
  } else {
    const report = qualify(parseJson(args.overlay, '--overlay'), parseJson(args.catalog, '--catalog'), args.localOnly);
    process.stdout.write(`${JSON.stringify(report)}\n`);
  }
} catch (error) {
  process.stderr.write(`qualify-models: ${error instanceof Error ? error.message : 'qualification failed'}\n`);
  process.exitCode = 1;
}
