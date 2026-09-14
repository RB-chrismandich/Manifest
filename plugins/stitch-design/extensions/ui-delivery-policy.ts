import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { basename, join } from 'node:path';
import type { ExtensionAPI } from '@oh-my-pi/pi-coding-agent';
import { runCheck } from '../runtime/ui-delivery/checks.ts';
import { appendEvidence } from '../runtime/ui-delivery/evidence.ts';
import { authorizePath } from '../runtime/ui-delivery/paths.ts';
import { loadTask } from '../runtime/ui-delivery/task.ts';

const STATUS = { extension: 'ui-delivery-policy', status: 'ready' } as const;
const result = (details: Record<string, unknown>) => ({ content: [{ type: 'text' as const, text: JSON.stringify(details) }], details });

function diffTargets(patch: string): string[] {
  if (!patch || /^(deleted file mode|rename from |rename to |new file mode 120000)/m.test(patch)) throw new Error('destructive or symlink diff is forbidden');
  const targets: string[] = [];
  for (const line of patch.split('\n')) {
    const matched = /^(?:diff --git a\/\S+ b\/|\+\+\+ b\/)(\S+)$/.exec(line);
    if (matched) targets.push(matched[1]);
  }
  if (!targets.length) throw new Error('patch has no file targets');
  for (const target of targets) if (target.startsWith('/') || target.split('/').includes('..') || target === '/dev/null') throw new Error('unsafe diff target');
  return [...new Set(targets)];
}

async function gitApply(cwd: string, patch: string, signal: AbortSignal): Promise<void> {
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  const child = spawn('git', ['apply', '--whitespace=nowarn', '--'], { cwd, shell: false, stdio: ['pipe', 'ignore', 'pipe'], signal });
  let stderr = '';
  child.stderr.on('data', (chunk) => { stderr += String(chunk).slice(0, 4096 - stderr.length); });
  child.on('error', reject);
  child.on('close', (code) => code === 0 ? resolve() : reject(new Error(`git apply failed${stderr ? ': rejected patch' : ''}`)));
  child.stdin.end(patch);
  return promise;
}

export default function uiDeliveryPolicy(pi: ExtensionAPI): void {
  pi.registerTool({ name: 'ui_delivery_status', label: 'UI delivery status', description: 'Read bounded UI delivery task status.', parameters: pi.zod.object({ taskFile: pi.zod.string().optional() }).strict(), approval: 'read', strict: true,
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const taskFile = (params as { taskFile?: string }).taskFile;
      if (!taskFile) return result(STATUS);
      const task = await loadTask({ repo: ctx.cwd, taskFile });
      return result({ extension: STATUS.extension, taskId: task.task_id, state: task.state, outcome: task.outcome });
    } });
  pi.registerTool({ name: 'ui_apply_patch', label: 'Apply approved UI patch', description: 'Apply an authorized non-destructive unified diff.', parameters: pi.zod.object({ taskFile: pi.zod.string(), patch: pi.zod.string() }).strict(), approval: 'write', strict: true,
    async execute(_id, params, signal, _onUpdate, ctx) {
      const args = params as { taskFile: string; patch: string };
      const task = await loadTask({ repo: ctx.cwd, taskFile: args.taskFile, mutation: true });
      const changedFiles = diffTargets(args.patch);
      for (const target of changedFiles) await authorizePath({ repo: ctx.cwd, task, path: target });
      await gitApply(ctx.cwd, args.patch, signal);
      return result({ taskId: task.task_id, operation: 'ui_apply_patch', outcome: 'mutation_unknown', changedFiles, patchHash: `sha256:${createHash('sha256').update(args.patch).digest('hex')}` });
    } });
  pi.registerTool({ name: 'ui_run_check', label: 'Run approved UI check', description: 'Run a named approved check in an OS sandbox.', parameters: pi.zod.object({ taskFile: pi.zod.string(), checkId: pi.zod.string() }).strict(), approval: 'exec', strict: true,
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const args = params as { taskFile: string; checkId: string };
      const task = await loadTask({ repo: ctx.cwd, taskFile: args.taskFile });
      const checked = await runCheck({ repo: ctx.cwd, task, checkId: args.checkId, environment: process.env });
      if (task.candidate_revision && task.candidate_hash) await appendEvidence({ repo: ctx.cwd, evidenceFile: join(ctx.cwd, '.omp/ui-delivery/evidence', `${task.task_id}.jsonl`), record: { taskId: task.task_id, approvedDesignHash: task.design_revision, candidateRevision: task.candidate_revision, candidateHash: task.candidate_hash, modelRoute: task.model_route, operation: 'ui_run_check', checkId: args.checkId, outcome: checked.exitCode === 0 ? 'verified' : 'failed', elapsedMs: 0, artifacts: [], stdoutHash: checked.stdout.hash, stderrHash: checked.stderr.hash } });
      return result({ taskId: task.task_id, operation: 'ui_run_check', checkId: args.checkId, exitCode: checked.exitCode, stdoutHash: checked.stdout.hash, stderrHash: checked.stderr.hash });
    } });
  pi.registerTool({ name: 'ui_capture', label: 'Capture approved UI evidence', description: 'Record only artifacts named by an approved capture recipe.', parameters: pi.zod.object({ taskFile: pi.zod.string(), recipeId: pi.zod.string() }).strict(), approval: 'exec', strict: true,
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const args = params as { taskFile: string; recipeId: string };
      const task = await loadTask({ repo: ctx.cwd, taskFile: args.taskFile });
      const recipe = task.capture_recipes.find((entry: { id: string }) => entry.id === args.recipeId);
      if (!recipe) throw new Error('unknown capture recipe');
      const checked = await runCheck({ repo: ctx.cwd, task, checkId: recipe.check_id, environment: process.env });
      if (checked.exitCode !== 0) throw new Error('capture check did not succeed');
      const artifacts = [];
      for (const artifact of recipe.artifacts) {
        const path = await authorizePath({ repo: ctx.cwd, task, path: artifact.path });
        const bytes = await readFile(path);
        artifacts.push({ path: artifact.path, hash: `sha256:${createHash('sha256').update(bytes).digest('hex')}` });
      }
      const evidenceFile = join(ctx.cwd, '.omp/ui-delivery/evidence', `${task.task_id}.jsonl`);
      await appendEvidence({ repo: ctx.cwd, evidenceFile, record: { taskId: task.task_id, approvedDesignHash: task.design_revision, candidateRevision: task.candidate_revision ?? 'unbound', candidateHash: task.candidate_hash ?? 'unbound', modelRoute: task.model_route, operation: 'ui_capture', outcome: 'captured', elapsedMs: 0, artifacts, stdoutHash: checked.stdout.hash, stderrHash: checked.stderr.hash } });
      return result({ taskId: task.task_id, operation: 'ui_capture', artifacts: artifacts.map((artifact) => basename(artifact.path)) });
    } });
  const optionalApi = pi as unknown as { on?: (event: string, handler: (event: { toolName: string; input: unknown; projectId: string }) => Promise<void>) => void; getMcpRegistry?: () => unknown[] };
  if (typeof optionalApi.on === 'function') optionalApi.on('tool_call', async () => { throw new Error('Stitch tool calls require a task-bound policy instance'); });
}
