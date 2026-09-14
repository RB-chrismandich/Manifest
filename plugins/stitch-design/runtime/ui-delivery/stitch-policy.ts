import { canonicalJsonHash } from './evidence.ts';

export function hashStitchInput(input: unknown): string { return canonicalJsonHash(input); }
type StitchRegistryTool = { name: string; sourceInfo?: { source?: string; path?: string }; parameters?: unknown; metadata?: { mcpServerName?: string; operation?: string }; inputSchema?: unknown };
export type StitchToolKind = 'read' | 'mutation';
function isStitchRegistryTool(value: unknown): value is StitchRegistryTool { return Boolean(value) && typeof value === 'object' && 'name' in value && typeof value.name === 'string'; }
const READ_TOOLS: Record<string, true> = {
  get_screen: true, list_screens: true, get_project: true, list_projects: true, list_design_systems: true, read_url_content: true,
};
const MUTATION_TOOLS: Record<string, true> = {
  create_project: true, generate_screen_from_text: true, edit_screens: true, generate_variants: true,
  upload_design_md: true, create_design_system_from_design_md: true, update_design_system: true, apply_design_system: true,
};
function kindFor(tool: StitchRegistryTool): StitchToolKind | undefined { const prefix = 'mcp__stitch_'; const suffix = tool.name.slice(prefix.length); if (!tool.name.startsWith(prefix) || tool.sourceInfo?.source !== 'mcp' || !String(tool.sourceInfo?.path ?? '').includes('stitch') || !(tool.parameters ?? tool.inputSchema)) return undefined; if (READ_TOOLS[suffix]) return 'read'; if (MUTATION_TOOLS[suffix]) return 'mutation'; return undefined; }

export interface StitchPolicy {
  classify(toolName: string): StitchToolKind | 'unknown';
  authorize(request: { projectId?: string; toolName: string; input: unknown; toolCallId: string }): Promise<void>;
  recordDispatchInterrupted(request: { toolCallId: string }): Promise<void>;
  recordDispatchFailed(request: { toolCallId: string }): Promise<void>;
  recordMutationResult(request: { toolName: string; toolCallId: string; projectId?: string; succeeded: boolean }): Promise<void>;
  recordReadback(request: { projectId: string; toolName: string; toolCallId: string; reconciled: boolean }): Promise<void>;
  state(): string;
}

type MutationLifecycle = 'pending' | 'consumed' | 'reconciled';
type StitchState = { entries?: Record<string, MutationLifecycle>; projectId?: string; version?: number };
type PersistedStitchState = { entries: Record<string, MutationLifecycle>; projectId: string; version: number };
type StitchGrant = { project_id?: string; expires_at?: string; mutations?: { tool_name: string; input_hash: string; max_uses: number }[]; readback_tools?: string[] };

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
  return {
    classify(toolName: string): StitchToolKind | 'unknown' { return classified.get(toolName) ?? 'unknown'; },
    async authorize({ projectId, toolName, input, toolCallId }: { projectId?: string; toolName: string; input: unknown; toolCallId: string }): Promise<void> {
      const kind = classified.get(toolName);
      if (!valid() || !kind) throw new Error('Stitch tool call is not authorized');
      if (kind === 'read') {
        if (toolName === 'mcp__stitch_list_projects') return;
        const boundProjectId = grant?.project_id ?? discoveredProjectId;
        if (!projectId || projectId !== boundProjectId) throw new Error('Stitch tool call is not authorized');
        const entryKey = unresolvedEntry();
        if (entryKey && entries.get(entryKey) === 'consumed' && mutationCalls.has(entryKey)) readbacks.set(toolCallId, entryKey);
        return;
      }
      const mutation = grant?.mutations?.find((entry) => entry.tool_name === toolName && entry.input_hash === hashStitchInput(input));
      const creating = toolName === 'mcp__stitch_create_project';
      const entryKey = mutation ? `${mutation.tool_name}:${mutation.input_hash}` : undefined;
      if (unresolvedEntry()) throw new Error('Stitch mutation requires readback reconciliation');
      if (entryKey && entries.has(entryKey)) throw new Error('Stitch mutation grant is already consumed');
      if (!mutation || !entryKey || mutation.max_uses !== 1 || (creating ? Boolean(projectId || grant?.project_id) : !projectId || grant?.project_id !== projectId)) throw new Error('Stitch mutation does not match one-shot grant');
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
    async recordReadback({ projectId, toolName, toolCallId, reconciled }: { projectId: string; toolName: string; toolCallId: string; reconciled: boolean }): Promise<void> {
      const boundProjectId = grant?.project_id ?? discoveredProjectId;
      const entryKey = unresolvedEntry();
      if (!entryKey || readbacks.get(toolCallId) !== entryKey || !boundProjectId || boundProjectId !== projectId || !grant?.readback_tools?.includes(toolName) || classified.get(toolName) !== 'read' || !reconciled) throw new Error('Stitch mutation cannot be reconciled');
      readbacks.delete(toolCallId);
      entries.set(entryKey, 'reconciled'); await save();
    },
    state(): string { return unresolvedEntry() ? 'mutation_unknown' : entries.size ? 'reconciled' : 'ready'; },
  };
}
