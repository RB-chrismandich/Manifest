import { createHash } from 'node:crypto';
import { constants, createReadStream } from 'node:fs';
import { lstat, open, readdir, readFile, realpath, rename, unlink, type FileHandle } from 'node:fs/promises';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { canonicalJsonHash } from './evidence.ts';
import { STITCH_MUTATION_TOOL_NAMES, STITCH_READBACK_TOOL_NAMES } from './stitch-policy.ts';
export type DeliveryTask = Record<string, any>;

function within(root: string, candidate: string): boolean {
  const rel = relative(root, candidate);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !rel.includes(`${sep}..${sep}`));
}
function invalid(message: string): never { throw new Error(`Invalid UI delivery task: ${message}`); }
function nonEmptyStrings(value: unknown): value is string[] { return Array.isArray(value) && value.length > 0 && value.every((entry) => typeof entry === 'string' && entry.length > 0); }
function relativePath(value: unknown): value is string { return value === '.' || typeof value === 'string' && value.length > 0 && !/\s/.test(value) && !value.startsWith('/') && !value.includes('\\') && !value.includes('//') && !value.split('/').some((part) => part === '.' || part === '..' || !part); }

function canonicalUtcDateTime(value: unknown): number | undefined {
  if (typeof value !== 'string') return undefined;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/.exec(value);
  if (!match) return undefined;
  const [, year, month, day, hour, minute, second] = match.map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hour, minute, second, 0);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day || date.getUTCHours() !== hour || date.getUTCMinutes() !== minute || date.getUTCSeconds() !== second) return undefined;
  return date.getTime();
}

export function authorizationDigest(task: DeliveryTask): string {
  const projection = Object.fromEntries(['task_id', 'design_revision', 'qualification_hash', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant', 'repair_authorization'].filter((key) => key in task).map((key) => [key, task[key]]));
  return canonicalJsonHash(projection);
}

export function assertActiveRuntimeQualification(task: DeliveryTask): void {
  if (process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 !== task.qualification_hash) invalid('active runtime qualification mismatch');
}

function validate(task: unknown): asserts task is DeliveryTask {
  if (!task || typeof task !== 'object' || Array.isArray(task)) invalid('must be an object');
  const value = task as DeliveryTask;
  for (const key of ['task_id', 'state', 'design_revision', 'qualification_hash', 'model_route', 'outcome']) if (typeof value[key] !== 'string' || !value[key]) invalid(`missing ${key}`);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value.task_id)) invalid('invalid task_id');
  if (!/^sha256:[a-f0-9]{64}$/i.test(value.qualification_hash)) invalid('invalid qualification hash');
  if (!nonEmptyStrings(value.allowed_paths) || !nonEmptyStrings(value.forbidden_policy_paths) || !value.allowed_paths.every(relativePath) || value.allowed_paths.includes('.') || !value.forbidden_policy_paths.every(relativePath)) invalid('paths must be non-empty relative string arrays without whitespace or repository root');
  if (!Array.isArray(value.approved_check_recipes) || !value.approved_check_recipes.length) invalid('missing check recipes');
  if (!Array.isArray(value.capture_recipes) || !value.capture_recipes.length) invalid('missing capture recipes');
  if (!Number.isInteger(value.repair_cycles) || value.repair_cycles < 0 || value.repair_cycles > 2) invalid('invalid repair cycles');
  const states = new Set(['draft', 'approved', 'building', 'candidate_ready', 'reviewing', 'repairing', 'accepted', 'blocked', 'failed']);
  if (!states.has(value.state)) invalid('invalid state');
  if (!['@ui_code', '@ui_review'].includes(value.model_route)) invalid('invalid model route');
  if ((value.state === 'accepted' && (value.outcome !== 'verified' || value.model_route !== '@ui_review')) || (value.state === 'blocked' && value.outcome !== 'blocked') || (value.state === 'failed' && value.outcome !== 'failed') || (!['accepted', 'blocked', 'failed'].includes(value.state) && value.outcome !== 'unverified')) invalid('state/outcome/model route mismatch');
  if (['candidate_ready', 'reviewing', 'repairing', 'accepted'].includes(value.state) && (typeof value.candidate_revision !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(value.candidate_hash))) invalid('candidate binding required');
  if (['accepted', 'blocked', 'failed'].includes(value.state) && !nonEmptyStrings(value.evidence_refs)) invalid('terminal evidence required');
  if (value.state === 'repairing' && (!value.repair_authorization || typeof value.repair_authorization !== 'object' || !Number.isInteger(value.repair_authorization.cycle) || value.repair_authorization.cycle !== value.repair_cycles || value.repair_authorization.cycle < 1 || typeof value.repair_authorization.nonce !== 'string' || !value.repair_authorization.nonce)) invalid('repairing requires renewed cycle-bound authorization');
  const ids = new Set<string>();
  for (const recipe of value.approved_check_recipes) {
    if (!recipe || typeof recipe !== 'object' || typeof recipe.id !== 'string' || !recipe.id || ids.has(recipe.id) || !nonEmptyStrings(recipe.argv) || !relativePath(recipe.cwd) || !relativePath(recipe.result_path) || !nonEmptyStrings(recipe.write_paths) || !recipe.write_paths.every(relativePath) || !recipe.write_paths.includes(recipe.result_path) || !Number.isInteger(recipe.timeout_ms) || recipe.timeout_ms < 1 || recipe.timeout_ms > 120000 || !['sandbox-exec', 'docker'].includes(recipe.backend)) invalid('invalid check recipe');
    const verifier = recipe.trusted_verifier;
    if (!verifier || typeof verifier !== 'object' || !/^\.omp\/ui-delivery\/verifiers\/(?!.*\.\.)[^/].*$/.test(verifier.path) || !/^sha256:[a-f0-9]{64}$/i.test(verifier.sha256)) invalid('invalid trusted verifier');
    for (const writePath of recipe.write_paths) if (writePath === '.' || writePath === '.git' || writePath === '.omp' || writePath === 'secrets' || value.allowed_paths.some((allowed: string) => allowed === writePath || allowed.startsWith(`${writePath}/`) || writePath.startsWith(`${allowed}/`))) invalid('check output overlaps candidate scope');
    ids.add(recipe.id);
    if (recipe.backend === 'docker' && (typeof recipe.sandbox_image !== 'string' || !/^[^@\s]+@sha256:[a-f0-9]{64}$/i.test(recipe.sandbox_image) || !['node', 'python3'].includes(recipe.argv[0]))) invalid('docker recipe must start with an approved image runtime');
  }
  const captureIds = new Set<string>();
  const artifactPaths = new Set<string>();
  for (const recipe of value.capture_recipes) {
    if (!recipe || typeof recipe !== 'object' || typeof recipe.id !== 'string' || !recipe.id || captureIds.has(recipe.id) || typeof recipe.check_id !== 'string' || !ids.has(recipe.check_id) || !Array.isArray(recipe.artifacts) || recipe.artifacts.length < 1) invalid('invalid capture recipe');
    captureIds.add(recipe.id);
    const check = value.approved_check_recipes.find((entry: Record<string, unknown>) => entry.id === recipe.check_id);
    for (const artifact of recipe.artifacts) {
      if (!artifact || typeof artifact !== 'object' || !relativePath(artifact.path) || typeof artifact.type !== 'string' || !artifact.type || !Array.isArray(check?.write_paths) || !check.write_paths.includes(artifact.path)) invalid('invalid capture artifact');
      if (artifactPaths.has(artifact.path)) invalid('duplicate capture artifact path');
      artifactPaths.add(artifact.path);
    }
  }
  const grant = value.stitch_grant;
  if (grant !== undefined) {
    if (!grant || typeof grant !== 'object' || !Array.isArray(grant.mutations) || !nonEmptyStrings(grant.readback_tools) || !grant.readback_tools.every((tool: string) => STITCH_READBACK_TOOL_NAMES.includes(tool as typeof STITCH_READBACK_TOOL_NAMES[number])) || canonicalUtcDateTime(grant.expires_at) === undefined) invalid('invalid Stitch grant');
    if (grant.mutations.some((mutation: Record<string, unknown>) => mutation?.tool_name === 'mcp__stitch_create_project') && Object.hasOwn(grant, 'project_id')) invalid('project-bound create grant is invalid');
    const mutationKeys = new Set<string>();
    for (const mutation of grant.mutations) {
      const expected = mutation?.expected_readback;
      const expectedRecord = expected && typeof expected === 'object' && !Array.isArray(expected) ? expected : undefined;
      const creating = mutation?.tool_name === 'mcp__stitch_create_project';
      const predictableFields = expectedRecord?.predictable_fields;
      const exactReadback = /^sha256:[a-f0-9]{64}$/.test(expectedRecord?.response_hash) && !Object.hasOwn(expectedRecord ?? {}, 'predictable_fields') && !Object.hasOwn(expectedRecord ?? {}, 'resource_identity');
      const predictableReadback = predictableFields && typeof predictableFields === 'object' && !Array.isArray(predictableFields) && Object.keys(predictableFields).length > 0 && Object.keys(predictableFields).every((field) => /^(?!project_id$)[a-z][a-z0-9_]*$/.test(field)) && !Object.hasOwn(expectedRecord ?? {}, 'response_hash') && ['project', 'screen', 'design_system'].includes(expectedRecord?.resource_identity);
      if (!STITCH_MUTATION_TOOL_NAMES.includes(mutation?.tool_name) || !/^sha256:[a-f0-9]{64}$/.test(mutation?.input_hash) || mutation?.max_uses !== 1 || !expectedRecord || !STITCH_READBACK_TOOL_NAMES.includes(expectedRecord.tool_name) || !grant.readback_tools.includes(expectedRecord.tool_name)) invalid('invalid Stitch grant tool');
      if (!exactReadback && !predictableReadback || creating && (!predictableReadback || expectedRecord.resource_identity !== 'project')) invalid('invalid Stitch grant readback');
      const mutationKey = `${mutation.tool_name}\0${mutation.input_hash}`;
      if (mutationKeys.has(mutationKey)) invalid('duplicate Stitch grant mutation');
      mutationKeys.add(mutationKey);
    }
  }
}

function excludedCandidatePath(path: string, task: DeliveryTask): boolean {
  if (path === '.git' || path.startsWith('.git/') || path === '.omp' || path.startsWith('.omp/')) return true;
  const outputs = task.approved_check_recipes.flatMap((recipe: { write_paths?: unknown }) => Array.isArray(recipe.write_paths) ? recipe.write_paths : []);
  return outputs.some((output: string) => path === output || path.startsWith(`${output}/`));
}
type CandidateEntry = { path: string; directory: boolean };
async function walk(root: string, current: string, task: DeliveryTask, entries: CandidateEntry[]): Promise<void> {
  const rel = relative(root, current);
  if (excludedCandidatePath(rel, task)) return;
  const stat = await lstat(current);
  if (stat.isSymbolicLink()) throw new Error('candidate contains symlink');
  if (stat.isDirectory()) {
    entries.push({ path: current, directory: true });
    for (const name of (await readdir(current)).sort()) await walk(root, join(current, name), task, entries);
    return;
  }
  if (stat.isFile()) { entries.push({ path: current, directory: false }); return; }
  throw new Error('candidate contains unsupported filesystem entry');
}
export function patchJournalPath(repo: string): string { return join(repo, '.omp', 'ui-delivery', 'evidence', 'repository.patch-pending.json'); }
async function assertNoPendingPatchJournal(repo: string): Promise<void> {
  try {
    const stat = await lstat(patchJournalPath(repo));
    if (!stat.isFile() || stat.isSymbolicLink()) invalid('patch recovery state is invalid');
    invalid('patch recovery is pending');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
}

export type PatchJournalPersistence = {
  open: (path: string, flags: number, mode?: number) => Promise<Pick<FileHandle, 'writeFile' | 'sync' | 'close'>>;
  unlink?: (path: string) => Promise<void>;
};
const patchJournalPersistence: PatchJournalPersistence = { open, unlink };
export async function beginPatchJournal({ repo, taskId, taskFile, patchHash, persistence = patchJournalPersistence }: { repo: string; taskId: string; taskFile: string; patchHash: string; persistence?: PatchJournalPersistence }): Promise<string> {
  const journal = patchJournalPath(repo);
  const handle = await persistence.open(journal, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try {
    await handle.writeFile(JSON.stringify({ taskId, taskFile, patchHash, state: 'pending' }));
    await handle.sync();
  } finally {
    await handle.close();
  }
  const parent = await persistence.open(dirname(journal), constants.O_RDONLY | constants.O_DIRECTORY);
  try {
    await parent.sync();
  } finally {
    await parent.close();
  }
  return journal;
}

export async function releasePatchJournal(repo: string, persistence = patchJournalPersistence): Promise<void> {
  const journal = patchJournalPath(repo);
  if (!persistence.unlink) throw new Error('patch journal persistence cannot remove journal');
  await persistence.unlink(journal);
  const parent = await persistence.open(dirname(journal), constants.O_RDONLY | constants.O_DIRECTORY);
  try {
    await parent.sync();
  } finally {
    await parent.close();
  }
}
export type TaskReplacementPersistence = {
  open: (path: string, flags: number, mode?: number) => Promise<Pick<FileHandle, 'writeFile' | 'sync' | 'close'>>;
  rename: (oldPath: string, newPath: string) => Promise<void>;
};
const taskReplacementPersistence: TaskReplacementPersistence = { open, rename };
export async function replaceTaskFile({ repo, taskFile, task, persistence = taskReplacementPersistence }: { repo: string; taskFile: string; task: Record<string, unknown>; persistence?: TaskReplacementPersistence }): Promise<void> {
  const target = await resolveTaskFile({ repo, taskFile });
  const temporary = join(dirname(target), `.${target.split(sep).at(-1)}.${process.pid}.${Date.now()}.tmp`);
  const handle = await persistence.open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try {
    await handle.writeFile(JSON.stringify(task));
    await handle.sync();
  } finally {
    await handle.close();
  }
  await persistence.rename(temporary, target);
  const parent = await persistence.open(dirname(target), constants.O_RDONLY | constants.O_DIRECTORY);
  try {
    await parent.sync();
  } finally {
    await parent.close();
  }
}
export async function candidateHash({ repo, task }: { repo: string; task: DeliveryTask }): Promise<string> {
  validate(task);
  const root = await realpath(repo); const entries: CandidateEntry[] = [];
  await walk(root, root, task, entries);
  const hash = createHash('sha256');
  for (const { path, directory } of entries) {
    const candidatePath = relative(root, path);
    const stat = await lstat(path);
    if (directory) {
      hash.update(Buffer.from(`directory\0${candidatePath}\0${stat.mode & 0o777}\0`));
      continue;
    }
    hash.update(Buffer.from(`file\0${candidatePath}\0${stat.size}\0${stat.mode & 0o777}\0`));
    for await (const chunk of createReadStream(path)) hash.update(chunk);
  }
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
  await assertNoPendingPatchJournal(await realpath(repo));
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
    assertActiveRuntimeQualification(task);
  }
  const grant = task.stitch_grant;
  const grantExpiry = grant ? canonicalUtcDateTime(grant.expires_at) : undefined;
  if (grant && grantExpiry === undefined) invalid('Stitch grant expiry is invalid');
  if (mutation && grant && grantExpiry <= now.getTime()) invalid('Stitch grant expired');
  return task;
}
