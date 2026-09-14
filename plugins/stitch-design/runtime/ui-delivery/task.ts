import { realpath, readFile } from 'node:fs/promises';
import { dirname, join, relative, resolve, sep } from 'node:path';

export type DeliveryTask = Record<string, any>;

function within(root: string, candidate: string): boolean {
  const rel = relative(root, candidate);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !rel.includes(`${sep}..${sep}`));
}

function invalid(message: string): never { throw new Error(`Invalid UI delivery task: ${message}`); }

function nonEmptyStrings(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every((entry) => typeof entry === 'string' && entry.length > 0);
}

function validate(task: unknown): asserts task is DeliveryTask {
  if (!task || typeof task !== 'object' || Array.isArray(task)) invalid('must be an object');
  const value = task as DeliveryTask;
  for (const key of ['task_id', 'state', 'design_revision', 'model_route', 'outcome']) if (typeof value[key] !== 'string' || !value[key]) invalid(`missing ${key}`);
  if (!nonEmptyStrings(value.allowed_paths) || !nonEmptyStrings(value.forbidden_policy_paths)) invalid('paths must be non-empty string arrays');
  if (!Array.isArray(value.approved_check_recipes) || !value.approved_check_recipes.length) invalid('missing check recipes');
  if (!Array.isArray(value.capture_recipes) || !value.capture_recipes.length) invalid('missing capture recipes');
  if (!Number.isInteger(value.repair_cycles) || value.repair_cycles < 0 || value.repair_cycles > 2) invalid('invalid repair cycles');
  const states = new Set(['draft', 'approved', 'candidate_ready', 'reviewing', 'repairing', 'accepted', 'blocked', 'failed']);
  if (!states.has(value.state)) invalid('invalid state');
  if (value.model_route !== '@ui_code') invalid('invalid model route');
  if ((value.state === 'accepted' && value.outcome !== 'verified') || (value.state === 'blocked' && value.outcome !== 'blocked') || (value.state === 'failed' && value.outcome !== 'failed') || (!['accepted', 'blocked', 'failed'].includes(value.state) && value.outcome !== 'unverified')) invalid('state/outcome mismatch');
  if (['candidate_ready', 'reviewing', 'repairing', 'accepted', 'blocked', 'failed'].includes(value.state) && (typeof value.candidate_revision !== 'string' || typeof value.candidate_hash !== 'string')) invalid('candidate binding required');
  for (const recipe of value.approved_check_recipes) {
    if (!recipe || typeof recipe !== 'object' || !nonEmptyStrings(recipe.argv) || typeof recipe.id !== 'string' || typeof recipe.cwd !== 'string' || !Number.isInteger(recipe.timeout_ms) || recipe.timeout_ms < 1 || recipe.timeout_ms > 120000 || !['sandbox-exec', 'docker'].includes(recipe.backend)) invalid('invalid check recipe');
    if (recipe.backend === 'docker' && (typeof recipe.sandbox_image !== 'string' || !/@sha256:[a-f0-9]{16,}$/i.test(recipe.sandbox_image))) invalid('docker image must be digest pinned');
  }
}

export async function loadTask({ repo, taskFile, mutation = false, now = new Date() }: { repo: string; taskFile: string; mutation?: boolean; now?: Date }): Promise<DeliveryTask> {
  const root = await realpath(repo);
  const tasks = join(root, '.omp', 'ui-delivery', 'tasks');
  const requested = resolve(root, taskFile);
  if (!within(tasks, requested)) invalid('task file is outside policy directory');
  let actual: string;
  try { actual = await realpath(requested); } catch { invalid('task file does not exist'); }
  if (!within(tasks, actual)) invalid('task file escapes policy directory');
  let task: unknown;
  try { task = JSON.parse(await readFile(actual, 'utf8')); } catch { invalid('task file is not JSON'); }
  validate(task);
  if (mutation && task.state !== 'approved') invalid('mutation requires approved state');
  const grant = task.stitch_grant;
  if (mutation && grant && (!grant.expires_at || Number.isNaN(Date.parse(grant.expires_at)) || Date.parse(grant.expires_at) <= now.getTime())) invalid('Stitch grant expired');
  return task;
}
