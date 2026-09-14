import { createHash, randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { mkdir, open, lstat, realpath, readFile, rename, unlink, type FileHandle } from 'node:fs/promises';
import { hostname, uptime } from 'node:os';
import { basename, dirname, join, relative, resolve, sep } from 'node:path';

function canonical(value: unknown): string { if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`; if (value && typeof value === 'object') return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`; return JSON.stringify(value); }
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

export async function readEvidence({ repo, evidenceFile }: { repo: string; evidenceFile: string }): Promise<string | undefined> {
  const root = await realpath(repo);
  const evidenceRoot = await prepareEvidenceDirectory(root);
  const requested = resolve(root, evidenceFile);
  let parent: string;
  try { parent = await realpath(dirname(requested)); } catch { throw new Error('evidence parent is unavailable'); }
  if (parent !== evidenceRoot || !requested.endsWith('.jsonl')) throw new Error('evidence path is not authorized');
  let handle: FileHandle;
  try { handle = await open(join(parent, basename(requested)), constants.O_RDONLY | constants.O_NOFOLLOW); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw error;
  }
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1) throw new Error('evidence file is unsafe');
    return await handle.readFile({ encoding: 'utf8' });
  } finally {
    await handle.close();
  }
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


type StatePersistence = {
  open: typeof open;
  rename: typeof rename;
  unlink: typeof unlink;
};
const statePersistence: StatePersistence = { open, rename, unlink };
async function closeQuietly(handle: FileHandle | undefined): Promise<void> {
  if (handle) await handle.close().catch(() => undefined);
}

type MutationLockOwner = { pid: number; host: string; bootId: string; nonce: string };
type LockSnapshot = { owner: MutationLockOwner; serialized: string; dev: number; ino: number };
export type StitchMutationLockEnvironment = {
  host: string;
  bootId: string;
  processExists(pid: number): boolean;
};
const localLockEnvironment: StitchMutationLockEnvironment = {
  host: hostname(),
  bootId: String(Math.floor(Date.now() / 1_000 - uptime())),
  processExists(pid) {
    try { process.kill(pid, 0); return true; }
    catch (error) { return (error as NodeJS.ErrnoException).code !== 'ESRCH'; }
  },
};
const maxLockBytes = 4_096;

function validLockOwner(value: unknown): value is MutationLockOwner {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) return false;
  const owner = value as Record<string, unknown>;
  return Number.isSafeInteger(owner.pid) && owner.pid > 0
    && typeof owner.host === 'string' && owner.host.length > 0 && owner.host.length <= 255
    && typeof owner.bootId === 'string' && owner.bootId.length > 0 && owner.bootId.length <= 255
    && typeof owner.nonce === 'string' && /^[0-9a-f-]{36}$/i.test(owner.nonce)
    && Object.keys(owner).length === 4;
}

async function inspectMutationLock(lock: string): Promise<LockSnapshot | undefined> {
  let before;
  try { before = await lstat(lock); } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined; throw error; }
  if (!before.isFile() || before.isSymbolicLink() || before.nlink !== 1 || before.size > maxLockBytes) throw new Error('Stitch mutation lock is unsafe');
  const handle = await open(lock, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.dev !== before.dev || stat.ino !== before.ino || stat.size > maxLockBytes) throw new Error('Stitch mutation lock is unsafe');
    const serialized = await handle.readFile({ encoding: 'utf8' });
    const after = await lstat(lock);
    if (!after.isFile() || after.isSymbolicLink() || after.nlink !== 1 || after.dev !== stat.dev || after.ino !== stat.ino) throw new Error('Stitch mutation lock changed concurrently');
    let owner: unknown;
    try { owner = JSON.parse(serialized); } catch { throw new Error('Stitch mutation lock is malformed'); }
    if (!validLockOwner(owner)) throw new Error('Stitch mutation lock is malformed');
    return { owner, serialized, dev: stat.dev, ino: stat.ino };
  } finally { await handle.close(); }
}

function staleLock(snapshot: LockSnapshot, environment: StitchMutationLockEnvironment): boolean {
  if (snapshot.owner.host !== environment.host) return false;
  if (snapshot.owner.bootId !== environment.bootId) return true;
  try { return !environment.processExists(snapshot.owner.pid); } catch { return false; }
}

async function removeUnchangedStaleLock(lock: string, expected: LockSnapshot): Promise<boolean> {
  const current = await inspectMutationLock(lock);
  if (!current || current.dev !== expected.dev || current.ino !== expected.ino || current.serialized !== expected.serialized) return false;
  await unlink(lock);
  return true;
}

async function releaseMutationLock(lock: string, owned: LockSnapshot): Promise<void> {
  try {
    const current = await inspectMutationLock(lock);
    if (!current || current.dev !== owned.dev || current.ino !== owned.ino || current.serialized !== owned.serialized) return;
    await unlink(lock);
  } catch { /* A replacement or unsafe lock is not ours to remove. */ }
}

export type StitchMutationState = {
  authorizationDigest: string;
  entries: Record<string, 'pending' | 'consumed' | 'reconciled'>;
  identities?: Record<string, { kind: 'project' | 'screen' | 'design_system'; value: string }>;
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
      || (state.identities !== undefined && (!state.identities || typeof state.identities !== 'object' || Array.isArray(state.identities) || Object.getPrototypeOf(state.identities) !== Object.prototype || Object.entries(state.identities).some(([key, value]) => !key || !value || typeof value !== 'object' || !['project', 'screen', 'design_system'].includes(value.kind) || typeof value.value !== 'string' || !value.value)))
      || !Number.isInteger(state.version)
      || state.version < 0
      || (state.projectId !== undefined && (typeof state.projectId !== 'string' || !state.projectId))
    ) throw new Error('Stitch mutation state is malformed');
    return state;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw error;
  }
}

export async function updateStitchMutationState({ repo, taskId, authorizationDigest, expectedVersion, state, persistence = statePersistence, lockEnvironment = localLockEnvironment }: { repo: string; taskId: string; authorizationDigest: string; expectedVersion: number; state: Omit<StitchMutationState, 'authorizationDigest' | 'version'>; persistence?: StatePersistence; lockEnvironment?: StitchMutationLockEnvironment }): Promise<StitchMutationState> {
  const target = await stateFile(repo, taskId);
  const lock = `${target}.lock`;
  let handle: FileHandle | undefined;
  let temporaryHandle: FileHandle | undefined;
  let directoryHandle: FileHandle | undefined;
  let temporary: string | undefined;
  let ownedLock: LockSnapshot | undefined;
  let renamed = false;
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        handle = await persistence.open(lock, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
        const serialized = JSON.stringify({ pid: process.pid, host: lockEnvironment.host, bootId: lockEnvironment.bootId, nonce: randomUUID() });
        await handle.write(serialized);
        await handle.sync();
        const acquired = await inspectMutationLock(lock);
        if (!acquired || acquired.serialized !== serialized) throw new Error('Stitch mutation lock changed concurrently');
        ownedLock = acquired;
        break;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'EEXIST' || attempt !== 0) throw error;
        const existing = await inspectMutationLock(lock);
        if (!existing || !staleLock(existing, lockEnvironment) || !await removeUnchangedStaleLock(lock, existing)) throw new Error('Stitch mutation state changed concurrently');
      }
    }
    if (!ownedLock) throw new Error('Stitch mutation state changed concurrently');
    const current = await loadStitchMutationState({ repo, taskId, authorizationDigest });
    const version = current?.version ?? 0;
    if (version !== expectedVersion) throw new Error('Stitch mutation state changed concurrently');
    const entries = state.entries;
    const identities = state.identities;
    if (!entries || typeof entries !== 'object' || Array.isArray(entries) || Object.getPrototypeOf(entries) !== Object.prototype || Object.entries(entries).some(([key, value]) => !key || !['pending', 'consumed', 'reconciled'].includes(value))) throw new Error('Stitch state entries are invalid');
    if (identities !== undefined && (!identities || typeof identities !== 'object' || Array.isArray(identities) || Object.getPrototypeOf(identities) !== Object.prototype || Object.entries(identities).some(([key, value]) => !key || !value || typeof value !== 'object' || !['project', 'screen', 'design_system'].includes(value.kind) || typeof value.value !== 'string' || !value.value))) throw new Error('Stitch state identities are invalid');
    const next: StitchMutationState = { authorizationDigest, entries, ...(identities ? { identities } : {}), ...(state.projectId ? { projectId: state.projectId } : {}), version: version + 1 };
    temporary = join(dirname(target), `.${basename(target)}.${process.pid}.${Date.now()}.tmp`);
    temporaryHandle = await persistence.open(temporary, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
    await temporaryHandle.write(JSON.stringify(next));
    await temporaryHandle.sync();
    await temporaryHandle.close();
    temporaryHandle = undefined;
    await persistence.rename(temporary, target);
    renamed = true;
    directoryHandle = await persistence.open(dirname(target), constants.O_RDONLY);
    await directoryHandle.sync();
    return next;
  } finally {
    await closeQuietly(directoryHandle);
    await closeQuietly(temporaryHandle);
    if (temporary && !renamed) await persistence.unlink(temporary).catch(() => undefined);
    await closeQuietly(handle);
    if (ownedLock) await releaseMutationLock(lock, ownedLock);
  }
}
