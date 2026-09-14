import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat } from 'node:fs/promises';
import { basename, join } from 'node:path';
import type { ExtensionAPI } from '@oh-my-pi/pi-coding-agent';
import { runCheck as defaultRunCheck } from '../runtime/ui-delivery/checks.ts';
import { appendEvidence, loadStitchMutationState, prepareEvidenceDirectory, readEvidence, updateStitchMutationState } from '../runtime/ui-delivery/evidence.ts';
import { authorizePath } from '../runtime/ui-delivery/paths.ts';
import { assertActiveRuntimeQualification, authorizationDigest, beginPatchJournal, candidateHash, loadTask, releasePatchJournal, replaceTaskFile } from '../runtime/ui-delivery/task.ts';
import { createStitchPolicy, type StitchPolicy } from '../runtime/ui-delivery/stitch-policy.ts';

const STATUS = { extension: 'ui-delivery-policy', status: 'ready' } as const;
const result = (details: Record<string, unknown>) => ({ content: [{ type: 'text' as const, text: JSON.stringify(details) }], details });
class GitApplyRejectedError extends Error {
  constructor() { super('git apply rejected patch'); }
}

async function diffTargets(repo: string, patch: string): Promise<string[]> {
  const lines = patch.split('\n'); const targets: string[] = [];
  const parseRange = (start: string, count: string | undefined): [number, number] => {
    const parsedStart = Number(start); const parsedCount = count === undefined ? 1 : Number(count);
    if (!Number.isSafeInteger(parsedStart) || !Number.isSafeInteger(parsedCount) || parsedStart < 0 || parsedCount < 0 || (parsedStart === 0 && parsedCount !== 0)) throw new Error('malformed hunk header');
    return [parsedStart, parsedCount];
  };
  for (let index = 0; index < lines.length;) {
    if (!lines[index]) { index += 1; continue; }
    const header = /^diff --git a\/([^\s]+) b\/([^\s]+)$/.exec(lines[index++]);
    if (!header) throw new Error('unsafe or unparseable diff policy');
    const [oldPath, newPath] = [header[1], header[2]];
    if ([oldPath, newPath].some((path) => path.startsWith('/') || path.split('/').includes('..'))) throw new Error('unsafe diff path');
    let created = false;
    if (/^new file mode 100644$/.test(lines[index])) {
      created = true; index += 1;
      if (/^index /.test(lines[index] ?? '')) {
        if (!/^index 0{7,64}\.\.[0-9a-f]{7,}(?: 100644)?$/i.test(lines[index++])) throw new Error('malformed new-file metadata');
      }
    } else if (/^(?:new|old) mode|^(?:rename|copy) |^similarity index|^dissimilarity index|^Binary /.test(lines[index] ?? '')) throw new Error('destructive or symlink diff policy');
    else {
      const indexMetadata = /^index [0-9a-f]{7,}\.\.[0-9a-f]{7,}(?: (100644|100755))?$/i.exec(lines[index] ?? '');
      if (indexMetadata) {
        index += 1;
        if (indexMetadata[1]) {
          const stat = await lstat(join(repo, newPath));
          if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o777) !== (Number.parseInt(indexMetadata[1], 8) & 0o777)) throw new Error('unsafe executable or mismatched diff metadata');
        }
      }
    }
    if ((created && (oldPath !== newPath || lines[index++] !== '--- /dev/null' || lines[index++] !== `+++ b/${newPath}`)) || (!created && (oldPath !== newPath || lines[index++] !== `--- a/${oldPath}` || lines[index++] !== `+++ b/${newPath}`))) throw new Error('unsafe or destructive diff policy');
    let hunks = 0;
    while (index < lines.length && !lines[index].startsWith('diff --git ')) {
      if (!lines[index]) { index += 1; continue; }
      const hunk = /^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@(?: .*)?$/.exec(lines[index]);
      if (!hunk) throw new Error(lines[index].startsWith('@@ ') ? 'malformed hunk header' : 'malformed hunk body');
      index += 1; hunks += 1;
      const [, oldCount] = parseRange(hunk[1], hunk[2]); let oldRemaining = oldCount;
      const [, newCount] = parseRange(hunk[3], hunk[4]); let newRemaining = newCount;
      let markerAllowed = false;
      while (oldRemaining > 0 || newRemaining > 0) {
        const line = lines[index++];
        if (line === undefined) throw new Error('malformed hunk body');
        if (line === '\\ No newline at end of file') {
          if (!markerAllowed) throw new Error('malformed hunk body');
          markerAllowed = false; continue;
        }
        if (line.startsWith(' ')) { oldRemaining -= 1; newRemaining -= 1; }
        else if (line.startsWith('-')) oldRemaining -= 1;
        else if (line.startsWith('+')) newRemaining -= 1;
        else throw new Error('malformed hunk body');
        if (oldRemaining < 0 || newRemaining < 0) throw new Error('malformed hunk body');
        markerAllowed = true;
      }
      if (lines[index] === '\\ No newline at end of file') {
        if (!markerAllowed) throw new Error('malformed hunk body');
        index += 1;
      }
    }
    if (!hunks || targets.includes(newPath)) throw new Error('unparseable diff policy');
    targets.push(newPath);
  }
  if (!targets.length) throw new Error('patch has no file targets');
  return targets;
}
async function gitApply(cwd: string, patch: string, signal: AbortSignal, reverse = false): Promise<void> {
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  let settled = false;
  const settle = (error?: Error) => {
    if (settled) return;
    settled = true;
    if (error) reject(error);
    else resolve();
  };
  const child = spawn('git', ['apply', '--whitespace=nowarn', ...(reverse ? ['--reverse'] : []), '--'], { cwd, shell: false, stdio: ['pipe', 'ignore', 'pipe'], signal });
  child.once('error', (error) => settle(signal.aborted ? new Error('git apply aborted') : error));
  child.once('close', (code) => {
    if (code === 0) settle();
    else if (signal.aborted) settle(new Error('git apply aborted'));
    else settle(new GitApplyRejectedError());
  });
  child.stdin.once('error', (error) => settle(signal.aborted ? new Error('git apply aborted') : error));
  child.stdin.end(patch);
  return promise;
}
function exactResult(value: unknown): boolean { if (!value || typeof value !== 'object') return false; const entry = value as Record<string, unknown>; return entry.schema === 'ui-delivery-check-v1' && Number.isInteger(entry.required) && entry.required >= 1 && entry.passed === entry.required && entry.failed === 0 && entry.skipped === 0; }
async function outputPath(repo: string, task: any, checkId: string, path: string): Promise<string> { const recipe = task.approved_check_recipes.find((entry: any) => entry.id === checkId); if (!recipe?.write_paths?.includes(path)) throw new Error('artifact is not a declared check output'); return authorizePath({ repo, task: { allowed_paths: recipe.write_paths, forbidden_policy_paths: task.forbidden_policy_paths }, path }); }
async function fileDigest(path: string): Promise<string> {
  const before = await lstat(path, { bigint: true });
  if (!before.isFile() || before.isSymbolicLink() || before.nlink !== 1n || before.size < 1n) throw new Error('stale or invalid capture artifact');
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  const after = await lstat(path, { bigint: true });
  if (!after.isFile() || after.isSymbolicLink() || after.nlink !== 1n || after.dev !== before.dev || after.ino !== before.ino || after.size !== before.size) throw new Error('stale or invalid capture artifact');
  return `sha256:${hash.digest('hex')}`;
}
async function freshArtifact(path: string, before?: { hash: string }): Promise<{ hash: string }> {
  const hash = await fileDigest(path);
  if (before?.hash === hash) throw new Error('stale or invalid capture artifact');
  return { hash };
}
async function verifiedArtifact(repo: string, task: any, checkId: string, expected: any[], recipe: any): Promise<boolean> {
  if (!Array.isArray(expected) || expected.length !== recipe.artifacts.length) return false;
  const seen = new Set<string>();
  for (const artifact of recipe.artifacts) {
    const evidence = expected.find((entry: any) => entry?.path === artifact.path);
    if (!evidence || seen.has(artifact.path) || typeof evidence.hash !== 'string') return false;
    seen.add(artifact.path);
    try { const actual = await freshArtifact(await outputPath(repo, task, checkId, artifact.path)); if (actual.hash !== evidence.hash) return false; } catch { return false; }
  }
  return true;
}
async function verifiedStatus(repo: string, task: any): Promise<boolean> {
  if (task.state !== 'accepted' || task.outcome !== 'verified' || task.model_route !== '@ui_review' || !task.candidate_hash || await candidateHash({ repo, task }) !== task.candidate_hash) return false;
  try {
    const checkPolicy = { ...task, model_route: '@ui_code' };
    const checkDigest = authorizationDigest(checkPolicy);
    const captureDigest = authorizationDigest(task);
    const records: Record<string, unknown>[] = [];
    for (const line of (await readEvidence({ repo, evidenceFile: join(repo, '.omp/ui-delivery/evidence', `${task.task_id}.jsonl`) }) ?? '').split('\n')) {
      if (!line.trim()) continue;
      try {
        const record: unknown = JSON.parse(line);
        if (!record || typeof record !== 'object' || Array.isArray(record)) return false;
        records.push(record as Record<string, unknown>);
      } catch {
        return false;
      }
    }
    const boundRecords = records.filter((evidence) => evidence.taskId === task.task_id && evidence.approvedDesignHash === task.design_revision && evidence.candidateRevision === task.candidate_revision && evidence.candidateHash === task.candidate_hash);
    const latest = (operation: string, key: string, id: string) => {
      const start = boundRecords.map((record, index) => ({ record, index })).filter(({ record }) => record.operation === operation && record[key] === id && record.attemptPhase === 'started').at(-1);
      if (!start || typeof start.record.attemptId !== 'string') return undefined;
      const completion = boundRecords.slice(start.index + 1).find((record) => record.attemptPhase === 'completed' && record.attemptId === start.record.attemptId);
      return completion ? { started: start.record, completed: completion } : undefined;
    };
    const phaseVerified = (
      attempt: { started: Record<string, unknown>; completed: Record<string, unknown> } | undefined,
      route: string, digest: string, outcome: string,
    ) => attempt?.started.modelRoute === route && attempt.started.authorizationDigest === digest
      && attempt.completed.modelRoute === route && attempt.completed.authorizationDigest === digest
      && attempt.completed.outcome === outcome;
    const captureRecipes = task.capture_recipes as Array<{ id: string; check_id: string; artifacts: Array<{ path: string }> }>;
    const checkRecipes = task.approved_check_recipes as Array<{ id: string }>;
    const captureCheckIds = new Set(captureRecipes.map((recipe) => recipe.check_id));
    if (!checkRecipes.filter((recipe) => !captureCheckIds.has(recipe.id)).every((recipe) => phaseVerified(latest('ui_run_check', 'checkId', recipe.id), '@ui_code', checkDigest, 'verified'))) return false;
    for (const recipe of captureRecipes) {
      const attempt = latest('ui_capture', 'recipeId', recipe.id);
      if (!phaseVerified(attempt, '@ui_review', captureDigest, 'captured') || !Array.isArray(attempt?.completed.artifacts) || !await verifiedArtifact(repo, task, recipe.check_id, attempt.completed.artifacts, recipe)) return false;
    }
    return true;
  } catch { return false; }
}
async function resultSnapshot(path: string): Promise<{ hash: string } | undefined> { try { return { hash: await fileDigest(path) }; } catch { return undefined; } }
async function freshResult(path: string, before: { hash: string } | undefined): Promise<void> {
  const hash = await fileDigest(path);
  if (before?.hash === hash) throw new Error('stale check result');
  if (!exactResult(JSON.parse(await readFile(path, 'utf8')))) throw new Error('check result is unverified');
}
async function updateTask(repo: string, taskFile: string, task: Record<string, unknown>, signal: AbortSignal): Promise<void> {
  if (signal.aborted) throw new Error('patch aborted');
  await replaceTaskFile({ repo, taskFile, task });
}
function evidenceRecord(task: any, attemptId: string, attemptPhase: 'started' | 'completed', operation: string, selector: Record<string, string>, outcome: string, artifacts: unknown[], elapsedMs: number, checked?: any): Record<string, unknown> { return { taskId: task.task_id, approvedDesignHash: task.design_revision, candidateRevision: task.candidate_revision, candidateHash: task.candidate_hash, modelRoute: task.model_route, authorizationDigest: authorizationDigest(task), attemptId, attemptPhase, operation, ...selector, outcome, elapsedMs, artifacts, stdoutHash: checked?.stdout?.hash ?? 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', stderrHash: checked?.stderr?.hash ?? 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855' }; }
async function appendAttempt(repo: string, task: any, record: Record<string, unknown>): Promise<void> { await appendEvidence({ repo, evidenceFile: join(repo, '.omp/ui-delivery/evidence', `${task.task_id}.jsonl`), record }); }

export function registerUiDeliveryPolicy(pi: ExtensionAPI, deps: { runCheck?: typeof defaultRunCheck } = {}): void {
  if (typeof pi.on !== 'function') throw new Error('required tool_call and tool_result enforcement hooks are unavailable');
  const checkRunner = deps.runCheck ?? defaultRunCheck;
  let stitch: { authorizationDigest: string; policy: StitchPolicy; repo: string; taskFile: string } | undefined;
  pi.registerTool({ name: 'ui_delivery_status', label: 'UI delivery status', description: 'Read bounded UI delivery task status.', parameters: pi.zod.object({ taskFile: pi.zod.string().optional() }).strict(), approval: 'read', strict: true, async execute(_id, params, _signal, _onUpdate, ctx) {
    const taskFile = (params as { taskFile?: string }).taskFile;
    if (!taskFile) return result(STATUS);
    const task = await loadTask({ repo: ctx.cwd, taskFile });
    assertActiveRuntimeQualification(task);
    const digest = authorizationDigest(task);
    const approved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256 === digest;
    const registry = pi.getAllTools?.() ?? [];
    if (approved && task.state === 'approved' && stitch?.authorizationDigest !== digest) {
      const state = await loadStitchMutationState({ repo: ctx.cwd, taskId: task.task_id, authorizationDigest: digest });
      stitch = {
        authorizationDigest: digest,
        repo: ctx.cwd,
        taskFile,
        policy: createStitchPolicy({
          task,
          registry,
          state,
          persist: async (next) => updateStitchMutationState({
            repo: ctx.cwd,
            taskId: task.task_id,
            authorizationDigest: digest,
            expectedVersion: next.version,
            state: { entries: next.entries, ...(next.identities && Object.keys(next.identities).length ? { identities: next.identities } : {}), ...(next.projectId ? { projectId: next.projectId } : {}) },
          }),
        }),
      };
    }
    const verified = await verifiedStatus(ctx.cwd, task);
    return result({ extension: STATUS.extension, taskId: task.task_id, state: task.state, outcome: verified ? task.outcome : 'evidence_unverified', verified, authorizationDigest: digest, approved: approved && verified || approved && task.outcome === 'unverified' });
  } });
  pi.registerTool({
    name: 'ui_apply_patch',
    label: 'Apply approved UI patch',
    description: 'Apply an authorized non-destructive unified diff.',
    parameters: pi.zod.object({ taskFile: pi.zod.string(), patch: pi.zod.string() }).strict(),
    approval: 'write',
    strict: true,
    async execute(_id, params, signal, _onUpdate, ctx) {
      const args = params as { taskFile: string; patch: string };
      const task = await loadTask({ repo: ctx.cwd, taskFile: args.taskFile, operation: 'patch' });
      const started = performance.now();
      await prepareEvidenceDirectory(ctx.cwd);
      const changedFiles = await diffTargets(ctx.cwd, args.patch);
      for (const target of changedFiles) await authorizePath({ repo: ctx.cwd, task, path: target });
      await beginPatchJournal({
        repo: ctx.cwd,
        taskId: task.task_id,
        taskFile: args.taskFile,
        patchHash: `sha256:${createHash('sha256').update(args.patch).digest('hex')}`,
      });
      let applied = false;
      try {
        await gitApply(ctx.cwd, args.patch, signal);
        applied = true;
        const hash = await candidateHash({ repo: ctx.cwd, task });
        const updated = {
          ...task,
          state: 'candidate_ready',
          candidate_revision: `git:${hash.slice(7, 19)}`,
          candidate_hash: hash,
          outcome: 'unverified',
        };
        await updateTask(ctx.cwd, args.taskFile, updated, signal);
        const evidenceFile = join(ctx.cwd, '.omp/ui-delivery/evidence', `${task.task_id}.jsonl`);
        await appendEvidence({
          repo: ctx.cwd,
          evidenceFile,
          record: {
            taskId: task.task_id,
            approvedDesignHash: task.design_revision,
            candidateRevision: updated.candidate_revision,
            candidateHash: hash,
            modelRoute: task.model_route,
            operation: 'ui_apply_patch',
            outcome: 'mutation_unknown',
            elapsedMs: Math.max(0, Math.round(performance.now() - started)),
            artifacts: [],
            stdoutHash: `sha256:${createHash('sha256').update(args.patch).digest('hex')}`,
            stderrHash: `sha256:${createHash('sha256').update('').digest('hex')}`,
          },
        });
        await releasePatchJournal(ctx.cwd);
        return result({
          taskId: task.task_id,
          operation: 'ui_apply_patch',
          state: updated.state,
          candidateRevision: updated.candidate_revision,
          candidateHash: hash,
          authorizationDigest: authorizationDigest(updated),
          evidenceRef: `artifact://${task.task_id}/evidence.jsonl`,
          changedFiles,
        });
      } catch (error) {
        if (!applied && error instanceof GitApplyRejectedError) await releasePatchJournal(ctx.cwd);
        if (applied) {
          try {
            await gitApply(ctx.cwd, args.patch, new AbortController().signal, true);
            await updateTask(ctx.cwd, args.taskFile, task, new AbortController().signal);
            await releasePatchJournal(ctx.cwd);
          } catch {}
        }
        throw error;
      }
    },
  });
  pi.registerTool({ name: 'ui_run_check', label: 'Run approved UI check', description: 'Run a named approved check in an OS sandbox.', parameters: pi.zod.object({ taskFile: pi.zod.string(), checkId: pi.zod.string() }).strict(), approval: 'exec', strict: true, async execute(_id, params, signal, _onUpdate, ctx) {
    const args = params as { taskFile: string; checkId: string }; const task = await loadTask({ repo: ctx.cwd, taskFile: args.taskFile, operation: 'check' }); const started = performance.now();
    if (!task.candidate_revision || !task.candidate_hash || await candidateHash({ repo: ctx.cwd, task }) !== task.candidate_hash) throw new Error('candidate hash does not match current worktree');
    const recipe = task.approved_check_recipes.find((entry: any) => entry.id === args.checkId); if (!recipe) throw new Error('unknown approved check');
    if ((task.capture_recipes as Array<{ check_id: string }>).some((entry) => entry.check_id === args.checkId)) throw new Error('capture check is reviewer-only');
    const path = await outputPath(ctx.cwd, task, args.checkId, recipe.result_path); const before = await resultSnapshot(path); const attemptId = randomUUID(); const selector = { checkId: args.checkId }; let checked: any;
    await appendAttempt(ctx.cwd, task, evidenceRecord(task, attemptId, 'started', 'ui_run_check', selector, 'pending', [], 0));
    try {
      checked = await checkRunner({ repo: ctx.cwd, task, checkId: args.checkId, signal }); if (checked.exitCode !== 0) throw new Error('check result is unverified'); await freshResult(path, before);
      if (await candidateHash({ repo: ctx.cwd, task }) !== task.candidate_hash) throw new Error('candidate changed');
      await appendAttempt(ctx.cwd, task, evidenceRecord(task, attemptId, 'completed', 'ui_run_check', selector, 'verified', [], Math.max(0, Math.round(performance.now() - started)), checked));
      return result({ taskId: task.task_id, operation: 'ui_run_check', checkId: args.checkId, exitCode: checked.exitCode, stdoutHash: checked.stdout.hash, stderrHash: checked.stderr.hash });
    } catch (error) {
      try { await appendAttempt(ctx.cwd, task, evidenceRecord(task, attemptId, 'completed', 'ui_run_check', selector, 'failed', [], Math.max(0, Math.round(performance.now() - started)), checked)); } catch {}
      throw error;
    }
  } });
  pi.registerTool({ name: 'ui_capture', label: 'Capture approved UI evidence', description: 'Record only artifacts named by an approved capture recipe.', parameters: pi.zod.object({ taskFile: pi.zod.string(), recipeId: pi.zod.string() }).strict(), approval: 'exec', strict: true, async execute(_id, params, signal, _onUpdate, ctx) {
    const args = params as { taskFile: string; recipeId: string }; const task = await loadTask({ repo: ctx.cwd, taskFile: args.taskFile, operation: 'capture' }); const started = performance.now();
    if (!task.candidate_revision || !task.candidate_hash || await candidateHash({ repo: ctx.cwd, task }) !== task.candidate_hash) throw new Error('candidate hash does not match current worktree');
    const recipe = task.capture_recipes.find((entry: any) => entry.id === args.recipeId); if (!recipe) throw new Error('unknown capture recipe'); const check = task.approved_check_recipes.find((entry: any) => entry.id === recipe.check_id); if (!check) throw new Error('unknown approved check');
    const resultPath = await outputPath(ctx.cwd, task, recipe.check_id, check.result_path); const resultBefore = await resultSnapshot(resultPath); const before = await Promise.all(recipe.artifacts.map(async (artifact: any) => resultSnapshot(await outputPath(ctx.cwd, task, recipe.check_id, artifact.path))));
    const attemptId = randomUUID(); const selector = { recipeId: args.recipeId }; let checked: any;
    await appendAttempt(ctx.cwd, task, evidenceRecord(task, attemptId, 'started', 'ui_capture', selector, 'pending', [], 0));
    try {
      checked = await checkRunner({ repo: ctx.cwd, task, checkId: recipe.check_id, signal }); if (checked.exitCode !== 0) throw new Error('capture check did not succeed'); await freshResult(resultPath, resultBefore);
      const artifacts = await Promise.all(recipe.artifacts.map(async (artifact: any, index: number) => ({ path: artifact.path, ...(await freshArtifact(await outputPath(ctx.cwd, task, recipe.check_id, artifact.path), before[index])) })));
      if (await candidateHash({ repo: ctx.cwd, task }) !== task.candidate_hash) throw new Error('candidate changed');
      await appendAttempt(ctx.cwd, task, evidenceRecord(task, attemptId, 'completed', 'ui_capture', selector, 'captured', artifacts, Math.max(0, Math.round(performance.now() - started)), checked));
      return result({ taskId: task.task_id, operation: 'ui_capture', artifacts: artifacts.map((artifact) => basename(artifact.path)) });
    } catch (error) {
      try { await appendAttempt(ctx.cwd, task, evidenceRecord(task, attemptId, 'completed', 'ui_capture', selector, 'failed', [], Math.max(0, Math.round(performance.now() - started)), checked)); } catch {}
      throw error;
    }
  } });
  pi.on('tool_call', async (event) => {
    if (typeof event?.toolName !== 'string' || !event.toolName.startsWith('mcp__stitch_')) return undefined;
    try {
      if (!stitch) throw new Error('Stitch tool call is not authorized');
      const task = await loadTask({ repo: stitch.repo, taskFile: stitch.taskFile, mutation: true });
      assertActiveRuntimeQualification(task);
      if (task.state !== 'approved' || authorizationDigest(task) !== stitch.authorizationDigest || process.env.UI_DELIVERY_APPROVED_TASK_SHA256 !== stitch.authorizationDigest) throw new Error('Stitch task authorization is stale');
      const input = event.input;
      const projectId = input && typeof input === 'object' && (typeof input.projectId === 'string' ? input.projectId : typeof input.project_id === 'string' ? input.project_id : undefined);
      if (typeof event.toolCallId !== 'string' || !event.toolCallId) throw new Error('Stitch tool call identity is required');
      await stitch.policy.authorize({ projectId, toolName: event.toolName, input, toolCallId: event.toolCallId });
      return undefined;
    } catch (error) {
      return { block: true, reason: error instanceof Error ? error.message : 'Stitch tool call is not authorized' };
    }
  });
  pi.on('tool_result', async (event) => {
    if (!stitch || typeof event?.toolName !== 'string' || !event.toolName.startsWith('mcp__stitch_')) return undefined;
    const task = await loadTask({ repo: stitch.repo, taskFile: stitch.taskFile });
    assertActiveRuntimeQualification(task);
    if (authorizationDigest(task) !== stitch.authorizationDigest || process.env.UI_DELIVERY_APPROVED_TASK_SHA256 !== stitch.authorizationDigest) throw new Error('Stitch task authorization is stale');
    const details = event.details;
    const projectId = details && typeof details === 'object' && (typeof details.projectId === 'string' ? details.projectId : typeof details.project_id === 'string' ? details.project_id : undefined);
    if (typeof event.toolCallId !== 'string' || !event.toolCallId) throw new Error('Stitch tool call identity is required');
    if (stitch.policy.classify(event.toolName) === 'mutation') {
      if (event.isError) await stitch.policy.recordDispatchFailed({ toolCallId: event.toolCallId });
      else await stitch.policy.recordMutationResult({ toolName: event.toolName, toolCallId: event.toolCallId, projectId, result: details, succeeded: true });
    }
    if (stitch.policy.classify(event.toolName) === 'read' && stitch.policy.hasCorrelatedReadback(event.toolCallId)) {
      if (!projectId) throw new Error('Stitch project binding is required');
      await stitch.policy.recordReadback({ projectId, toolName: event.toolName, toolCallId: event.toolCallId, reconciled: !event.isError, observation: details });
    }
    return undefined;
  });
}
export default function uiDeliveryPolicy(pi: ExtensionAPI): void { registerUiDeliveryPolicy(pi); }
