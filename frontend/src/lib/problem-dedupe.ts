export type ProblemLikeForDedupe = {
  id?: string | number | null;
  source_id?: string | number | null;
  source_module?: string | null;
  source_kind?: string | null;
  problem_instance_id?: string | number | null;
  problem_code?: string | null;
  action_type?: string | null;
  detector_code?: string | null;
  nm_id?: string | number | null;
};

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function problemKey(item: ProblemLikeForDedupe): string {
  const problemCode = text(item.problem_code ?? item.action_type ?? item.detector_code).toLowerCase();
  const nmId = text(item.nm_id).toLowerCase();
  if (problemCode || nmId) return `problem:${problemCode}:nm:${nmId}`;
  return `source:${text(item.source_module)}:${text(item.source_id ?? item.id)}`;
}

function priority(item: ProblemLikeForDedupe): number {
  if (item.source_module === "problem_engine") return 4;
  if (item.source_kind === "dynamic_problem") return 3;
  if (item.source_kind === "checker" && item.source_module === "checker") return 2;
  return 1;
}

export function dedupeProblemItems<T extends ProblemLikeForDedupe>(items: T[]): T[] {
  const byKey = new Map<string, T>();
  for (const item of items) {
    const key = problemKey(item);
    const current = byKey.get(key);
    if (!current || priority(item) > priority(current)) {
      byKey.set(key, item);
    }
  }
  return Array.from(byKey.values());
}
