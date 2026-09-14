import { createHash } from 'node:crypto';
import { appendFile, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { registerUiDeliveryPolicy } from './ui-delivery-policy.ts';
import { candidateHash as calculateCandidateHash } from '../runtime/ui-delivery/task.ts';

export function extensionApi() {
  const tools = []; const handlers = new Map();
  const schema = { strict: () => schema, optional: () => schema };
  return {
    tools, handlers,
    api: {
      zod: { object: () => schema, string: () => schema },
      registerTool: (tool) => tools.push(tool),
      on: (event, handler) => handlers.set(event, handler),
      getAllTools: () => [
        { name: 'mcp__stitch_get_screen', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: { type: 'object' } },
        { name: 'mcp__stitch_generate_screen_from_text', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: { type: 'object' } },
      ],
    },
  };
}

export function execute(tool, args, cwd, signal = new AbortController().signal) {
  return tool.execute('call', args, signal, () => {}, { cwd });
}

export function task(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [
      {
        id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
        backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
        write_paths: ['.ui-results/unit.json'],
      },
      {
        id: 'capture-unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
        backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
        write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
      },
    ],
    capture_recipes: [{ id: 'capture', check_id: 'capture-unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }] }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
    ...overrides,
  };
}

export function digest(value) {
  const canonical = (entry) => Array.isArray(entry) ? entry.map(canonical)
    : entry && typeof entry === 'object' ? Object.fromEntries(Object.keys(entry).sort().map((key) => [key, canonical(entry[key])])) : entry;
  const projection = Object.fromEntries(['task_id', 'design_revision', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant']
    .filter((key) => key in value).map((key) => [key, value[key]]));
  return `sha256:${createHash('sha256').update(JSON.stringify(canonical(projection))).digest('hex')}`;
}

export async function fixture(definition = task()) {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-policy-'));
  await Promise.all(['src', '.ui-results', 'evidence', '.omp/ui-delivery/tasks', '.omp/ui-delivery/evidence'].map((path) => mkdir(join(repo, path), { recursive: true })));
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'prior capture');
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify(definition));
  return { repo, definition };
}

export async function withoutApproval(operation) {
  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  try { return await operation(); } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
  }
}

export async function withApproval(definition, operation) {
  const saved = process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  try { return await operation(); } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
  }
}

export async function bindCandidate(repo, definition) {
  definition.candidate_hash = await calculateCandidateHash({ repo, task: definition });
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify(definition));
}

export function policyWithCheckRunner(api, runCheck) {
  return registerUiDeliveryPolicy(api, { runCheck });
}

export function success() {
  return { exitCode: 0, stdout: { hash: 'sha256:stdout' }, stderr: { hash: 'sha256:stderr' } };
}

export function evidenceRecord(definition, { attemptId, attemptPhase, operation = 'ui_run_check', outcome, artifacts = [], ...extra }) {
  const evidenceTask = operation === 'ui_run_check' ? { ...definition, model_route: '@ui_code' } : definition;
  return {
    taskId: definition.task_id, approvedDesignHash: definition.design_revision,
    candidateRevision: definition.candidate_revision, candidateHash: definition.candidate_hash,
    modelRoute: evidenceTask.model_route, authorizationDigest: digest(evidenceTask),
    attemptId, attemptPhase, operation, outcome, elapsedMs: 0, artifacts,
    stdoutHash: 'sha256:stdout', stderrHash: 'sha256:stderr', ...extra,
  };
}

export async function appendAttempt(evidenceFile, definition, { attemptId, operation, outcome, artifacts = [], ...extra }) {
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId, attemptPhase: 'started', operation, outcome: 'pending', ...extra }))}\n`);
  await appendFile(evidenceFile, `${JSON.stringify(evidenceRecord(definition, { attemptId, attemptPhase: 'completed', operation, outcome, artifacts, ...extra }))}\n`);
}

export async function appendCaptureEvidence(evidenceFile, definition, repo, attemptId = 'capture-1') {
  const page = await readFile(join(repo, 'evidence/page.png'));
  await appendAttempt(evidenceFile, definition, {
    attemptId, operation: 'ui_capture', recipeId: 'capture', outcome: 'captured',
    artifacts: [{ path: 'evidence/page.png', hash: `sha256:${createHash('sha256').update(page).digest('hex')}` }],
  });
}
