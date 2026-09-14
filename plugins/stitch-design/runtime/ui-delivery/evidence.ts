import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { open, lstat, realpath } from 'node:fs/promises';
import { dirname, join, relative, resolve, sep } from 'node:path';

function canonical(value: unknown): string { if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`; if (value && typeof value === 'object') return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`; return JSON.stringify(value); }
export function canonicalJsonHash(value: unknown): string { return `sha256:${createHash('sha256').update(canonical(value)).digest('hex')}`; }
function below(root: string, candidate: string): boolean { const rel = relative(root, candidate); return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..'); }
async function safePolicyDirectory(root: string): Promise<string> { const components = ['.omp', 'ui-delivery', 'evidence']; let current = root; for (const part of components) { current = join(current, part); const stat = await lstat(current); if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('evidence policy directory is unsafe'); } const actual = await realpath(current); if (!below(root, actual)) throw new Error('evidence directory escapes repository'); return actual; }

export async function appendEvidence({ repo, evidenceFile, record }: { repo: string; evidenceFile: string; record: Record<string, unknown> }): Promise<void> {
  for (const field of ['taskId', 'approvedDesignHash', 'candidateRevision', 'candidateHash', 'modelRoute', 'operation', 'outcome', 'stdoutHash', 'stderrHash']) if (typeof record[field] !== 'string' || !record[field] || record[field] === 'unbound') throw new Error(`evidence missing ${field}`);
  if (typeof record.elapsedMs !== 'number' || !Array.isArray(record.artifacts)) throw new Error('evidence has invalid bounded fields');
  const root = await realpath(repo); const evidenceRoot = await safePolicyDirectory(root); const requested = resolve(root, evidenceFile);
  if (dirname(requested) !== evidenceRoot || join(evidenceRoot, requested.slice(evidenceRoot.length + 1)) !== requested || !requested.endsWith('.jsonl')) throw new Error('evidence path is not authorized');
  try { const stat = await lstat(requested); if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1) throw new Error('evidence file is unsafe'); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const handle = await open(requested, constants.O_APPEND | constants.O_CREAT | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600);
  try { const stat = await handle.stat(); if (!stat.isFile() || stat.nlink !== 1) throw new Error('evidence file is unsafe'); await handle.write(`${JSON.stringify(record)}\n`); }
  finally { await handle.close(); }
}
