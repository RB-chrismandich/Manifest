import { canonicalJsonHash } from './evidence.ts';

export function hashStitchInput(input: unknown): string { return canonicalJsonHash(input); }
type StitchRegistryTool = { name: string; sourceInfo?: { source?: string; path?: string }; parameters?: unknown; metadata?: { mcpServerName?: string; operation?: string }; inputSchema?: unknown };
export type StitchToolKind = 'read' | 'mutation';
function isStitchRegistryTool(value: unknown): value is StitchRegistryTool { return Boolean(value) && typeof value === 'object' && 'name' in value && typeof value.name === 'string'; }
const READ_TOOLS: Record<string, true> = { get_screen: true, list_screens: true, get_project: true, list_projects: true };
const MUTATION_TOOLS: Record<string, true> = { create_project: true, generate_screen_from_text: true, edit_screens: true, generate_variants: true };
function kindFor(tool: StitchRegistryTool): StitchToolKind | undefined { const prefix = 'mcp__stitch_'; const suffix = tool.name.slice(prefix.length); if (!tool.name.startsWith(prefix) || tool.sourceInfo?.source !== 'mcp' || !String(tool.sourceInfo?.path ?? '').includes('stitch') || !(tool.parameters ?? tool.inputSchema)) return undefined; if (READ_TOOLS[suffix]) return 'read'; if (MUTATION_TOOLS[suffix]) return 'mutation'; return undefined; }

export interface StitchPolicy {
  classify(toolName: string): StitchToolKind | 'unknown';
  authorize(request: { projectId?: string; toolName: string; input: unknown }): Promise<void>;
  recordDispatchInterrupted(): Promise<void>;
  recordDispatchFailed(): Promise<void>;
  recordMutationResult(request: { toolName: string; projectId?: string; succeeded: boolean }): Promise<void>;
  recordReadback(request: { projectId: string; toolName: string; reconciled: boolean }): Promise<void>;
  state(): string;
}

type StitchState = { lifecycle?: string; used?: boolean; projectId?: string; version?: number };
type StitchGrant = { project_id?: string; expires_at?: string; mutations?: { tool_name: string; input_hash: string; max_uses: number }[]; readback_tools?: string[] };

export function createStitchPolicy({ task, registry, now = () => new Date(), state, persist }: { task: Record<string, unknown>; registry: unknown[]; now?: () => Date; state?: StitchState; persist?: (state: Required<StitchState>) => Promise<StitchState> }): StitchPolicy {
  let lifecycle = state?.lifecycle === 'mutation_unknown' || state?.lifecycle === 'reconciled' ? state.lifecycle : 'ready';
  let used = state?.used === true;
  let discoveredProjectId = typeof state?.projectId === 'string' && state.projectId ? state.projectId : undefined;
  const classified = new Map(registry.filter(isStitchRegistryTool).map((tool) => [tool.name, kindFor(tool)]).filter((entry): entry is [string, StitchToolKind] => Boolean(entry[1])));
  const grant = task.stitch_grant as StitchGrant | undefined;
  let version = Number.isInteger(state?.version) ? state.version : 0;
  const save = async (): Promise<void> => {
    if (!persist) return;
    const saved = await persist({ lifecycle, used, projectId: discoveredProjectId ?? '', version });
    lifecycle = saved.lifecycle === 'mutation_unknown' || saved.lifecycle === 'reconciled' ? saved.lifecycle : 'ready';
    used = saved.used === true;
    discoveredProjectId = saved.projectId;
    version = saved.version ?? version;
  };
  const valid = (): boolean => {
    const expiresAt = Date.parse(grant?.expires_at ?? '');
    return Boolean(grant && task.state === 'approved' && Number.isFinite(expiresAt) && expiresAt > now().getTime());
  };
  return {
    classify(toolName: string): StitchToolKind | 'unknown' { return classified.get(toolName) ?? 'unknown'; },
    async authorize({ projectId, toolName, input }: { projectId?: string; toolName: string; input: unknown }): Promise<void> {
      const kind = classified.get(toolName);
      if (!valid() || !kind) throw new Error('Stitch tool call is not authorized');
      if (kind === 'read') {
        if (toolName === 'mcp__stitch_list_projects') return;
        const boundProjectId = grant?.project_id ?? discoveredProjectId;
        if (!projectId || projectId !== boundProjectId) throw new Error('Stitch tool call is not authorized');
        return;
      }
      if (lifecycle === 'mutation_unknown') throw new Error('Stitch mutation requires readback reconciliation');
      if (used) throw new Error('Stitch mutation grant is already consumed');
      const mutation = grant?.mutations?.find((entry) => entry.tool_name === toolName);
      const creating = toolName === 'mcp__stitch_create_project';
      if (!mutation || mutation.max_uses !== 1 || mutation.input_hash !== hashStitchInput(input) || (creating ? Boolean(projectId || grant?.project_id) : !projectId || grant?.project_id !== projectId)) throw new Error('Stitch mutation does not match one-shot grant');
      used = true; lifecycle = 'mutation_unknown'; await save();
    },
    async recordDispatchInterrupted(): Promise<void> { lifecycle = 'mutation_unknown'; await save(); },
    async recordDispatchFailed(): Promise<void> { lifecycle = 'mutation_unknown'; await save(); },
    async recordMutationResult({ toolName, projectId, succeeded }: { toolName: string; projectId?: string; succeeded: boolean }): Promise<void> {
      if (lifecycle !== 'mutation_unknown' || !used || !succeeded || toolName !== 'mcp__stitch_create_project' || !projectId) throw new Error('Stitch mutation cannot be reconciled');
      discoveredProjectId = projectId; await save();
    },
    async recordReadback({ projectId, toolName, reconciled }: { projectId: string; toolName: string; reconciled: boolean }): Promise<void> {
      const boundProjectId = grant?.project_id ?? discoveredProjectId;
      if (lifecycle !== 'mutation_unknown' || !boundProjectId || boundProjectId !== projectId || !grant?.readback_tools?.includes(toolName) || classified.get(toolName) !== 'read' || !reconciled) throw new Error('Stitch mutation cannot be reconciled');
      lifecycle = 'reconciled'; await save();
    },
    state(): string { return lifecycle; },
  };
}
