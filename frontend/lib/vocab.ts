/* The glossary values, mirrored from the backend (app/common/vocab.py, docs/API_CONTRACT.md).
   State keeps the backend's values; the labels below are only how the screens word them. */

export type Confidence = "low" | "medium" | "high";
export type Phase = "ask_first_thought" | "teach" | "stress_test" | "verdict" | "exited";
export type GapType = "recognition" | "representation" | "concept" | "procedure" | "strategy_choice" | "self_correction" | "transfer";
export type Strategy = "socratic" | "visual_decomposition" | "worked_example" | "analogy" | "counterexample" | "representation_switch" | "micro_hint";
export type DecisionMode = "best_known" | "experiment" | "cold_start";
export type StepRole = "identify_quantities" | "choose_method" | "set_up" | "substitute" | "compute" | "interpret";
export type StepStatus = "correct" | "wrong" | "missing";
export type State = "strong" | "fragile" | "weak" | "untested" | "verified";

const GAP: Record<GapType, string> = {
  recognition: "Recognising the method",
  representation: "Representation",
  concept: "Concept",
  procedure: "Procedure",
  strategy_choice: "Strategy choice",
  self_correction: "Self-correction",
  transfer: "Transfer",
};
const STRATEGY: Record<Strategy, string> = {
  socratic: "Socratic questions",
  visual_decomposition: "Visual decomposition",
  worked_example: "Worked example",
  analogy: "Analogy",
  counterexample: "Counterexample",
  representation_switch: "Representation switch",
  micro_hint: "Micro-hint",
};
const ROLE: Record<StepRole, string> = {
  identify_quantities: "Identify quantities",
  choose_method: "Choose a method",
  set_up: "Set up",
  substitute: "Substitute",
  compute: "Compute",
  interpret: "Interpret",
};
const MODE: Record<DecisionMode, string> = { best_known: "Best known", experiment: "Experiment", cold_start: "First try" };

// An unknown value (the backend added one) is shown as it is rather than hidden.
export const gapLabel = (g: string) => GAP[g as GapType] ?? g;
export const strategyLabel = (s: string) => STRATEGY[s as Strategy] ?? s;
export const roleLabel = (r: string) => ROLE[r as StepRole] ?? r;
export const modeLabel = (m: string) => MODE[m as DecisionMode] ?? m;
