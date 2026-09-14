import { lstat, realpath } from 'node:fs/promises';
import { dirname, relative, resolve, sep } from 'node:path';

function isBelow(root: string, candidate: string): boolean {
  const rel = relative(root, candidate);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..');
}

async function existingAncestor(path: string): Promise<string> {
  let current = path;
  while (true) {
    try { await lstat(current); return current; } catch {
      const parent = dirname(current);
      if (parent === current) throw new Error('no existing ancestor');
      current = parent;
    }
  }
}

export async function authorizePath({ repo, task, path }: { repo: string; task: { allowed_paths: string[]; forbidden_policy_paths: string[] }; path: string }): Promise<string> {
  if (typeof path !== 'string' || !path || path.includes('\0')) throw new Error('invalid path');
  const root = await realpath(repo);
  const candidate = resolve(root, path);
  if (!isBelow(root, candidate)) throw new Error('path escapes repository');
  const rel = relative(root, candidate);
  const blocked = ['.git', '.omp/ui-delivery/tasks', '.omp/ui-delivery/evidence', 'secrets'];
  if (blocked.some((entry) => rel === entry || rel.startsWith(`${entry}${sep}`)) || task.forbidden_policy_paths.some((entry) => rel === entry || rel.startsWith(`${entry}${sep}`))) throw new Error('protected path');
  const allowed = task.allowed_paths.some((entry) => {
    const base = resolve(root, entry);
    return isBelow(base, candidate);
  });
  if (!allowed) throw new Error('path is not authorized');
  const ancestor = await existingAncestor(candidate);
  if (!isBelow(root, await realpath(ancestor))) throw new Error('path resolves outside repository');
  return candidate;
}
