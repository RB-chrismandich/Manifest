import { canonicalJsonHash } from './evidence.ts';

export function hashStitchInput(input: unknown): string { return canonicalJsonHash(input); }
type StitchRegistryTool = { name: string; sourceInfo?: { source?: string; path?: string }; parameters?: unknown; metadata?: { mcpServerName?: string; operation?: string }; inputSchema?: unknown };
export type StitchToolKind = 'read' | 'mutation';
function isStitchRegistryTool(value: unknown): value is StitchRegistryTool { return Boolean(value) && typeof value === 'object' && 'name' in value && typeof value.name === 'string'; }
const READ_TOOLS = new Set(['get_screen', 'list_screens', 'get_project', 'list_projects']);
const MUTATION_TOOLS = new Set(['edit_screen', 'create_screen', 'delete_screen', 'update_project']);
function kindFor(tool: StitchRegistryTool): StitchToolKind | undefined { const suffix = tool.name.replace(/^mcp__stitch__/, ''); if (!tool.name.startsWith('mcp__stitch__') || tool.sourceInfo?.source !== 'mcp' || !String(tool.sourceInfo?.path ?? '').includes('stitch') || !(tool.parameters ?? tool.inputSchema)) return undefined; if (READ_TOOLS.has(suffix)) return 'read'; if (MUTATION_TOOLS.has(suffix)) return 'mutation'; return undefined; }

export interface StitchPolicy {
  classify(toolName: string): StitchToolKind | 'unknown';
  authorize(request: { projectId: string; toolName: string; input: unknown }): Promise<void>;
  recordDispatchInterrupted(): void;
  recordDispatchFailed(): void;
  recordReadback(request: { toolName: string; reconciled: boolean }): void;
  state(): string;
}

export function createStitchPolicy({ task, registry, now = () => new Date() }: { task: Record<string, unknown>; registry: unknown[]; now?: () => Date }): StitchPolicy {
  let lifecycle = 'ready'; let used = false; const classified = new Map(registry.filter(isStitchRegistryTool).map((tool) => [tool.name, kindFor(tool)]).filter((entry): entry is [string, StitchToolKind] => Boolean(entry[1])));
  const grant = task.stitch_grant as { project_id?: string; expires_at?: string; mutations?: { tool_name: string; input_hash: string; max_uses: number }[]; readback_tools?: string[] } | undefined;
  return {
    classify(toolName: string): Kind | 'unknown' { return classified.get(toolName) ?? 'unknown'; },
    async authorize({ projectId, toolName, input }: { projectId: string; toolName: string; input: unknown }): Promise<void> {
      if (classified.get(toolName) === 'read') return;
      if (lifecycle === 'mutation_unknown') throw new Error('Stitch mutation requires readback reconciliation');
      if (used) throw new Error('Stitch mutation grant is already consumed');
      if (classified.get(toolName) !== 'mutation' || !grant || task.state !== 'approved' || grant.project_id !== projectId || Date.parse(grant.expires_at ?? '') <= now().getTime()) throw new Error('Stitch tool call is not authorized');
      const mutation = grant.mutations?.find((entry) => entry.tool_name === toolName); if (!mutation || mutation.max_uses !== 1 || mutation.input_hash !== hashStitchInput(input)) throw new Error('Stitch mutation does not match one-shot grant'); used = true; lifecycle = 'mutation_unknown';
    },
    recordDispatchInterrupted(): void { lifecycle = 'mutation_unknown'; }, recordDispatchFailed(): void { lifecycle = 'mutation_unknown'; },
    recordReadback({ toolName, reconciled }: { toolName: string; reconciled: boolean }): void { if (lifecycle !== 'mutation_unknown' || !grant?.readback_tools?.includes(toolName) || classified.get(toolName) !== 'read' || !reconciled) throw new Error('Stitch mutation cannot be reconciled'); lifecycle = 'reconciled'; },
    state(): string { return lifecycle; },
  };
}
