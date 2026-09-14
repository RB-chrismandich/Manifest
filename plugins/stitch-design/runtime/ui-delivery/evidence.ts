import { createHash } from 'node:crypto';
import { appendFile, lstat, realpath } from 'node:fs/promises';
import { dirname, relative, resolve, sep } from 'node:path';

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`;
  return JSON.stringify(value);
}

export function canonicalJsonHash(value: unknown): string {
  return `sha256:${createHash('sha256').update(canonical(value)).digest('hex')}`;
}

function isBelow(root: string, candidate: string): boolean {
  const rel = relative(root, candidate);
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..');
}

export async function appendEvidence({ repo, evidenceFile, record }: { repo: string; evidenceFile: string; record: Record<string, unknown> }): Promise<void> {
  for (const field of ['taskId', 'approvedDesignHash', 'candidateRevision', 'candidateHash', 'modelRoute', 'operation', 'outcome', 'stdoutHash', 'stderrHash']) if (typeof record[field] !== 'string' || !record[field]) throw new Error(`evidence missing ${field}`);
  if (typeof record.elapsedMs !== 'number' || !Array.isArray(record.artifacts)) throw new Error('evidence has invalid bounded fields');
  const root = await realpath(repo);
  const evidenceRoot = await realpath(resolve(root, '.omp/ui-delivery/evidence'));
  const requested = resolve(root, evidenceFile);
  if (!isBelow(evidenceRoot, requested) || dirname(requested) !== evidenceRoot) throw new Error('evidence path is not authorized');
  try {
    await lstat(requested);
    if (!isBelow(evidenceRoot, await realpath(requested))) throw new Error('evidence path escapes directory');
  } catch (error) {
    if (error instanceof Error && error.message.includes('escapes')) throw error;
  }
  await appendFile(requested, `${JSON.stringify(record)}\n`, { encoding: 'utf8', flag: 'a' });
}
