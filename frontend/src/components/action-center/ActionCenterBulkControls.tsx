import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { PortalAssignableUser } from "@/lib/portal";

export function ActionCenterBulkControls({
  selectedCount,
  users,
  bulkAssignedUserId,
  onBulkAssignedUserIdChange,
  bulkDeadlineAt,
  onBulkDeadlineAtChange,
  bulkDismissReason,
  onBulkDismissReasonChange,
  bulkBusy,
  onApplyBulkAction,
  onClearSelection,
}: {
  selectedCount: number;
  users?: PortalAssignableUser[];
  bulkAssignedUserId: string;
  onBulkAssignedUserIdChange: (value: string) => void;
  bulkDeadlineAt: string;
  onBulkDeadlineAtChange: (value: string) => void;
  bulkDismissReason: string;
  onBulkDismissReasonChange: (value: string) => void;
  bulkBusy: string | null;
  onApplyBulkAction: (
    action: "assign" | "deadline" | "in_progress" | "dismiss",
  ) => void;
  onClearSelection: () => void;
}) {
  if (selectedCount <= 0) return null;

  return (
    <Card>
      <CardContent className="p-3">
        <div className="grid gap-2 md:flex md:flex-wrap md:items-center">
          <div className="text-sm font-medium md:mr-auto">
            Выбрано задач: {selectedCount}
          </div>
          <Select
            value={bulkAssignedUserId}
            onValueChange={onBulkAssignedUserIdChange}
          >
            <SelectTrigger className="min-h-10 w-full text-xs md:h-8 md:min-h-8 md:w-[220px]">
              <SelectValue placeholder="Ответственный" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Выберите ответственного</SelectItem>
              {users?.map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.display_name || u.full_name || u.email}
                  {u.role ? ` · ${u.role}` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 w-full md:h-8 md:min-h-8 md:w-auto"
            disabled={bulkBusy != null || bulkAssignedUserId === "__none__"}
            onClick={() => onApplyBulkAction("assign")}
          >
            Назначить
          </Button>
          <Input
            type="datetime-local"
            value={bulkDeadlineAt}
            onChange={(event) => onBulkDeadlineAtChange(event.target.value)}
            className="min-h-10 w-full text-xs md:h-8 md:min-h-8 md:w-[190px]"
          />
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 w-full md:h-8 md:min-h-8 md:w-auto"
            disabled={bulkBusy != null || !bulkDeadlineAt}
            onClick={() => onApplyBulkAction("deadline")}
          >
            Поставить срок
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 w-full md:h-8 md:min-h-8 md:w-auto"
            disabled={bulkBusy != null}
            onClick={() => onApplyBulkAction("in_progress")}
          >
            В работу
          </Button>
          <Input
            value={bulkDismissReason}
            onChange={(event) => onBulkDismissReasonChange(event.target.value)}
            placeholder="Причина отклонения"
            className="min-h-10 w-full text-xs md:h-8 md:min-h-8 md:w-[220px]"
          />
          <Button
            size="sm"
            variant="outline"
            className="min-h-10 w-full md:h-8 md:min-h-8 md:w-auto"
            disabled={bulkBusy != null || !bulkDismissReason.trim()}
            onClick={() => onApplyBulkAction("dismiss")}
          >
            Отклонить
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="min-h-10 w-full md:h-8 md:min-h-8 md:w-auto"
            disabled={bulkBusy != null}
            onClick={onClearSelection}
          >
            Снять выбор
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
