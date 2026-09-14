import { createHash } from 'node:crypto';
import { appendFile, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { registerUiDeliveryPolicy } from './ui-delivery-policy.ts';
import { hashStitchInput } from '../runtime/ui-delivery/stitch-policy.ts';
import { candidateHash as calculateCandidateHash } from '../runtime/ui-delivery/task.ts';

export function extensionApi({ hooks = true } = {}) {
  const tools = []; const handlers = new Map();
  const schema = { strict: () => schema, optional: () => schema };
  const api = {
    zod: { object: () => schema, string: () => schema },
    registerTool: (tool) => tools.push(tool),
    getAllTools: () => [
      { name: 'mcp__stitch_get_screen', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: { type: 'object' } },
      { name: 'mcp__stitch_generate_screen_from_text', sourceInfo: { source: 'mcp', path: '<mcp:stitch>', scope: 'project', origin: 'package' }, parameters: { type: 'object' } },
    ],
  };
  if (hooks) api.on = (event, handler) => handlers.set(event, handler);
  return { tools, handlers, api };
}

export function execute(tool, args, cwd, signal = new AbortController().signal) {
  return tool.execute('call', args, signal, () => {}, { cwd });
}

const verifierSource = 'export default () => ({ schema: "ui-delivery-check-v1", required: 1, passed: 1, failed: 0, skipped: 0 });\n';
const verifierHash = `sha256:${createHash('sha256').update(verifierSource).digest('hex')}`;

export function task(overrides = {}) {
  return {
    task_id: 'task-17', state: 'approved', design_revision: 'stitch-r17',
    qualification_hash: `sha256:${'a'.repeat(64)}`, allowed_paths: ['src/Card.tsx'], forbidden_policy_paths: ['policy/baseline.json'],
    approved_check_recipes: [
      {
        id: 'unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
        backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
        write_paths: ['.ui-results/unit.json'],
        trusted_verifier: { path: '.omp/ui-delivery/verifiers/unit.mjs', sha256: verifierHash },
      },
      {
        id: 'capture-unit', argv: ['node', '--test'], cwd: '.', timeout_ms: 1_000,
        backend: 'sandbox-exec', result_path: '.ui-results/unit.json',
        write_paths: ['.ui-results/unit.json', 'evidence/page.png'],
        trusted_verifier: { path: '.omp/ui-delivery/verifiers/capture.mjs', sha256: verifierHash },
      },
    ],
    capture_recipes: [{ id: 'capture', check_id: 'capture-unit', artifacts: [{ path: 'evidence/page.png', type: 'screenshot' }] }],
    model_route: '@ui_code', repair_cycles: 0, outcome: 'unverified',
    ...overrides,
  };
}

export function taskWithStitchGrant(input) {
  return task({
    stitch_grant: {
      project_id: 'project-17', expires_at: '2030-01-01T00:00:00Z',
      mutations: [{ tool_name: 'mcp__stitch_generate_screen_from_text', input_hash: hashStitchInput(input), max_uses: 1, expected_readback: { tool_name: 'mcp__stitch_get_screen', response_hash: hashStitchInput({ projectId: 'project-17' }) } }],
      readback_tools: ['mcp__stitch_get_screen'],
    },
  });
}

export function digest(value) {
  const canonical = (entry) => Array.isArray(entry) ? entry.map(canonical)
    : entry && typeof entry === 'object' ? Object.fromEntries(Object.keys(entry).sort().map((key) => [key, canonical(entry[key])])) : entry;
  const projection = Object.fromEntries(['task_id', 'design_revision', 'qualification_hash', 'allowed_paths', 'forbidden_policy_paths', 'approved_check_recipes', 'capture_recipes', 'model_route', 'stitch_grant', 'repair_authorization']
    .filter((key) => key in value).map((key) => [key, value[key]]));
  return `sha256:${createHash('sha256').update(JSON.stringify(canonical(projection))).digest('hex')}`;
}

export async function fixture(definition = task()) {
  const repo = await mkdtemp(join(tmpdir(), 'ui-delivery-policy-'));
  await Promise.all(['src', '.ui-results', 'evidence', '.omp/ui-delivery/tasks', '.omp/ui-delivery/evidence', '.omp/ui-delivery/verifiers'].map((path) => mkdir(join(repo, path), { recursive: true })));
  await writeFile(join(repo, 'src/Card.tsx'), 'export const Card = 1;\n');
  await writeFile(join(repo, '.ui-results/unit.json'), '{"prior":true}\n');
  await writeFile(join(repo, 'evidence/page.png'), 'prior capture');
  await writeFile(join(repo, '.omp/ui-delivery/verifiers/unit.mjs'), verifierSource);
  await writeFile(join(repo, '.omp/ui-delivery/verifiers/capture.mjs'), verifierSource);
  await writeFile(join(repo, '.omp/ui-delivery/tasks/task.json'), JSON.stringify(definition));
  process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = definition.qualification_hash;
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
  const active = process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
  process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = digest(definition);
  process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = definition.qualification_hash;
  try { return await operation(); } finally {
    if (saved === undefined) delete process.env.UI_DELIVERY_APPROVED_TASK_SHA256;
    else process.env.UI_DELIVERY_APPROVED_TASK_SHA256 = saved;
    if (active === undefined) delete process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256;
    else process.env.UI_DELIVERY_ACTIVE_QUALIFICATION_SHA256 = active;
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
