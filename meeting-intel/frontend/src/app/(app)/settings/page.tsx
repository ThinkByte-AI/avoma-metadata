"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { UsersSection } from "@/components/admin/users";
import { ErrorState, PageHeader } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/use-me";
import { cn } from "@/lib/utils";

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

function ThemeChoice() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const current = mounted ? theme ?? "system" : undefined;
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-md border p-0.5">
      {THEMES.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={current === value}
          onClick={() => setTheme(value)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded px-3 py-1 text-sm text-muted-foreground transition-colors",
            current === value && "bg-primary text-primary-foreground",
          )}
        >
          <Icon className="size-3.5" /> {label}
        </button>
      ))}
    </div>
  );
}

export default function SettingsPage() {
  const { data: me, isPending, error, refetch } = useMe();
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" />
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Profile</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
                <dt className="text-muted-foreground">Name</dt>
                <dd>{me.name}</dd>
                <dt className="text-muted-foreground">Email</dt>
                <dd>{me.email}</dd>
                <dt className="text-muted-foreground">Role</dt>
                <dd>{me.role === "admin" ? "Administrator" : "Standard user"}</dd>
                <dt className="text-muted-foreground">Meeting access</dt>
                <dd>
                  {me.role === "admin" || me.access_scope === "all"
                    ? "All meetings"
                    : `Meetings from the ${me.account_label ?? "(no)"} Avoma account, plus meetings you attended`}
                </dd>
                <dt className="text-muted-foreground">Theme</dt>
                <dd><ThemeChoice /></dd>
              </dl>
            </CardContent>
          </Card>
          {me.role === "admin" && <UsersSection />}
        </>
      )}
    </div>
  );
}
