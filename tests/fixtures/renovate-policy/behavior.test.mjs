// Integration contract with pinned Renovate internals, not a policy simulator.
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import http from 'node:http';
import net from 'node:net';

assert.equal(process.version, 'v24.11.1', 'Use the approved Node runtime');
const modules = resolve(process.env.RENOVATE_TEST_MODULES ?? resolve(dirname(process.execPath), '../..'));
const load = (path) => import(pathToFileURL(join(modules, 'renovate', path)));
const readJson = async (url) => JSON.parse(await readFile(url, 'utf8'));
const fixture = await readJson(new URL('./cases.json', import.meta.url));
const starter = await readJson(new URL(
  '../../../plugins/manifest-ops/skills/renovate-config/assets/renovate.json', import.meta.url,
));
assert.equal((await readJson(join(modules, 'renovate/package.json'))).version, '44.199.2');

// Clear credentials/configuration before loading any Renovate module. Nothing
// extracts a real repository or invokes a package manager or platform writer.
for (const key of Object.keys(process.env)) {
  if (key !== 'NODE_TEST_CONTEXT') delete process.env[key];
}
const sandbox = await mkdtemp(join(tmpdir(), 'renovate-policy-'));
process.env.HOME = sandbox;
process.env.XDG_CACHE_HOME = sandbox;
process.env.LOG_LEVEL = 'fatal';
process.chdir(sandbox);

const RealDate = Date;
globalThis.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [fixture.clock])); }
  static now() { return RealDate.parse(fixture.clock); }
};

// Deny outbound sockets even if a fixture accidentally introduces a live URL.
const deniedConnections = [];
let registryPort;
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const options = typeof first === 'object' ? first : { host: args[1] };
  const host = options.host ?? options.hostname;
  if (host !== '127.0.0.1' || !registryPort || Number(options.port) !== registryPort) {
    deniedConnections.push(host ?? 'unspecified');
    throw new Error('Only the fixture registry socket is permitted');
  }
  return connect.apply(this, args);
};

const { getConfig } = await load('dist/config/defaults.js');
const { mergeChildConfig } = await load('dist/config/utils.js');
const { validateConfig } = await load('dist/config/validation.js');
const { migrateConfig } = await load('dist/config/migration.js');
const { massageConfig } = await load('dist/config/massage.js');
const { resolveConfigPresets } = await load('dist/config/presets/index.js');
const { GlobalConfig } = await load('dist/config/global.js');
const { setPlatformApi } = await load('dist/modules/platform/index.js');
const { default: platformApis } = await load('dist/modules/platform/api.js');
const { platformScmImpls } = await load('dist/modules/platform/scm.js');
const { init: initLogger } = await load('dist/logger/index.js');
await initLogger();
const { processBranch } = await load('dist/workers/repository/update/branch/index.js');
const { setCount, isLimitReached } = await load('dist/workers/global/limits.js');
const { detectVulnerabilityAlerts } = await load('dist/workers/repository/init/vulnerability.js');
const { lookup: renovateLookup } = await load('dist/workers/repository/process/extract-update.js');
const { resetCache } = await load('dist/util/cache/repository/index.js');
const memory = await load('dist/util/cache/memory/index.js');
const hostRules = await load('dist/util/host-rules.js');
const requests = [];
const unexpected = [];
let origin;
const server = http.createServer((req, res) => {
  requests.push(req.url);
  res.setHeader('content-type', 'application/json');
  const name = req.url.split('/').filter(Boolean).filter((part) => part !== 'json').at(-1);
  const pkg = fixture.packages.find((item) => item.name === name);
  const presets = {
    '/inherited.json': fixture.inherited,
    '/shared.json': starter,
  };
  let body = presets[req.url];
  if (pkg && req.url.startsWith('/npm/')) {
    body = {
      name, 'dist-tags': { latest: pkg.version },
      versions: { '1.0.0': { version: '1.0.0' }, [pkg.version]: { version: pkg.version } },
      time: { '1.0.0': '2026-01-01T00:00:00.000Z', ...(pkg.timestamp ? { [pkg.version]: pkg.timestamp } : {}) },
    };
  }
  if (pkg && req.url.startsWith('/pypi/')) {
    body = {
      info: { name, version: pkg.version },
      releases: Object.fromEntries(['1.0.0', pkg.version].map((version) => [version, [{
        filename: `${name}-${version}.tar.gz`, url: `${origin}/unused.tar.gz`,
        upload_time: version === '1.0.0' ? '2026-01-01T00:00:00' : pkg.timestamp?.replace('.000Z', ''),
        yanked: false,
      }]])),
    };
  }
  if (!body) {
    unexpected.push(req.url);
    res.statusCode = 404;
    body = { error: 'Unexpected fixture request' };
  }
  res.end(JSON.stringify(body));
});

before(async () => {
  await new Promise((done, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', done);
  });
  registryPort = server.address().port;
  origin = `http://127.0.0.1:${registryPort}`;
  GlobalConfig.set({ platform: 'github', cacheDir: sandbox, localDir: sandbox });
  platformScmImpls.set('github', class { async branchExists() { return false; } });
  setPlatformApi('github');
  hostRules.add({ matchHost: origin, allowInternal: true });
});

after(async () => {
  await new Promise((done) => server.close(done));
  net.Socket.prototype.connect = connect;
  globalThis.Date = RealDate;
  process.chdir(tmpdir());
  await rm(sandbox, { recursive: true, force: true });
  assert.deepEqual(deniedConnections, [], 'No outbound network attempts allowed');
  assert.deepEqual(unexpected, [], 'All service responses must be controlled');
  assert.ok(requests.includes('/shared.json'), 'Shared preset was actually fetched');
  assert.ok(requests.includes('/inherited.json'), 'Inherited preset was actually fetched');
});

async function configFor({ shared = false, consumer = false, alerts = false, rules = [] } = {}) {
  resetCache();
  memory.reset();
  setCount('ConcurrentPRs', 0);
  setCount('Branches', 0);
  platformApis.set('github', {
    getVulnerabilityAlerts: async () => alerts ? structuredClone(fixture.alerts) : [],
    getBranchPr: async () => null, findPr: async () => null,
  });
  setPlatformApi('github');
  const input = shared
    ? { extends: [`${origin}/inherited.json`, `${origin}/shared.json`], ...(consumer ? fixture.consumer : {}) }
    : { ...starter, extends: [`${origin}/inherited.json`, ...starter.extends] };
  const resolved = await resolveConfigPresets(input);
  assert.deepEqual(resolved.errors ?? [], []);
  let config = mergeChildConfig(getConfig(), resolved.config);
  config = mergeChildConfig(config, {
    repository: 'fixture/isolated', baseBranch: 'main', defaultBranch: 'main',
    repoIsOnboarded: true, semanticCommits: 'disabled', errors: [], warnings: [],
    packageRules: [
      { matchDatasources: ['npm'], registryUrls: [`${origin}/npm/`] },
      { matchDatasources: ['pypi'], registryUrls: [`${origin}/pypi/`] },
      ...rules,
    ],
  });
  return detectVulnerabilityAlerts(config);
}

async function lookup(config, files) {
  const result = await renovateLookup(config, files);
  for (const managerFiles of Object.values(result.packageFiles)) {
    for (const file of managerFiles) {
      for (const dep of file.deps) {
        assert.deepEqual(dep.warnings ?? [], [], `Lookup failed for ${dep.depName}`);
      }
    }
  }
  return result;
}

function filesFor(names, manager = 'npm', currentValue = '1.0.0') {
  return { [manager]: [{
    packageFile: manager === 'npm' ? 'package.json' : 'requirements.txt',
    deps: names.map((depName) => ({
      depName, packageName: depName, currentValue, lockedVersion: '1.0.0',
      datasource: manager === 'npm' ? 'npm' : 'pypi',
      depType: manager === 'npm' ? 'dependencies' : 'requirements',
    })),
  }] };
}

test('six-day and missing timestamps held; exactly seven days eligible', async () => {
  const result = await lookup(await configFor(), filesFor(['six-day', 'seven-day', 'no-time']));
  assert.deepEqual(result.branches.flatMap((b) => b.upgrades.map((u) => u.depName)), ['seven-day']);
  assert.equal(result.branches[0].branchName, 'renovate/all');
});

test('eligible majors/minors/patches across npm and pip share one branch despite inherited groups', async () => {
  const result = await lookup(await configFor(), {
    ...filesFor(['major', 'minor']), ...filesFor(['patch'], 'pip_requirements'),
  });
  assert.equal(result.branches.length, 1);
  assert.equal(result.branches[0].branchName, 'renovate/all');
  assert.deepEqual(result.branches[0].upgrades.map((u) => u.updateType).sort(), ['major', 'minor', 'patch']);
  assert.deepEqual(new Set(result.branches[0].upgrades.map((u) => u.manager)), new Set(['npm', 'pip_requirements']));
});

test('shared preset restores inherited cooldown but later consumer rules can override it', async () => {
  const held = await lookup(await configFor({ shared: true }), filesFor(['six-day']));
  assert.equal(held.branches.length, 1);
  assert.equal(held.branches[0].pendingChecks, true);
  assert.equal((await processBranch(held.branches[0])).result, 'pending');
  const overridden = await lookup(await configFor({ shared: true, consumer: true }), filesFor(['six-day']));
  assert.equal(overridden.branches.length, 1);
  assert.equal(overridden.branches[0].branchName, 'renovate/consumer');
  assert.equal(overridden.branches[0].upgrades[0].minimumReleaseAge, '3 days');
});

test('one-hour-old security fix bypasses routine group and cap with manual merge', async () => {
  const result = await lookup(await configFor({ alerts: true }), filesFor(['urgent', 'minor']));
  assert.equal(result.branches.length, 2);
  const urgent = result.branches.find((b) => b.isVulnerabilityAlert);
  assert.ok(urgent);
  assert.notEqual(urgent.branchName, 'renovate/all');
  assert.equal(urgent.prConcurrentLimit, 0);
  setCount('ConcurrentPRs', 1);
  setCount('Branches', 1);
  assert.equal(isLimitReached('ConcurrentPRs', urgent), false);
  assert.equal(isLimitReached('Branches', urgent), false);
  assert.equal(isLimitReached('ConcurrentPRs', result.branches.find((b) => !b.isVulnerabilityAlert)), true);
  assert.equal(urgent.automerge, false);
  assert.equal(urgent.upgrades[0].newVersion, '1.0.1');
  assert.equal(result.branches.find((b) => !b.isVulnerabilityAlert).prConcurrentLimit, 1);
});

test('security fixes a locked range while its routine candidate is still too young', async () => {
  const routine = await lookup(await configFor(), filesFor(['urgent'], 'npm', '^1.0.0'));
  assert.equal(routine.branches[0].pendingChecks, true);
  assert.equal((await processBranch(routine.branches[0])).result, 'pending');
  const security = await lookup(await configFor({ alerts: true }), filesFor(['urgent'], 'npm', '^1.0.0'));
  assert.equal(security.branches.length, 1);
  assert.equal(security.branches[0].isVulnerabilityAlert, true);
  assert.equal(security.branches[0].automerge, false);
});

test('each held candidate reaches Renovate branch processing as pending', async () => {
  for (const name of ['six-day', 'no-time']) {
    const result = await lookup(await configFor(), filesFor([name]));
    assert.equal(result.branches.length, 1);
    assert.equal(result.branches[0].pendingChecks, true);
    const processed = await processBranch(result.branches[0]);
    assert.equal(processed.result, 'pending');
    assert.equal(processed.branchExists, false);
  }
});

test('eligible routine pin is disabled, while the same alert can fix a locked range', async () => {
  const options = { rules: [{ matchPackageNames: ['minor'], rangeStrategy: 'pin' }] };
  const routine = await lookup(await configFor(options), filesFor(['minor'], 'npm', '^1.0.0'));
  assert.equal(routine.branches.flatMap((b) => b.upgrades).some((u) => u.updateType === 'pin'), false);
  const control = await lookup(await configFor({ rules: [
    ...options.rules, { matchUpdateTypes: ['pin'], enabled: true },
  ] }), filesFor(['minor'], 'npm', '^1.0.0'));
  assert.equal(control.branches.flatMap((b) => b.upgrades).some((u) => u.updateType === 'pin'), true);
  const security = await lookup(await configFor({ alerts: true }), filesFor(['urgent'], 'npm', '^1.0.0'));
  assert.equal(security.branches[0].isVulnerabilityAlert, true);
  assert.equal(security.branches[0].upgrades[0].updateType, 'patch');
  assert.equal(security.branches[0].upgrades[0].isLockfileUpdate, true);
  assert.equal(security.branches[0].pendingChecks ?? false, false);
  assert.equal(security.branches[0].automerge, false);
});

test('an explicit routine patch disable still permits the approved security fix', async () => {
  const rules = [{ matchUpdateTypes: ['patch'], enabled: false }];
  const routine = await lookup(await configFor({ rules }), filesFor(['patch']));
  assert.equal(routine.branches.length, 0);
  const security = await lookup(await configFor({ rules, alerts: true }), filesFor(['urgent']));
  assert.equal(security.branches.length, 1);
  assert.equal(security.branches[0].isVulnerabilityAlert, true);
  assert.equal(security.branches[0].automerge, false);
});


test('resolved representative consumers pass strict validation even when they override policy', async () => {
  for (const consumer of [false, true]) {
    const input = {
      extends: [`${origin}/inherited.json`, `${origin}/shared.json`],
      ...(consumer ? fixture.consumer : {}),
    };
    const resolved = await resolveConfigPresets(input);
    const { isMigrated, migratedConfig } = migrateConfig(resolved.config);
    assert.equal(isMigrated, false, 'Strict validation rejects required migration');
    const checked = await validateConfig('repo', massageConfig(migratedConfig));
    assert.deepEqual(checked.errors, []);
    assert.deepEqual(checked.warnings, []);
  }
});
