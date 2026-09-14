import { createHash } from 'node:crypto';
import { cp, lstat, mkdir, mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const fixtureRoot = resolve(dirname(fileURLToPath(import.meta.url)));
const requestedRoot = process.argv[2];
if (requestedRoot !== undefined && !isAbsolute(requestedRoot)) throw new Error('preparation root must be absolute');
if (requestedRoot) await mkdir(requestedRoot, { recursive: true });
const outputRoot = requestedRoot ? await mkdtemp(join(requestedRoot, 'ui-delivery-consumer-')) : await mkdtemp(join(tmpdir(), 'ui-delivery-consumer-'));
const chromeCandidates = [
  process.env.UI_DELIVERY_CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
].filter((value) => typeof value === 'string' && value.length > 0);
let chromePath;
for (const candidate of chromeCandidates) {
  if (!isAbsolute(candidate)) continue;
  try {
    const stat = await lstat(candidate);
    if (stat.isFile() && !stat.isSymbolicLink()) { chromePath = await realpath(candidate); break; }
  } catch {}
}
if (!chromePath) throw new Error('an absolute Chrome executable is required');

const canonical = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`;
  return JSON.stringify(value);
};
const authorizationDigest = (task) => {
  const projection = Object.fromEntries(['task_id', 'design_revision', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant'].filter((key) => key in task).map((key) => [key, task[key]]));
  return `sha256:${createHash('sha256').update(canonical(projection)).digest('hex')}`;
};
const writeJson = (path, value) => writeFile(path, `${JSON.stringify(value)}\n`, 'utf8');

const cases = [
  { id: 'existing-screen', source: 'existing', contract: 'existing-screen.json', target: 'site/account.html' },
  { id: 'new-screen', source: 'new', contract: 'new-screen.json', target: 'site/welcome.html' },
];
const launches = [];
for (const definition of cases) {
  const repo = join(outputRoot, definition.id);
  await cp(join(fixtureRoot, 'cases', definition.source), repo, { recursive: true });
  await Promise.all([
    cp(join(fixtureRoot, 'contracts'), join(repo, 'contracts'), { recursive: true }),
    cp(join(fixtureRoot, 'programs'), join(repo, 'tools'), { recursive: true }),
    mkdir(join(repo, 'site'), { recursive: true }),
    mkdir(join(repo, '.omp/ui-delivery/tasks'), { recursive: true }),
    mkdir(join(repo, '.ui-results'), { recursive: true }),
  ]);
  const checkResult = '.ui-results/design-check.result.json';
  const capturePng = '.ui-results/screen.png';
  const captureResult = '.ui-results/capture.result.json';
  await Promise.all([writeFile(join(repo, checkResult), ''), writeFile(join(repo, capturePng), ''), writeFile(join(repo, captureResult), '')]);
  const task = {
    task_id: `consumer-pilot-${definition.id}-v1`,
    state: 'approved',
    design_revision: `approved-${definition.id}-v1`,
    allowed_paths: ['site'],
    forbidden_policy_paths: ['.omp'],
    approved_check_recipes: [
      {
        id: 'design-contract',
        argv: [process.execPath, join(repo, 'tools/check-design.mjs'), join(repo, 'contracts', definition.contract), join(repo, definition.target), join(repo, checkResult)],
        cwd: '.', timeout_ms: 30000, backend: 'sandbox-exec', result_path: checkResult, write_paths: [checkResult],
      },
      {
        id: 'capture-screen',
        argv: [process.execPath, join(repo, 'tools/capture-screen.mjs'), chromePath, join(repo, definition.target), join(repo, capturePng), join(repo, captureResult)],
        cwd: '.', timeout_ms: 30000, backend: 'sandbox-exec', result_path: captureResult, write_paths: [capturePng, captureResult],
      },
    ],
    capture_recipes: [{ id: 'screen-png', check_id: 'capture-screen', artifacts: [{ path: capturePng, type: 'image/png' }] }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
  };
  const taskPath = join(repo, '.omp/ui-delivery/tasks/task.json');
  await writeJson(taskPath, task);
  launches.push({
    id: definition.id, repo, task: taskPath, external_approval_sha256: authorizationDigest(task),
    astra_model_route: 'openai-codex/gpt-6-astra:high', target: definition.target,
  });
}
process.stdout.write(`${JSON.stringify({ schema: 'ui-delivery-consumer-launch-v1', fixture_root: fixtureRoot, cases: launches })}\n`);
