"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Menu } from "lucide-react";
import { useRouter } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { AppSidebar, Brand, SidebarNav } from "@/components/app-sidebar";
import { GlobalSearch } from "@/components/global-search";
import { DevBanner } from "@/components/states";
import { ThemeToggle } from "@/components/theme-toggle";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useMe } from "@/hooks/use-me";
import { api } from "@/lib/api";

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

function UserMenu() {
  const { data: me } = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  if (!me) return <div className="size-8 rounded-full bg-muted" />;
  const signOut = async () => {
    await api.post("/api/auth/logout").catch(() => undefined);
    qc.clear();
    router.replace("/login");
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label="Account">
          <Avatar className="size-8">
            <AvatarFallback className="text-xs">{initials(me.name || me.email)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="text-sm font-medium">{me.name}</div>
          <div className="truncate text-xs text-muted-foreground">{me.email}</div>
          <div className="mt-1 text-xs capitalize text-muted-foreground">{me.role === "admin" ? "Administrator" : "Standard user"}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut className="size-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <DevBanner />
      <div className="flex flex-1">
        <Suspense fallback={<div className="hidden w-60 shrink-0 border-r bg-sidebar md:block" />}>
          <AppSidebar isAdmin={isAdmin} />
        </Suspense>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur md:px-6">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-64 p-0">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <Brand />
                <Suspense fallback={null}>
                  <SidebarNav isAdmin={isAdmin} onNavigate={() => setMobileOpen(false)} />
                </Suspense>
              </SheetContent>
            </Sheet>
            <div className="flex-1">
              <Suspense fallback={null}>
                <GlobalSearch />
              </Suspense>
            </div>
            <ThemeToggle />
            <UserMenu />
          </header>
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
