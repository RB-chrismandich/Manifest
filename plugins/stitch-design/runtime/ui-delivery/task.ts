import { createHash } from 'node:crypto';
import { lstat, readdir, readFile, realpath } from 'node:fs/promises';
import { join, relative, resolve, sep } from 'node:path';
import { canonicalJsonHash } from './evidence.ts';

export type DeliveryTask = Record<string, any>;

function within(root: string, candidate: string): boolean {
  const rel = relative(root, candidate);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !rel.includes(`${sep}..${sep}`));
}
function invalid(message: string): never { throw new Error(`Invalid UI delivery task: ${message}`); }
function nonEmptyStrings(value: unknown): value is string[] { return Array.isArray(value) && value.length > 0 && value.every((entry) => typeof entry === 'string' && entry.length > 0); }
function relativePath(value: unknown): value is string { return typeof value === 'string' && value.length > 0 && !/\s/.test(value) && !value.startsWith('/') && !value.split(/[\\/]/).includes('..'); }

export function authorizationDigest(task: DeliveryTask): string {
  const projection = Object.fromEntries(['task_id', 'design_revision', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant', 'repair_authorization'].filter((key) => key in task).map((key) => [key, task[key]]));
  return canonicalJsonHash(projection);
}

function validate(task: unknown): asserts task is DeliveryTask {
  if (!task || typeof task !== 'object' || Array.isArray(task)) invalid('must be an object');
  const value = task as DeliveryTask;
  for (const key of ['task_id', 'state', 'design_revision', 'model_route', 'outcome']) if (typeof value[key] !== 'string' || !value[key]) invalid(`missing ${key}`);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value.task_id)) invalid('invalid task_id');
  if (!nonEmptyStrings(value.allowed_paths) || !nonEmptyStrings(value.forbidden_policy_paths) || !value.allowed_paths.every(relativePath) || !value.forbidden_policy_paths.every(relativePath)) invalid('paths must be non-empty relative string arrays without whitespace');
  if (!Array.isArray(value.approved_check_recipes) || !value.approved_check_recipes.length) invalid('missing check recipes');
  if (!Array.isArray(value.capture_recipes) || !value.capture_recipes.length) invalid('missing capture recipes');
  if (!Number.isInteger(value.repair_cycles) || value.repair_cycles < 0 || value.repair_cycles > 2) invalid('invalid repair cycles');
  const states = new Set(['draft', 'approved', 'building', 'candidate_ready', 'reviewing', 'repairing', 'accepted', 'blocked', 'failed']);
  if (!states.has(value.state)) invalid('invalid state');
  if (!['@ui_code', '@ui_review'].includes(value.model_route)) invalid('invalid model route');
  if ((value.state === 'accepted' && value.outcome !== 'verified') || (value.state === 'blocked' && value.outcome !== 'blocked') || (value.state === 'failed' && value.outcome !== 'failed') || (!['accepted', 'blocked', 'failed'].includes(value.state) && value.outcome !== 'unverified')) invalid('state/outcome mismatch');
  if (['candidate_ready', 'reviewing', 'repairing', 'accepted'].includes(value.state) && (typeof value.candidate_revision !== 'string' || !/^sha256:[a-f0-9]{64}$/i.test(value.candidate_hash))) invalid('candidate binding required');
  if (['accepted', 'blocked', 'failed'].includes(value.state) && !nonEmptyStrings(value.evidence_refs)) invalid('terminal evidence required');
  if (value.state === 'repairing' && (!value.repair_authorization || typeof value.repair_authorization !== 'object' || !Number.isInteger(value.repair_authorization.cycle) || value.repair_authorization.cycle !== value.repair_cycles || value.repair_authorization.cycle < 1 || typeof value.repair_authorization.nonce !== 'string' || !value.repair_authorization.nonce)) invalid('repairing requires renewed cycle-bound authorization');
  const ids = new Set<string>();
  for (const recipe of value.approved_check_recipes) {
    if (!recipe || typeof recipe !== 'object' || typeof recipe.id !== 'string' || !recipe.id || ids.has(recipe.id) || !nonEmptyStrings(recipe.argv) || !relativePath(recipe.cwd) || !relativePath(recipe.result_path) || !nonEmptyStrings(recipe.write_paths) || !recipe.write_paths.every(relativePath) || !recipe.write_paths.includes(recipe.result_path) || !Number.isInteger(recipe.timeout_ms) || recipe.timeout_ms < 1 || recipe.timeout_ms > 120000 || !['sandbox-exec', 'docker'].includes(recipe.backend)) invalid('invalid check recipe');
    const verifier = recipe.trusted_verifier;
    if (!verifier || typeof verifier !== 'object' || !/^\.omp\/ui-delivery\/verifiers\/(?!.*\.\.)[^/].*$/.test(verifier.path) || !/^sha256:[a-f0-9]{64}$/i.test(verifier.sha256)) invalid('invalid trusted verifier');
    for (const writePath of recipe.write_paths) if (writePath === '.' || writePath === '.git' || writePath === '.omp' || writePath === 'secrets' || value.allowed_paths.some((allowed: string) => allowed === writePath || allowed.startsWith(`${writePath}/`) || writePath.startsWith(`${allowed}/`))) invalid('check output overlaps candidate scope');
    ids.add(recipe.id);
    if (recipe.backend === 'docker' && (typeof recipe.sandbox_image !== 'string' || !/^[^@\s]+@sha256:[a-f0-9]{64}$/i.test(recipe.sandbox_image))) invalid('docker image must be digest pinned');
  }
  const captureIds = new Set<string>();
  for (const recipe of value.capture_recipes) {
    if (!recipe || typeof recipe !== 'object' || typeof recipe.id !== 'string' || !recipe.id || captureIds.has(recipe.id) || typeof recipe.check_id !== 'string' || !ids.has(recipe.check_id) || !Array.isArray(recipe.artifacts) || recipe.artifacts.length < 1) invalid('invalid capture recipe');
    captureIds.add(recipe.id);
    const check = value.approved_check_recipes.find((entry: Record<string, unknown>) => entry.id === recipe.check_id);
    for (const artifact of recipe.artifacts) if (!artifact || typeof artifact !== 'object' || !relativePath(artifact.path) || typeof artifact.type !== 'string' || !artifact.type || !Array.isArray(check?.write_paths) || !check.write_paths.includes(artifact.path)) invalid('invalid capture artifact');
  }
}

function excludedCandidatePath(path: string, task: DeliveryTask): boolean {
  if (path === '.git' || path.startsWith('.git/') || path === '.omp/ui-delivery' || path.startsWith('.omp/ui-delivery/')) return true;
  const outputs = task.approved_check_recipes.flatMap((recipe: { write_paths?: unknown }) => Array.isArray(recipe.write_paths) ? recipe.write_paths : []);
  return outputs.some((output: string) => path === output || path.startsWith(`${output}/`));
}
async function walk(root: string, current: string, task: DeliveryTask, files: string[]): Promise<void> {
  const rel = relative(root, current);
  if (excludedCandidatePath(rel, task)) return;
  const stat = await lstat(current);
  if (stat.isSymbolicLink()) throw new Error('candidate contains symlink');
  if (stat.isDirectory()) { for (const name of await readdir(current)) await walk(root, join(current, name), task, files); return; }
  if (stat.isFile()) files.push(current);
}
export function patchJournalPath(repo: string, taskId: string): string { return join(repo, '.omp', 'ui-delivery', 'evidence', `${taskId}.patch-pending.json`); }
async function assertNoPendingPatchJournal(repo: string, taskId: string): Promise<void> {
  try {
    const stat = await lstat(patchJournalPath(repo, taskId));
    if (!stat.isFile() || stat.isSymbolicLink()) invalid('patch recovery state is invalid');
    invalid('patch recovery is pending');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
}
export async function candidateHash({ repo, task }: { repo: string; task: DeliveryTask }): Promise<string> {
  const root = await realpath(repo); const files: string[] = [];
  await walk(root, root, task, files);
  files.sort(); const hash = createHash('sha256');
  for (const path of files) { const relativePath = relative(root, path); const bytes = await readFile(path); hash.update(Buffer.from(`${relativePath}\0${bytes.length}\0`)); hash.update(bytes); }
  return `sha256:${hash.digest('hex')}`;
}

export async function resolveTaskFile({ repo, taskFile }: { repo: string; taskFile: string }): Promise<string> {
  const root = await realpath(repo); const tasks = join(root, '.omp', 'ui-delivery', 'tasks');
  let actual: string; try { actual = await realpath(resolve(root, taskFile)); } catch { return invalid('task file does not exist'); }
  if (!within(tasks, actual)) invalid('task file is outside policy directory');
  return actual;
}

export async function loadTask({ repo, taskFile, mutation = false, operation, now = new Date() }: { repo: string; taskFile: string; mutation?: boolean; operation?: 'patch' | 'check' | 'capture'; now?: Date }): Promise<DeliveryTask> {
  const actual = await resolveTaskFile({ repo, taskFile });
  let task: unknown; try { task = JSON.parse(await readFile(actual, 'utf8')); } catch { invalid('task file is not JSON'); }
  validate(task);
  await assertNoPendingPatchJournal(await realpath(repo), task.task_id);
  if (mutation || operation) {
    if (operation === 'patch') {
      if (task.model_route !== '@ui_code') invalid('patch requires @ui_code model route');
      if (task.state !== 'approved' && task.state !== 'repairing') invalid('patch requires approved or renewed repairing lifecycle state');
    } else if (operation === 'check') {
      if (task.model_route !== '@ui_code') invalid('check requires @ui_code model route');
      if (!['candidate_ready', 'reviewing', 'repairing', 'accepted'].includes(task.state)) invalid('check requires candidate lifecycle state');
    } else if (operation === 'capture') {
      if (task.model_route !== '@ui_review') invalid('capture requires @ui_review model route');
      if (!['reviewing', 'accepted'].includes(task.state)) invalid('capture requires reviewing or accepted lifecycle state');
    } else {
      if (task.model_route !== '@ui_code') invalid('mutation requires @ui_code model route');
      if (!['approved', 'candidate_ready'].includes(task.state)) invalid('mutation requires authorized lifecycle state');
    }
    if (process.env.UI_DELIVERY_APPROVED_TASK_SHA256 !== authorizationDigest(task)) invalid('external approval digest mismatch');
  }
  const grant = task.stitch_grant;
  const grantExpiry = grant && typeof grant.expires_at === 'string' ? Date.parse(grant.expires_at) : Number.NaN;
  if (grant && !Number.isFinite(grantExpiry)) invalid('Stitch grant expiry is invalid');
  if ((mutation || operation) && grant && grantExpiry <= now.getTime()) invalid('Stitch grant expired');
  return task;
}
