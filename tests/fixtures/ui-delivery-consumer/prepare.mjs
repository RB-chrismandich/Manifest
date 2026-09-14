import { createHash } from 'node:crypto';
import { cp, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const fixtureRoot = resolve(dirname(fileURLToPath(import.meta.url)));
const requestedRoot = process.argv[2];
if (requestedRoot !== undefined && !isAbsolute(requestedRoot)) throw new Error('preparation root must be absolute');
if (requestedRoot) await mkdir(requestedRoot, { recursive: true });
const outputRoot = requestedRoot ? await mkdtemp(join(requestedRoot, 'ui-delivery-consumer-')) : await mkdtemp(join(tmpdir(), 'ui-delivery-consumer-'));

const canonical = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`;
  return JSON.stringify(value);
};
const qualificationHash = `sha256:${createHash('sha256').update('ui-delivery-consumer-qualification-v1').digest('hex')}`;
const authorizationDigest = (task) => {
  const projection = Object.fromEntries(['task_id', 'design_revision', 'qualification_hash', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant'].filter((key) => key in task).map((key) => [key, task[key]]));
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
    cp(join(fixtureRoot, 'verifiers'), join(repo, '.omp/ui-delivery/verifiers'), { recursive: true }),
    mkdir(join(repo, 'site'), { recursive: true }),
    mkdir(join(repo, '.omp/ui-delivery/tasks'), { recursive: true }),
    mkdir(join(repo, '.ui-results'), { recursive: true }),
  ]);
  const checkVerifier = '.omp/ui-delivery/verifiers/check-design.mjs';
  const captureVerifier = '.omp/ui-delivery/verifiers/capture-screen.py';
  const verifier = async (path) => ({
    path,
    sha256: `sha256:${createHash('sha256').update(await readFile(join(repo, path))).digest('hex')}`,
  });
  const [designVerifier, captureTrustedVerifier] = await Promise.all([
    verifier(checkVerifier),
    verifier(captureVerifier),
  ]);
  const checkResult = '.ui-results/design-check.result.json';
  const capturePng = '.ui-results/screen.png';
  const captureResult = '.ui-results/capture.result.json';
  await Promise.all([writeFile(join(repo, checkResult), ''), writeFile(join(repo, capturePng), ''), writeFile(join(repo, captureResult), '')]);
  const task = {
    task_id: `consumer-pilot-${definition.id}-v1`,
    state: 'approved',
    design_revision: `approved-${definition.id}-v1`,
    qualification_hash: qualificationHash,
    allowed_paths: ['site'],
    forbidden_policy_paths: ['.omp'],
    approved_check_recipes: [
      {
        id: 'design-contract',
        argv: ['node', join(repo, checkVerifier), join(repo, 'contracts', definition.contract), join(repo, definition.target)],
        cwd: '.', timeout_ms: 30000, backend: 'sandbox-exec', result_path: checkResult, write_paths: [checkResult], trusted_verifier: designVerifier,
      },
      {
        id: 'capture-screen',
        argv: ['/home/cptr/.venv/bin/python3', `/repo/${captureVerifier}`, '/usr/bin/chromium', `/repo/${definition.target}`],
        cwd: '.', timeout_ms: 30000, backend: 'docker', sandbox_image: 'ghcr.io/open-webui/computer@sha256:bbcf59b541dba201ca91084a1f7857ca617b94aa0f770b0fd2dd279e2e56a7ce', result_path: captureResult, write_paths: [capturePng, captureResult], trusted_verifier: captureTrustedVerifier,
      },
    ],
    capture_recipes: [{ id: 'screen-png', check_id: 'capture-screen', artifacts: [{ path: capturePng, type: 'image/png' }] }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
  };
  const taskPath = join(repo, '.omp/ui-delivery/tasks/task.json');
  await writeJson(taskPath, task);
  launches.push({
    id: definition.id, repo, task: taskPath, external_approval_sha256: authorizationDigest(task),
    active_qualification_sha256: qualificationHash,
    astra_model_route: 'openai-codex/gpt-6-astra:high', target: definition.target,
  });
}
process.stdout.write(`${JSON.stringify({ schema: 'ui-delivery-consumer-launch-v1', fixture_root: fixtureRoot, cases: launches })}\n`);
