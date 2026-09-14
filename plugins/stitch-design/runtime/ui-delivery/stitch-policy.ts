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
const COLLECTION_READBACK_TOOLS: Record<string, true> = {
  mcp__stitch_list_screens: true,
  mcp__stitch_list_design_systems: true,
};
const MAX_STITCH_OBSERVATION_BYTES = 1_048_576;
const recordFrom = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
const canonicalProjectId = (value: unknown): string | undefined => {
  if (typeof value !== 'string' || !value) return undefined;
  const resource = /^projects\/([^/]+)(?:\/.*)?$/.exec(value);
  return resource?.[1] ?? (!value.includes('/') ? value : undefined);
};
export function stitchProjectIdFrom(value: unknown): string | undefined {
  const record = recordFrom(value);
  if (!record) return undefined;
  for (const candidate of [record, recordFrom(record.project), recordFrom(record.structuredContent)]) {
    if (!candidate) continue;
    for (const key of ['projectId', 'project_id']) {
      const projectId = canonicalProjectId(candidate[key]);
      if (projectId) return projectId;
    }
    const projectId = canonicalProjectId(candidate.name);
    if (projectId) return projectId;
  }
  return undefined;
}
export function stitchObservation(content: unknown, details: unknown): unknown {
  const structured = recordFrom(details)?.structuredContent;
  if (recordFrom(structured)) return structured;
  if (Array.isArray(content) && content.length === 1) {
    const chunk = recordFrom(content[0]);
    if (chunk?.type === 'text' && typeof chunk.text === 'string' && Buffer.byteLength(chunk.text, 'utf8') <= MAX_STITCH_OBSERVATION_BYTES) {
      try {
        const parsed = JSON.parse(chunk.text);
        if (recordFrom(parsed)) return parsed;
      } catch {}
    }
  }
  return details;
}
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
  recordMutationResult(request: { toolName: string; toolCallId: string; projectId?: string; result?: unknown; succeeded: boolean }): Promise<void>;
  hasCorrelatedReadback(toolCallId: string): boolean;
  state(): string;
}

type MutationLifecycle = 'pending' | 'consumed' | 'reconciled';
type StitchIdentityKind = 'project' | 'screen' | 'design_system';
type StitchIdentity = { kind: StitchIdentityKind; value: string };
type StitchState = { entries?: Record<string, MutationLifecycle>; identities?: Record<string, StitchIdentity>; projectId?: string; version?: number };
type PersistedStitchState = { entries: Record<string, MutationLifecycle>; identities: Record<string, StitchIdentity>; projectId: string; version: number };
type StitchReadback = { tool_name: string; response_hash?: string; predictable_fields?: Record<string, unknown>; resource_identity?: StitchIdentityKind };
type StitchGrant = { project_id?: string; expires_at?: string; mutations?: { tool_name: string; input_hash: string; max_uses: number; expected_readback: StitchReadback }[]; readback_tools?: string[] };

export function createStitchPolicy({ task, registry, now = () => new Date(), state, persist }: { task: Record<string, unknown>; registry: unknown[]; now?: () => Date; state?: StitchState; persist?: (state: PersistedStitchState) => Promise<PersistedStitchState> }): StitchPolicy {
  const identities = new Map<string, StitchIdentity>(Object.entries(state?.identities ?? {}).filter((entry): entry is [string, StitchIdentity] => {
    const value = entry[1];
    return Boolean(value) && typeof value === 'object' && ['project', 'screen', 'design_system'].includes(value.kind) && typeof value.value === 'string' && Boolean(value.value);
  }));
  const entries = new Map<string, MutationLifecycle>(Object.entries(state?.entries ?? {}).filter((entry): entry is [string, MutationLifecycle] => ['pending', 'consumed', 'reconciled'].includes(entry[1])));
  const mutationCalls = new Map<string, string>();
  const readbacks = new Map<string, string>();
  let discoveredProjectId = typeof state?.projectId === 'string' && state.projectId ? state.projectId : undefined;
  const classified = new Map(registry.filter(isStitchRegistryTool).map((tool) => [tool.name, kindFor(tool)]).filter((entry): entry is [string, StitchToolKind] => Boolean(entry[1])));
  const grant = task.stitch_grant as StitchGrant | undefined;
  let version = Number.isInteger(state?.version) ? state.version : 0;
  const save = async (): Promise<void> => {
    if (!persist) return;
    const saved = await persist({ entries: Object.fromEntries(entries), identities: Object.fromEntries(identities), projectId: discoveredProjectId ?? '', version });
    entries.clear();
    identities.clear();
    for (const [key, value] of Object.entries(saved.entries)) if (['pending', 'consumed', 'reconciled'].includes(value)) entries.set(key, value as MutationLifecycle);
    for (const [key, value] of Object.entries(saved.identities ?? {})) if (value && typeof value === 'object' && ['project', 'screen', 'design_system'].includes(value.kind) && typeof value.value === 'string' && value.value) identities.set(key, value as StitchIdentity);
    discoveredProjectId = saved.projectId || undefined;
    version = saved.version ?? version;
  };
  const valid = (): boolean => {
    const expiresAt = Date.parse(grant?.expires_at ?? '');
    return Boolean(grant && task.state === 'approved' && Number.isFinite(expiresAt) && expiresAt > now().getTime());
  };
  const unresolvedEntry = (): string | undefined => [...entries].find(([, lifecycle]) => lifecycle !== 'reconciled')?.[0];
  const canonicalHash = (value: unknown): value is string => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value);
  const projectIdFrom = stitchProjectIdFrom;
  const identityKeys: Record<StitchIdentityKind, readonly string[]> = {
    project: ['projectId', 'project_id'],
    screen: ['screenId', 'screen_id'],
    design_system: ['designSystemId', 'design_system_id'],
  };
  const identityContainers: Record<StitchIdentityKind, readonly string[]> = {
    project: ['project'],
    screen: ['screen'],
    design_system: ['designSystem', 'design_system'],
  };
  const resourceNamePatterns: Record<StitchIdentityKind, RegExp> = {
    project: /^projects\/[^/]+$/,
    screen: /^projects\/[^/]+\/screens\/[^/]+$/,
    design_system: /^projects\/[^/]+\/designSystems\/[^/]+$/,
  };
  const identityFrom = (value: unknown, kind: StitchIdentityKind): StitchIdentity | undefined => {
    const record = recordFrom(value);
    if (!record) return undefined;
    for (const candidate of [record, ...identityContainers[kind].map((key) => recordFrom(record[key]))]) {
      if (!candidate) continue;
      for (const key of identityKeys[kind]) if (typeof candidate[key] === 'string' && candidate[key]) return { kind, value: candidate[key] };
      if (typeof candidate.name === 'string' && resourceNamePatterns[kind].test(candidate.name)) return { kind, value: candidate.name };
    }
    return undefined;
  };
  const collectionRecords = (value: unknown): Record<string, unknown>[] => {
    if (Array.isArray(value)) return value.flatMap((item) => {
      const record = recordFrom(item);
      return record ? [record, ...collectionRecords(record)] : collectionRecords(item);
    });
    const record = recordFrom(value);
    return record ? Object.values(record).flatMap(collectionRecords) : [];
  };
  const predictableFieldsMatch = (record: Record<string, unknown>, expected: StitchReadback): boolean =>
    validPredictableFields(expected.predictable_fields)
      && Object.entries(expected.predictable_fields).every(([field, value]) => Object.hasOwn(record, field) && hashStitchInput(record[field]) === hashStitchInput(value));
  const validPredictableFields = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 0 && Object.keys(value).every((field) => /^(?!project_id$)[a-z][a-z0-9_]*$/.test(field));
  const validIdentityKind = (value: unknown): value is StitchIdentityKind => value === 'project' || value === 'screen' || value === 'design_system';
  const predictableReadback = (expected: StitchReadback): boolean => expected.response_hash === undefined && validPredictableFields(expected.predictable_fields) && validIdentityKind(expected.resource_identity);
  const validExpectedReadback = (mutation: NonNullable<StitchGrant['mutations']>[number]): boolean => {
    const expected = mutation.expected_readback;
    return Boolean(READBACK_TOOLS[expected.tool_name] && grant?.readback_tools?.includes(expected.tool_name)
      && ((canonicalHash(expected.response_hash) && expected.predictable_fields === undefined && expected.resource_identity === undefined) || predictableReadback(expected)));
  };
  const matchesReadback = (mutation: NonNullable<StitchGrant['mutations']>[number], entryKey: string, observation: unknown, projectId: string): boolean => {
    const expected = mutation.expected_readback;
    if (canonicalHash(expected.response_hash)) return expected.response_hash === hashStitchInput(observation);
    const identity = identities.get(entryKey);
    const record = recordFrom(observation);
    if (!identity || !record || projectIdFrom(observation) !== projectId) return false;
    if (COLLECTION_READBACK_TOOLS[expected.tool_name]) {
      const matches = collectionRecords(observation).filter((candidate) => identityFrom(candidate, identity.kind)?.value === identity.value);
      return matches.length === 1 && predictableFieldsMatch(matches[0], expected);
    }
    return identityFrom(observation, identity.kind)?.value === identity.value && predictableFieldsMatch(record, expected);
  };
  const readbackEntryFor = (toolName: string, input: unknown, recovery: boolean): string | undefined => {
    const candidates = [...entries].flatMap(([entryKey, lifecycle]) => {
      const mutation = grant?.mutations?.find((entry) => `${entry.tool_name}:${entry.input_hash}` === entryKey);
      const identity = identities.get(entryKey);
      return lifecycle === 'consumed'
        && Boolean(mutation)
        && validExpectedReadback(mutation!)
        && mutation!.expected_readback.tool_name === toolName
        && (COLLECTION_READBACK_TOOLS[toolName] || !identity || identityFrom(input, identity.kind)?.value === identity.value)
        && (recovery ? !mutationCalls.has(entryKey) : mutationCalls.has(entryKey))
        ? [entryKey]
        : [];
    });
    return candidates.length === 1 ? candidates[0] : undefined;
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
        const activeEntry = readbackEntryFor(toolName, input, false);
        const recoveredEntry = mutationCalls.size === 0 ? readbackEntryFor(toolName, input, true) : undefined;
        const expectsReadback = [...entries].some(([entryKey, lifecycle]) => lifecycle === 'consumed' && grant?.mutations?.some((mutation) => `${mutation.tool_name}:${mutation.input_hash}` === entryKey && mutation.expected_readback.tool_name === toolName));
        if (expectsReadback && !(activeEntry ?? recoveredEntry)) throw new Error('Stitch readback does not match learned resource identity');
        if (activeEntry ?? recoveredEntry) readbacks.set(toolCallId, activeEntry ?? recoveredEntry!);
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
    async recordMutationResult({ toolName, toolCallId, projectId, result, succeeded }: { toolName: string; toolCallId: string; projectId?: string; result?: unknown; succeeded: boolean }): Promise<void> {
      const entryKey = unresolvedEntry();
      const mutation = grant?.mutations?.find((entry) => `${entry.tool_name}:${entry.input_hash}` === entryKey);
      const mutationResult = result ?? (projectId ? { projectId } : undefined);
      const learnedProjectId = projectId ?? projectIdFrom(mutationResult);
      const identityKind = mutation?.expected_readback.resource_identity;
      const identity = identityKind && validIdentityKind(identityKind) ? identityFrom(mutationResult, identityKind) : undefined;
      if (!entryKey || !mutation || mutationCalls.get(entryKey) !== toolCallId || !succeeded || !entryKey.startsWith(`${toolName}:`) || (toolName === 'mcp__stitch_create_project' && !learnedProjectId) || (identityKind !== undefined && !identity)) throw new Error('Stitch mutation cannot be reconciled');
      if (toolName === 'mcp__stitch_create_project') discoveredProjectId = learnedProjectId;
      if (identity) identities.set(entryKey, identity);
      entries.set(entryKey, 'consumed'); await save();
    },
    hasCorrelatedReadback(toolCallId: string): boolean { return readbacks.has(toolCallId); },
    async recordReadback({ projectId, toolName, toolCallId, reconciled, observation }: { projectId: string; toolName: string; toolCallId: string; reconciled: boolean; observation: unknown }): Promise<void> {
      const boundProjectId = grant?.project_id ?? discoveredProjectId;
      const entryKey = unresolvedEntry();
      const mutation = grant?.mutations?.find((entry) => `${entry.tool_name}:${entry.input_hash}` === entryKey);
      if (!entryKey || !mutation || !validExpectedReadback(mutation) || readbacks.get(toolCallId) !== entryKey || !boundProjectId || boundProjectId !== projectId || mutation.expected_readback.tool_name !== toolName || !matchesReadback(mutation, entryKey, observation, projectId) || classified.get(toolName) !== 'read' || !reconciled) throw new Error('Stitch mutation cannot be reconciled');
      readbacks.delete(toolCallId);
      entries.set(entryKey, 'reconciled'); await save();
    },
    state(): string { return unresolvedEntry() ? 'mutation_unknown' : entries.size ? 'reconciled' : 'ready'; },
  };
}
