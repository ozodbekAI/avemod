import { useState } from "react";
import { LifeBuoy, Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { SidebarNavContent } from "@/components/SidebarNavContent";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden h-8 w-8 shrink-0 -ml-1"
          aria-label="Открыть меню"
        >
          <Menu className="h-4 w-4" />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="left"
        className="w-72 p-0 bg-sidebar text-sidebar-foreground border-sidebar-border flex flex-col"
      >
        <SheetHeader className="px-4 py-4 border-b border-sidebar-border text-left">
          <SheetTitle className="flex items-center gap-2.5 text-sm">
            <span className="rounded-md bg-primary p-1.5 text-primary-foreground">
              <LifeBuoy className="h-4 w-4" />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="font-semibold tracking-tight">Control Tower</span>
              <span className="text-[11px] font-normal text-muted-foreground">
                Операционный центр продавца
              </span>
            </span>
          </SheetTitle>
        </SheetHeader>
        <SidebarNavContent onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}
