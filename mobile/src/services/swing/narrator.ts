import {
  buildLlmInsightRequest,
  compareSwing,
  narrateComparison,
  type ComparableSwing,
  type ComparisonPacket,
  type LlmInsightRequest,
  type ProReference,
  type SwingInsight,
} from '../../domain/swingCompare';

/**
 * The screen talks to swing explanations only through this interface.
 * `templateSwingNarrator` writes the observations from the angle gaps.
 * `LlmSwingNarrator` is the same packet, for when a model is connected.
 * Build the model input with `buildLlmInsightRequest` and validate the JSON
 * back into `SwingInsight` before showing it.
 */
export interface SwingInsightNarrator {
  readonly id: string;
  narrate(packet: ComparisonPacket, reference: ProReference): SwingInsight[];
}

export const templateSwingNarrator: SwingInsightNarrator = {
  id: 'template',
  narrate(packet, reference) {
    return narrateComparison(packet, reference);
  },
};

export class LlmSwingNarrator implements SwingInsightNarrator {
  readonly id = 'llm';

  narrate(packet: ComparisonPacket, reference: ProReference): SwingInsight[] {
    const request: LlmInsightRequest = buildLlmInsightRequest(packet, reference);
    void request;
    throw new Error('LLM swing narration is not connected in this build.');
  }
}

export function compareAndNarrate(swing: ComparableSwing, reference: ProReference) {
  const packet = compareSwing(swing, reference);
  return {
    packet,
    insights: templateSwingNarrator.narrate(packet, reference),
  };
}
