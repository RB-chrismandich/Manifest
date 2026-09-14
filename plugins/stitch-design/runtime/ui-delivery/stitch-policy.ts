import { canonicalJsonHash } from './evidence.ts';

export function hashStitchInput(input: unknown): string { return canonicalJsonHash(input); }
type StitchRegistryTool = { name: string; sourceInfo?: { source?: string; path?: string }; parameters?: unknown; metadata?: { mcpServerName?: string; operation?: string }; inputSchema?: unknown };
export type StitchToolKind = 'read' | 'mutation';
function isStitchRegistryTool(value: unknown): value is StitchRegistryTool { return Boolean(value) && typeof value === 'object' && 'name' in value && typeof value.name === 'string'; }
export const STITCH_READ_TOOL_NAMES = [
  'mcp__stitch_get_screen', 'mcp__stitch_list_screens', 'mcp__stitch_get_project',
  'mcp__stitch_list_projects', 'mcp__stitch_list_design_systems', 'mcp__stitch_read_url_content',
] as const;
export const STITCH_MUTATION_TOOL_NAMES = [
  'mcp__stitch_create_project', 'mcp__stitch_generate_screen_from_text', 'mcp__stitch_edit_screens',
  'mcp__stitch_generate_variants', 'mcp__stitch_upload_design_md',
  'mcp__stitch_create_design_system_from_design_md', 'mcp__stitch_update_design_system',
  'mcp__stitch_apply_design_system',
] as const;
export const STITCH_READBACK_TOOL_NAMES = [
  'mcp__stitch_get_screen', 'mcp__stitch_list_screens', 'mcp__stitch_get_project',
  'mcp__stitch_list_design_systems',
] as const;
const READ_TOOLS: Record<string, true> = Object.fromEntries(STITCH_READ_TOOL_NAMES.map((name) => [name, true]));
const READBACK_TOOLS: Record<string, true> = Object.fromEntries(STITCH_READBACK_TOOL_NAMES.map((name) => [name, true]));
const MUTATION_TOOLS: Record<string, true> = Object.fromEntries(STITCH_MUTATION_TOOL_NAMES.map((name) => [name, true]));
const PROJECTLESS_READ_TOOLS: Record<string, true> = {
  mcp__stitch_list_projects: true,
  mcp__stitch_read_url_content: true,
};
function kindFor(tool: StitchRegistryTool): StitchToolKind | undefined {
  if (!tool.name.startsWith('mcp__stitch_') || tool.sourceInfo?.source !== 'mcp' || !String(tool.sourceInfo?.path ?? '').includes('stitch') || !(tool.parameters ?? tool.inputSchema)) return undefined;
  if (READ_TOOLS[tool.name]) return 'read';
  if (MUTATION_TOOLS[tool.name]) return 'mutation';
  return undefined;
}

export interface StitchPolicy {
  classify(toolName: string): StitchToolKind | 'unknown';
  authorize(request: { projectId?: string; toolName: string; input: unknown; toolCallId: string }): Promise<void>;
  recordDispatchInterrupted(request: { toolCallId: string }): Promise<void>;
  recordDispatchFailed(request: { toolCallId: string }): Promise<void>;
  recordMutationResult(request: { toolName: string; toolCallId: string; projectId?: string; succeeded: boolean }): Promise<void>;
  recordReadback(request: { projectId: string; toolName: string; toolCallId: string; reconciled: boolean; observation: unknown }): Promise<void>;
  state(): string;
}

type MutationLifecycle = 'pending' | 'consumed' | 'reconciled';
type StitchState = { entries?: Record<string, MutationLifecycle>; projectId?: string; version?: number };
type PersistedStitchState = { entries: Record<string, MutationLifecycle>; projectId: string; version: number };
type StitchReadback = { tool_name: string; response_hash?: string; predictable_fields?: Record<string, unknown> };
type StitchGrant = { project_id?: string; expires_at?: string; mutations?: { tool_name: string; input_hash: string; max_uses: number; expected_readback: StitchReadback }[]; readback_tools?: string[] };

export function createStitchPolicy({ task, registry, now = () => new Date(), state, persist }: { task: Record<string, unknown>; registry: unknown[]; now?: () => Date; state?: StitchState; persist?: (state: PersistedStitchState) => Promise<PersistedStitchState> }): StitchPolicy {
  const entries = new Map<string, MutationLifecycle>(Object.entries(state?.entries ?? {}).filter((entry): entry is [string, MutationLifecycle] => ['pending', 'consumed', 'reconciled'].includes(entry[1])));
  const mutationCalls = new Map<string, string>();
  const readbacks = new Map<string, string>();
  let discoveredProjectId = typeof state?.projectId === 'string' && state.projectId ? state.projectId : undefined;
  const classified = new Map(registry.filter(isStitchRegistryTool).map((tool) => [tool.name, kindFor(tool)]).filter((entry): entry is [string, StitchToolKind] => Boolean(entry[1])));
  const grant = task.stitch_grant as StitchGrant | undefined;
  let version = Number.isInteger(state?.version) ? state.version : 0;
  const save = async (): Promise<void> => {
    if (!persist) return;
    const saved = await persist({ entries: Object.fromEntries(entries), projectId: discoveredProjectId ?? '', version });
    entries.clear();
    for (const [key, value] of Object.entries(saved.entries)) if (['pending', 'consumed', 'reconciled'].includes(value)) entries.set(key, value as MutationLifecycle);
    discoveredProjectId = saved.projectId || undefined;
    version = saved.version ?? version;
  };
  const valid = (): boolean => {
    const expiresAt = Date.parse(grant?.expires_at ?? '');
    return Boolean(grant && task.state === 'approved' && Number.isFinite(expiresAt) && expiresAt > now().getTime());
  };
  const unresolvedEntry = (): string | undefined => [...entries].find(([, lifecycle]) => lifecycle !== 'reconciled')?.[0];
  const canonicalHash = (value: unknown): value is string => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value);
  const projectIdFrom = (value: unknown): string | undefined => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
    const record = value as Record<string, unknown>;
    return typeof record.projectId === 'string' ? record.projectId : typeof record.project_id === 'string' ? record.project_id : undefined;
  };
  const validPredictableFields = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 0 && Object.keys(value).every((field) => /^(?!project_id$)[a-z][a-z0-9_]*$/.test(field));
  const validExpectedReadback = (mutation: NonNullable<StitchGrant['mutations']>[number]): boolean => {
    const expected = mutation.expected_readback;
    if (!READBACK_TOOLS[expected.tool_name] || !grant?.readback_tools?.includes(expected.tool_name)) return false;
    return mutation.tool_name === 'mcp__stitch_create_project'
      ? expected.response_hash === undefined && validPredictableFields(expected.predictable_fields)
      : canonicalHash(expected.response_hash) && expected.predictable_fields === undefined;
  };
  const matchesReadback = (mutation: NonNullable<StitchGrant['mutations']>[number], observation: unknown, projectId: string): boolean => {
    const expected = mutation.expected_readback;
    if (mutation.tool_name !== 'mcp__stitch_create_project') return canonicalHash(expected.response_hash) && expected.response_hash === hashStitchInput(observation);
    if (!validPredictableFields(expected.predictable_fields) || typeof observation !== 'object' || !observation || Array.isArray(observation) || projectIdFrom(observation) !== projectId) return false;
    const record = observation as Record<string, unknown>;
    return Object.entries(expected.predictable_fields).every(([field, value]) => Object.hasOwn(record, field) && hashStitchInput(record[field]) === hashStitchInput(value));
  };
  return {
    classify(toolName: string): StitchToolKind | 'unknown' { return classified.get(toolName) ?? 'unknown'; },
    async authorize({ projectId, toolName, input, toolCallId }: { projectId?: string; toolName: string; input: unknown; toolCallId: string }): Promise<void> {
      const kind = classified.get(toolName);
      if (!valid() || !kind) throw new Error('Stitch tool call is not authorized');
      if (kind === 'read') {
        if (PROJECTLESS_READ_TOOLS[toolName]) return;
        const boundProjectId = grant?.project_id ?? discoveredProjectId;
        if (!projectId || projectId !== boundProjectId) throw new Error('Stitch tool call is not authorized');
        const entryKey = unresolvedEntry();
        if (entryKey && entries.get(entryKey) === 'consumed' && mutationCalls.has(entryKey)) readbacks.set(toolCallId, entryKey);
        return;
      }
      const mutation = grant?.mutations?.find((entry) => entry.tool_name === toolName && entry.input_hash === hashStitchInput(input));
      const creating = toolName === 'mcp__stitch_create_project';
      const boundProjectId = grant?.project_id ?? discoveredProjectId;
      const entryKey = mutation ? `${mutation.tool_name}:${mutation.input_hash}` : undefined;
      if (unresolvedEntry()) throw new Error('Stitch mutation requires readback reconciliation');
      if (entryKey && entries.has(entryKey)) throw new Error('Stitch mutation grant is already consumed');
      if (!mutation || !entryKey || !validExpectedReadback(mutation) || !canonicalHash(mutation.input_hash) || mutation.max_uses !== 1 || (creating ? Boolean(projectId || grant?.project_id) : !projectId || projectId !== boundProjectId)) throw new Error('Stitch mutation does not match one-shot grant');
      entries.set(entryKey, 'pending'); mutationCalls.set(entryKey, toolCallId); await save();
    },
    async recordDispatchInterrupted({ toolCallId }: { toolCallId: string }): Promise<void> {
      const entryKey = unresolvedEntry();
      if (!entryKey || mutationCalls.get(entryKey) !== toolCallId) throw new Error('Stitch mutation cannot be reconciled');
      entries.set(entryKey, 'consumed'); await save();
    },
    async recordDispatchFailed({ toolCallId }: { toolCallId: string }): Promise<void> {
      const entryKey = unresolvedEntry();
      if (!entryKey || mutationCalls.get(entryKey) !== toolCallId) throw new Error('Stitch mutation cannot be reconciled');
      entries.set(entryKey, 'consumed'); await save();
    },
    async recordMutationResult({ toolName, toolCallId, projectId, succeeded }: { toolName: string; toolCallId: string; projectId?: string; succeeded: boolean }): Promise<void> {
      const entryKey = unresolvedEntry();
      if (!entryKey || mutationCalls.get(entryKey) !== toolCallId || !succeeded || !entryKey.startsWith(`${toolName}:`) || (toolName === 'mcp__stitch_create_project' && !projectId)) throw new Error('Stitch mutation cannot be reconciled');
      if (toolName === 'mcp__stitch_create_project') discoveredProjectId = projectId;
      entries.set(entryKey, 'consumed'); await save();
    },
    async recordReadback({ projectId, toolName, toolCallId, reconciled, observation }: { projectId: string; toolName: string; toolCallId: string; reconciled: boolean; observation: unknown }): Promise<void> {
      const boundProjectId = grant?.project_id ?? discoveredProjectId;
      const entryKey = unresolvedEntry();
      const mutation = grant?.mutations?.find((entry) => `${entry.tool_name}:${entry.input_hash}` === entryKey);
      if (!entryKey || !mutation || !validExpectedReadback(mutation) || readbacks.get(toolCallId) !== entryKey || !boundProjectId || boundProjectId !== projectId || mutation.expected_readback.tool_name !== toolName || !matchesReadback(mutation, observation, projectId) || classified.get(toolName) !== 'read' || !reconciled) throw new Error('Stitch mutation cannot be reconciled');
      readbacks.delete(toolCallId);
      entries.set(entryKey, 'reconciled'); await save();
    },
    state(): string { return unresolvedEntry() ? 'mutation_unknown' : entries.size ? 'reconciled' : 'ready'; },
  };
}
