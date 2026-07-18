import { updateActionBySource } from "@/lib/portal";

type TaskHistoryContext = {
  accountId?: number | null;
  problemInstanceId?: string | number | null;
  comment: string;
  status?: "new" | "acknowledged" | "in_progress" | "done" | "postponed" | "ignored" | "blocked" | "resolved" | "dismissed" | "reopened";
};

export async function appendActionCenterProblemHistory({
  accountId,
  problemInstanceId,
  comment,
  status = "in_progress",
}: TaskHistoryContext) {
  if (!accountId || problemInstanceId == null || String(problemInstanceId).trim() === "") {
    return null;
  }
  return updateActionBySource({
    account_id: accountId,
    source_module: "problem_engine",
    source_id: String(problemInstanceId),
    status,
    comment,
    event_type: "comment",
  });
}
