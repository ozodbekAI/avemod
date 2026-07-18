import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Users } from "lucide-react";

export function NoAccountSelected({ message }: { message?: string }) {
  return (
    <Alert>
      <Users className="h-4 w-4" />
      <AlertTitle>Выберите аккаунт</AlertTitle>
      <AlertDescription>
        {message ?? "Чтобы загрузить данные, выберите аккаунт в верхней панели."}
      </AlertDescription>
    </Alert>
  );
}
