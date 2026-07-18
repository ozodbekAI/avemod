import type { ReactNode } from "react";
import { Sheet } from "@/components/ui/sheet";

type ActionCenterTaskDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
};

export function ActionCenterTaskDrawer({
  open,
  onOpenChange,
  children,
}: ActionCenterTaskDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {children}
    </Sheet>
  );
}
