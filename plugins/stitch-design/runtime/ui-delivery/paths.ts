import { lstat, realpath } from 'node:fs/promises';
import { dirname, relative, resolve, sep } from 'node:path';

const PROTECTED = ['.git', '.omp', 'secrets'];
function isBelow(root: string, candidate: string): boolean { const rel = relative(root, candidate); return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..'); }
function blocked(rel: string, entries: string[]): boolean { return entries.some((entry) => entry === '.' || rel === entry || rel.startsWith(`${entry}${sep}`) || entry.startsWith(`${rel}${sep}`)); }
async function existingAncestor(path: string): Promise<string> { let current = path; while (true) { try { await lstat(current); return current; } catch { const parent = dirname(current); if (parent === current) throw new Error('no existing ancestor'); current = parent; } } }
async function noSymlinkComponents(root: string, path: string): Promise<void> { let current = root; for (const part of relative(root, path).split(sep)) { if (!part) continue; current = resolve(current, part); try { if ((await lstat(current)).isSymbolicLink()) throw new Error('symlink path is forbidden'); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; break; } } }

export async function authorizePath({ repo, task, path }: { repo: string; task: { allowed_paths: string[]; forbidden_policy_paths: string[] }; path: string }): Promise<string> {
  if (typeof path !== 'string' || !path || path.includes('\0') || path.startsWith('/') || path.includes('\\') || path.includes('//') || path.split('/').some((part) => part === '.' || part === '..' || !part)) throw new Error('invalid path');
  const root = await realpath(repo); const candidate = resolve(root, path);
  if (!isBelow(root, candidate)) throw new Error('path escapes repository');
  const rel = relative(root, candidate);
  if (blocked(rel, [...PROTECTED, ...task.forbidden_policy_paths])) throw new Error('protected path');
  if (!task.allowed_paths.some((entry) => isBelow(resolve(root, entry), candidate))) throw new Error('path is not authorized');
  await noSymlinkComponents(root, candidate);
  const ancestor = await existingAncestor(candidate);
  if (!isBelow(root, await realpath(ancestor))) throw new Error('path resolves outside repository');
  return candidate;
}
