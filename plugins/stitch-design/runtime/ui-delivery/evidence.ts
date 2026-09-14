import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { mkdir, open, lstat, realpath, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { basename, dirname, join, relative, resolve, sep } from 'node:path';

function canonical(value: unknown): string { if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`; if (value && typeof value === 'object') return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`; return JSON.stringify(value); }
export function canonicalJsonHash(value: unknown): string { return `sha256:${createHash('sha256').update(canonical(value)).digest('hex')}`; }
function below(root: string, candidate: string): boolean { const rel = relative(root, candidate); return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..'); }
export async function prepareEvidenceDirectory(repo: string): Promise<string> {
  const root = await realpath(repo); let current = root;
  for (const part of ['.omp', 'ui-delivery']) { current = join(current, part); const stat = await lstat(current); if (!stat.isDirectory() || stat.isSymbolicLink() || !below(root, await realpath(current))) throw new Error('evidence policy directory is unsafe'); }
  const evidence = join(current, 'evidence');
  try { await mkdir(evidence, { mode: 0o700 }); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error; }
  const stat = await lstat(evidence); if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('evidence policy directory is unsafe');
  const actual = await realpath(evidence); if (!below(root, actual)) throw new Error('evidence directory escapes repository'); return actual;
}

export async function appendEvidence({ repo, evidenceFile, record }: { repo: string; evidenceFile: string; record: Record<string, unknown> }): Promise<void> {
  for (const field of ['taskId', 'approvedDesignHash', 'candidateRevision', 'candidateHash', 'modelRoute', 'operation', 'outcome', 'stdoutHash', 'stderrHash']) if (typeof record[field] !== 'string' || !record[field] || record[field] === 'unbound') throw new Error(`evidence missing ${field}`);
  if (typeof record.elapsedMs !== 'number' || !Array.isArray(record.artifacts)) throw new Error('evidence has invalid bounded fields');
  const root = await realpath(repo); const evidenceRoot = await prepareEvidenceDirectory(root); const requested = resolve(root, evidenceFile);
  let parent: string; try { parent = await realpath(dirname(requested)); } catch { throw new Error('evidence parent is unavailable'); }
  if (parent !== evidenceRoot || !requested.endsWith('.jsonl')) throw new Error('evidence path is not authorized');
  const target = join(parent, basename(requested));
  try { const stat = await lstat(target); if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1) throw new Error('evidence file is unsafe'); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const handle = await open(target, constants.O_APPEND | constants.O_CREAT | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
  try { const stat = await handle.stat(); if (!stat.isFile() || stat.nlink !== 1) throw new Error('evidence file is unsafe'); await handle.write(`${JSON.stringify(record)}\n`); }
  finally { await handle.close(); }
}

export type StitchMutationState = {
  authorizationDigest: string;
  entries: Record<string, 'pending' | 'consumed' | 'reconciled'>;
  projectId?: string;
  version: number;
};

async function stateFile(repo: string, taskId: string): Promise<string> {
  if (!/^[A-Za-z0-9._-]+$/.test(taskId)) throw new Error('invalid Stitch state task id');
  return join(await prepareEvidenceDirectory(repo), `${taskId}.stitch-state.json`);
}

export async function loadStitchMutationState({ repo, taskId, authorizationDigest }: { repo: string; taskId: string; authorizationDigest: string }): Promise<StitchMutationState | undefined> {
  const target = await stateFile(repo, taskId);
  try {
    const stat = await lstat(target);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1) throw new Error('Stitch state file is unsafe');
    const state = JSON.parse(await readFile(target, 'utf8')) as StitchMutationState;
    if (
      state.authorizationDigest !== authorizationDigest
      || !state.entries
      || typeof state.entries !== 'object'
      || Array.isArray(state.entries)
      || Object.getPrototypeOf(state.entries) !== Object.prototype
      || Object.entries(state.entries).some(([key, value]) => !key || !['pending', 'consumed', 'reconciled'].includes(value))
      || !Number.isInteger(state.version)
      || state.version < 0
      || (state.projectId !== undefined && (typeof state.projectId !== 'string' || !state.projectId))
    ) return undefined;
    return state;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw error;
  }
}

export async function updateStitchMutationState({ repo, taskId, authorizationDigest, expectedVersion, state }: { repo: string; taskId: string; authorizationDigest: string; expectedVersion: number; state: Omit<StitchMutationState, 'authorizationDigest' | 'version'> }): Promise<StitchMutationState> {
  const target = await stateFile(repo, taskId);
  const lock = `${target}.lock`;
  let handle;
  try {
    handle = await open(lock, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
    const current = await loadStitchMutationState({ repo, taskId, authorizationDigest });
    const version = current?.version ?? 0;
    if (version !== expectedVersion) throw new Error('Stitch mutation state changed concurrently');
    const entries = state.entries;
    if (!entries || typeof entries !== 'object' || Array.isArray(entries) || Object.getPrototypeOf(entries) !== Object.prototype || Object.entries(entries).some(([key, value]) => !key || !['pending', 'consumed', 'reconciled'].includes(value))) throw new Error('Stitch state entries are invalid');
    const next: StitchMutationState = { authorizationDigest, entries, ...(state.projectId ? { projectId: state.projectId } : {}), version: version + 1 };
    const temporary = join(dirname(target), `.${basename(target)}.${process.pid}.${Date.now()}.tmp`);
    await writeFile(temporary, JSON.stringify(next), { mode: 0o600, flag: 'wx' });
    await rename(temporary, target);
    return next;
  } finally {
    await handle?.close();
    await unlink(lock).catch(() => undefined);
  }
}
