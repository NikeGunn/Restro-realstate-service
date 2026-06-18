import { cn } from "@/lib/utils";
import React, { useState, useRef, useEffect } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Check,
  BrainCircuit,
} from "lucide-react";

/* ------------------------------------------------------------------ *
 * ai-planning.tsx
 *
 * An "agent is thinking" timeline card. Renders a collapsible plan of
 * steps, each with its own status (pending / active / success / error),
 * optional rich content panel, icon and duration. Built for the
 * Inventory AI chat so the assistant visibly reasons through the real
 * backend stages (parse → scan stock → check alerts → review movements
 * → synthesize) before the grounded answer lands.
 *
 * Pure presentational component: all state (which steps are which
 * status, what content they show) is driven by the `steps` prop, so the
 * caller can map it straight off the real API lifecycle. No fabricated
 * data lives here.
 * ------------------------------------------------------------------ */

// Minimal counter kept from the source snippet's named `Component` export.
export const Component = () => {
  const [count, setCount] = useState(0);

  return (
    <div className={cn("flex flex-col items-center gap-4 p-4 rounded-lg")}>
      <h1 className="text-2xl font-bold mb-2">Component Example</h1>
      <h2 className="text-xl font-semibold">{count}</h2>
      <div className="flex gap-2">
        <button onClick={() => setCount((prev) => prev - 1)}>-</button>
        <button onClick={() => setCount((prev) => prev + 1)}>+</button>
      </div>
    </div>
  );
};

export type PlanStepStatus = "pending" | "active" | "success" | "error";

export interface PlanStep {
  id: string;
  title: string;
  content?: React.ReactNode;
  status: PlanStepStatus;
  icon?: React.ReactNode;
  duration?: string;
  defaultExpanded?: boolean;
}

export interface AgentPlanningProps {
  title?: string;
  steps?: PlanStep[];
  /** Start the outer card collapsed. Defaults to expanded. */
  defaultMainExpanded?: boolean;
}

const getStatusColor = (status: PlanStepStatus): string => {
  switch (status) {
    case "success":
      return "bg-emerald-100 text-emerald-600 ring-emerald-500/20 dark:bg-emerald-500/20 dark:text-emerald-400";
    case "active":
      return "bg-blue-100 text-blue-600 ring-blue-500/30 dark:bg-blue-500/20 dark:text-blue-400";
    case "error":
      return "bg-rose-100 text-rose-600 ring-rose-500/20 dark:bg-rose-500/20 dark:text-rose-400";
    case "pending":
    default:
      return "bg-secondary text-muted-foreground ring-border/50 dark:bg-secondary/50";
  }
};

export const AgentPlanning: React.FC<AgentPlanningProps> = ({
  title = "Agent is planning",
  steps = [],
  defaultMainExpanded = true,
}) => {
  const [isMainExpanded, setIsMainExpanded] = useState(defaultMainExpanded);

  // Track expanded state of individual step details.
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>(
    () =>
      steps.reduce((acc, step) => {
        acc[step.id] = step.defaultExpanded || false;
        return acc;
      }, {} as Record<string, boolean>)
  );

  const mainContentRef = useRef<HTMLDivElement>(null);

  // As the plan advances, auto-open any step that newly declares
  // defaultExpanded (e.g. the stage that just became active) without
  // clobbering steps the user has already toggled themselves. Steps the
  // user explicitly collapsed are tracked so we never re-open them.
  const userTouched = useRef<Set<string>>(new Set());
  useEffect(() => {
    setExpandedSteps((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const step of steps) {
        if (step.defaultExpanded && !userTouched.current.has(step.id) && !next[step.id]) {
          next[step.id] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [steps]);

  const toggleStep = (id: string, e: React.MouseEvent) => {
    userTouched.current.add(id);
    e.stopPropagation();
    setExpandedSteps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const hasActive = steps.some((s) => s.status === "active");
  const hasError = steps.some((s) => s.status === "error");
  const allSuccess = steps.length > 0 && steps.every((s) => s.status === "success");

  return (
    <div className="w-full font-sans text-foreground">
      {/* Outer Card Container */}
      <div className="bg-card border border-border shadow-sm rounded-xl overflow-hidden transition-all duration-300">
        {/* Top Header / Trigger Badge */}
        <div
          onClick={() => setIsMainExpanded(!isMainExpanded)}
          className={`flex items-center justify-between px-4 py-3.5 cursor-pointer transition-colors select-none
            ${isMainExpanded ? "bg-secondary/30 border-b border-border/50" : "hover:bg-secondary/30"}
          `}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-5 h-5">
              {hasActive ? (
                <Loader2 className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin" />
              ) : allSuccess ? (
                <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <BrainCircuit className="w-4 h-4 text-muted-foreground" />
              )}
            </div>

            <span className="text-[15px] font-semibold text-foreground/90 tracking-tight">
              {title}
            </span>
          </div>

          <div className="flex items-center justify-center w-6 h-6 rounded-md hover:bg-secondary text-muted-foreground transition-colors">
            {isMainExpanded ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
          </div>
        </div>

        {/* Expandable Main Timeline Area */}
        <div
          className={`grid transition-all duration-500 ease-in-out bg-card ${
            isMainExpanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
          }`}
        >
          <div className="overflow-hidden">
            <div ref={mainContentRef} className="p-5 flex flex-col">
              {steps.map((step, index) => {
                const isStepExpanded = expandedSteps[step.id];
                const isLast = index === steps.length - 1;

                return (
                  <div
                    key={step.id}
                    className={`relative flex gap-4 animate-in fade-in slide-in-from-top-4 duration-500 fill-mode-both
                      ${step.status === "pending" ? "opacity-60 grayscale" : "opacity-100"}
                    `}
                    style={{ animationDelay: `${index * 80}ms` }}
                  >
                    {/* Timeline connecting line */}
                    {!isLast && (
                      <div className="absolute left-[11px] top-7 bottom-[-10px] w-[2px] bg-border/60 z-0" />
                    )}

                    {/* Icon Column */}
                    <div className="relative z-10 flex-none w-6 h-6 mt-0.5">
                      <div
                        className={`flex items-center justify-center w-full h-full rounded-full ring-4 ring-card transition-colors duration-300
                          ${getStatusColor(step.status)}
                        `}
                      >
                        {step.status === "success" ? (
                          <Check className="w-3.5 h-3.5" />
                        ) : step.status === "active" ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          step.icon || <div className="w-1.5 h-1.5 rounded-full bg-current" />
                        )}
                      </div>
                    </div>

                    {/* Content Column */}
                    <div className="flex-1 pb-6">
                      {/* Step Header */}
                      <div
                        className={`flex items-center justify-between group rounded-md -mx-2 px-2 py-1 transition-colors
                          ${step.content ? "cursor-pointer hover:bg-secondary/50" : ""}
                        `}
                        onClick={(e) => step.content && toggleStep(step.id, e)}
                      >
                        <span
                          className={`text-[14px] tracking-tight transition-colors duration-200
                          ${
                            step.status === "active"
                              ? "text-foreground font-semibold"
                              : step.status === "error"
                              ? "text-rose-600 dark:text-rose-400 font-semibold"
                              : "text-foreground/80 group-hover:text-foreground font-medium"
                          }
                        `}
                        >
                          {step.title}
                        </span>

                        <div className="flex items-center gap-3">
                          {step.duration && (
                            <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
                              {step.duration}
                            </span>
                          )}
                          {step.content && (
                            <div className="text-muted-foreground/40 group-hover:text-muted-foreground transition-colors">
                              {isStepExpanded ? (
                                <ChevronDown className="w-4 h-4" />
                              ) : (
                                <ChevronRight className="w-4 h-4" />
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Step Expanded Content */}
                      {step.content && (
                        <div
                          className={`grid transition-all duration-300 ease-in-out ${
                            isStepExpanded
                              ? "grid-rows-[1fr] mt-2 opacity-100"
                              : "grid-rows-[0fr] mt-0 opacity-0"
                          }`}
                        >
                          <div className="overflow-hidden">
                            <div className="pt-1 pb-2">{step.content}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* a11y: announce terminal states to screen readers without visual noise */}
      <span className="sr-only" role="status" aria-live="polite">
        {hasActive ? `${title}: working` : hasError ? `${title}: needs attention` : allSuccess ? `${title}: complete` : ""}
      </span>
    </div>
  );
};

export default AgentPlanning;
