import type { ExtensionAPI } from '@oh-my-pi/pi-coding-agent';
import { assertBindingCurrent } from '../runtime/ui-delivery/task.ts';
import { stitchObservation, stitchProjectIdFrom, STITCH_READ_TOOL_NAMES, type StitchPolicy } from '../runtime/ui-delivery/stitch-policy.ts';

const STITCH_READS: Record<string, true> = Object.fromEntries(STITCH_READ_TOOL_NAMES.map((name) => [name, true]));

export type StitchBinding = { authorizationDigest: string; policy: StitchPolicy; repo: string; taskFile: string; live: boolean; op: Promise<void> };
export type StitchBindingState = { current?: StitchBinding };

// Re-verifies the bound task per call; a failed object stays so late results report "stale".
async function refreshBinding(state: StitchBindingState, requireApproved: boolean): Promise<StitchBinding | undefined> {
  const binding = state.current;
  if (!binding?.live) return binding;
  try { await assertBindingCurrent({ repo: binding.repo, taskFile: binding.taskFile, digest: binding.authorizationDigest, requireApproved }); } catch {
    if (state.current === binding) binding.live = false; // only invalidate the object that actually failed
  }
  return binding;
}

export function registerStitchHooks(pi: ExtensionAPI, state: StitchBindingState): void {
  pi.on('tool_call', async (event) => {
    if (typeof event?.toolName !== 'string' || !event.toolName.startsWith('mcp__stitch_')) return undefined;
    try {
      // Reads need no grant; mutations stay fail-closed. Loop so the
      // validated binding is still the current global before authorizing.
      let binding = state.current;
      while (binding?.live && (binding = await refreshBinding(state, true)) !== state.current) { /* a concurrent rebind swapped stitch mid-refresh; revalidate it */ }
      if (!binding?.live) {
        if (STITCH_READS[event.toolName]) return undefined;
        throw new Error(binding ? 'Stitch task authorization is stale' : 'Stitch tool call is not authorized');
      }
      const input = event.input;
      const projectId = stitchProjectIdFrom(input);
      if (typeof event.toolCallId !== 'string' || !event.toolCallId) throw new Error('Stitch tool call identity is required');
      await binding.policy.authorize({ projectId, toolName: event.toolName, input, toolCallId: event.toolCallId });
      return undefined;
    } catch (error) {
      return { block: true, reason: error instanceof Error ? error.message : 'Stitch tool call is not authorized' };
    }
  });
  pi.on('tool_result', async (event) => {
    if (!state.current || typeof event?.toolName !== 'string' || !event.toolName.startsWith('mcp__stitch_')) return undefined;
    const observation = stitchObservation(event.content, event.details);
    const projectId = stitchProjectIdFrom(observation) ?? stitchProjectIdFrom(event.details) ?? stitchProjectIdFrom(event.input);
    if (typeof event.toolCallId !== 'string' || !event.toolCallId) throw new Error('Stitch tool call identity is required');
    const binding = await refreshBinding(state, false);
    if (!binding?.live) {
      // Uncorrelated reads need nothing; correlated results stay loud. A
      // successful mutation has no rollback: preserve its learned identity,
      // then settle the call ID so revival can recover the pending entry.
      if (binding && STITCH_READS[event.toolName] && !binding.policy.hasCorrelatedReadback(event.toolCallId)) return undefined;
      if (binding && !event.isError && !STITCH_READS[event.toolName]) {
        const op = binding.policy.preserveResultIdentity({ toolCallId: event.toolCallId, result: observation });
        binding.op = binding.op.then(() => op).catch(() => {});
        await op; // persistence failures still surface as a rejected result
      }
      binding?.policy.settleCorrelation(event.toolCallId);
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
