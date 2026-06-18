import type { PlanStepStatus } from '@/components/ui/ai-planning'

export type AgentPhase = 'planning' | 'done' | 'error'

/**
 * Pure status derivation for one stage of the Inventory AI planning timeline,
 * given the turn phase and how far the planning stepper has advanced.
 *
 * This is the failure-prone bit that must never mislabel a stage — e.g. show
 * "active" after the answer already arrived, or mark the wrong stage as the
 * failure. Kept React-free so it can be unit-tested in the node test env.
 */
export function deriveStageStatus(
  phase: AgentPhase,
  activeStage: number,
  idx: number,
  total: number,
): PlanStepStatus {
  if (phase === 'done') return 'success'
  // On error, every lead-up stage succeeded (the server did fetch context);
  // only the final synthesize stage carries the failure.
  if (phase === 'error') return idx < total - 1 ? 'success' : 'error'
  // planning
  if (idx < activeStage) return 'success'
  if (idx === activeStage) return 'active'
  return 'pending'
}
