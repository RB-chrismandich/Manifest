import type { ExtensionAPI } from '@oh-my-pi/pi-coding-agent';
import { assertBindingCurrent } from '../runtime/ui-delivery/task.ts';
import { stitchObservation, stitchProjectIdFrom, STITCH_READ_TOOL_NAMES, type StitchPolicy } from '../runtime/ui-delivery/stitch-policy.ts';

const STITCH_READS: Record<string, true> = Object.fromEntries(STITCH_READ_TOOL_NAMES.map((name) => [name, true]));

export type StitchBinding = { authorizationDigest: string; policy: StitchPolicy; repo: string; taskFile: string; live: boolean; op: Promise<void> };
export type StitchBindingState = { current?: StitchBinding };

async function refreshBinding(binding: StitchBinding | undefined, requireApproved: boolean): Promise<StitchBinding | undefined> {
  if (!binding?.live) return binding;
  try { await assertBindingCurrent({ repo: binding.repo, taskFile: binding.taskFile, digest: binding.authorizationDigest, requireApproved }); } catch {
    binding.live = false; // mark the object that actually failed
  }
  return binding;
}

export function registerStitchHooks(pi: ExtensionAPI, state: StitchBindingState): void {
  // Routes each dispatched call's result to the binding that authorized it,
  // so rebinds mid-call never orphan in-flight grant state.
  const calls = new Map<string, StitchBinding>();
  pi.on('tool_call', async (event) => {
    if (typeof event?.toolName !== 'string' || !event.toolName.startsWith('mcp__stitch_')) return undefined;
    try {
      // Reads need no grant; mutations stay fail-closed. Revalidate until the
      // checked binding is still current; never converge → stay fail-closed.
      let binding = state.current;
      for (let attempts = 0; attempts < 3 && binding?.live; attempts += 1) {
        binding = await refreshBinding(binding, true);
        if (binding === state.current) break;
        binding = state.current;
      }
      if (!binding?.live || binding !== state.current) {
        if (STITCH_READS[event.toolName]) return undefined;
        throw new Error(binding ? 'Stitch task authorization is stale' : 'Stitch tool call is not authorized');
      }
      const input = event.input;
      const projectId = stitchProjectIdFrom(input);
      if (typeof event.toolCallId !== 'string' || !event.toolCallId) throw new Error('Stitch tool call identity is required');
      // Recheck currency after the awaited authorize: a concurrent rebind must
      // not dispatch a mutation under a superseded authorization.
      const grant = binding.policy.authorize({ projectId, toolName: event.toolName, input, toolCallId: event.toolCallId });
      await grant;
      if (binding !== state.current || !binding.live) {
        // The grant is persisted pending but no dispatch will follow — roll it
        // back to consumed or it blocks every later mutation forever.
        await binding.policy.recordDispatchInterrupted({ toolCallId: event.toolCallId });
        throw new Error('Stitch task authorization is stale');
      }
      calls.set(event.toolCallId, binding);
      return undefined;
    } catch (error) {
      return { block: true, reason: error instanceof Error ? error.message : 'Stitch tool call is not authorized' };
    }
  });
  pi.on('tool_result', async (event) => {
    if (typeof event?.toolName !== 'string' || !event.toolName.startsWith('mcp__stitch_')) return undefined;
    const routed = calls.get(event.toolCallId ?? '');
    if (event.toolCallId) calls.delete(event.toolCallId);
    let binding = routed !== undefined ? await refreshBinding(routed, false) : (state.current ? await refreshBinding(state.current, false) : undefined);
    // A dead routed binding defers to the refreshed current binding: same-task
    // revival carried its correlations, so the result can still reconcile.
    if (binding && !binding.live && state.current && state.current !== binding && state.current.authorizationDigest === binding.authorizationDigest && state.current.taskFile === binding.taskFile) binding = await refreshBinding(state.current, false);
    if (!binding) return undefined;
    const observation = stitchObservation(event.content, event.details);
    const projectId = stitchProjectIdFrom(observation) ?? stitchProjectIdFrom(event.details) ?? stitchProjectIdFrom(event.input);
    if (typeof event.toolCallId !== 'string' || !event.toolCallId) throw new Error('Stitch tool call identity is required');
    if (!binding.live) {
      // Uncorrelated reads need nothing; correlated results stay loud. A
      // successful mutation has no rollback: preserve its learned identity,
      // then settle the call ID so revival can recover the pending entry.
      if (STITCH_READS[event.toolName] && !binding.policy.hasCorrelatedReadback(event.toolCallId)) return undefined;
      if (!event.isError && !STITCH_READS[event.toolName]) {
        const op = binding.policy.preserveResultIdentity({ toolCallId: event.toolCallId, result: observation });
        binding.op = binding.op.then(() => op).then(() => undefined, () => undefined);
        await op; // persistence failures still surface as a rejected result
      }
      binding.policy.settleCorrelation(event.toolCallId);
      throw new Error('Stitch task authorization is stale');
    }
    if (binding.policy.classify(event.toolName) === 'mutation') {
      if (event.isError) await binding.policy.recordDispatchFailed({ toolCallId: event.toolCallId });
      else await binding.policy.recordMutationResult({ toolName: event.toolName, toolCallId: event.toolCallId, projectId, result: observation, succeeded: true });
    }
    if (binding.policy.classify(event.toolName) === 'read' && binding.policy.hasCorrelatedReadback(event.toolCallId)) {
      if (!projectId) throw new Error('Stitch project binding is required');
      await binding.policy.recordReadback({ projectId, toolName: event.toolName, toolCallId: event.toolCallId, reconciled: !event.isError, observation });
    }
    return undefined;
  });
}
