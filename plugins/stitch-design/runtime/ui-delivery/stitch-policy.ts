import { createHash } from 'node:crypto';

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

export function hashStitchInput(input: unknown): string {
  return `sha256:${createHash('sha256').update(canonical(input)).digest('hex')}`;
}

type RegistryTool = { name: string; metadata?: { mcpServerName?: string; mcpToolName?: string; operation?: string }; inputSchema?: unknown };

export function createStitchPolicy({ task, registry, now = new Date() }: { task: Record<string, unknown>; registry: RegistryTool[]; now?: Date }) {
  let lifecycle = 'ready';
  let used = false;
  const classified = new Map(registry.filter((tool) => tool.metadata?.mcpServerName === 'stitch' && tool.inputSchema && ['read', 'mutation'].includes(tool.metadata.operation ?? '')).map((tool) => [tool.name, tool.metadata!.operation!]));
  const grant = task.stitch_grant as { project_id?: string; expires_at?: string; mutations?: { tool_name: string; input_hash: string; max_uses: number }[]; readback_tools?: string[] } | undefined;
  return {
    classify(toolName: string): 'read' | 'mutation' | 'unknown' {
      const kind = classified.get(toolName);
      return kind === 'read' || kind === 'mutation' ? kind : 'unknown';
    },
    async authorize({ projectId, toolName, input }: { projectId: string; toolName: string; input: unknown }): Promise<void> {
      if (classified.get(toolName) === 'read') return;
      if (classified.get(toolName) !== 'mutation' || !grant || task.state !== 'approved' || grant.project_id !== projectId || Date.parse(grant.expires_at ?? '') <= now.getTime() || used || lifecycle === 'mutation_unknown') throw new Error('Stitch tool call is not authorized');
      const mutation = grant.mutations?.find((entry) => entry.tool_name === toolName);
      if (!mutation || mutation.max_uses !== 1 || mutation.input_hash !== hashStitchInput(input)) throw new Error('Stitch mutation does not match one-shot grant');
      used = true;
      lifecycle = 'mutation_unknown';
    },
    recordDispatchInterrupted(): void { lifecycle = 'mutation_unknown'; },
    recordDispatchFailed(_error: Error): void { lifecycle = 'mutation_unknown'; },
    recordReadback({ toolName, reconciled }: { toolName: string; reconciled: boolean }): void {
      if (lifecycle !== 'mutation_unknown' || !grant?.readback_tools?.includes(toolName) || classified.get(toolName) !== 'read' || !reconciled) throw new Error('Stitch mutation cannot be reconciled');
      lifecycle = 'reconciled';
    },
    state(): string { return lifecycle; },
  };
}
