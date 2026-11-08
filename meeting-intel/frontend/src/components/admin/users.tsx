"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Role, Scope, User } from "@/lib/types";

const NONE = "__none__";
const MIN_PASSWORD = 10;

interface FormState {
  email: string;
  name: string;
  password: string;
  role: Role;
  access_scope: Scope;
  account_label: string;
  can_download: boolean;
  is_active: boolean;
}

function initialState(u?: User): FormState {
  return {
    email: u?.email ?? "",
    name: u?.name ?? "",
    password: "",
    role: u?.role ?? "user",
    access_scope: u?.access_scope ?? "own",
    account_label: u?.account_label ?? NONE,
    can_download: u?.can_download ?? false,
    is_active: u?.is_active ?? true,
  };
}

function UserDialog({ user, open, onOpenChange }: { user?: User; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const editing = !!user;
  const [f, setF] = useState<FormState>(() => initialState(user));
  const [error, setError] = useState<string | null>(null);
  const accounts = useQuery({
    queryKey: ["meeting-accounts"],
    queryFn: () => api.get<string[]>("/api/meetings/accounts"),
    enabled: open,
    staleTime: 5 * 60_000,
  });

  const save = useMutation({
    mutationFn: async () => {
      const label = f.account_label === NONE ? null : f.account_label;
      if (editing) {
        const body: Record<string, unknown> = {
          name: f.name.trim(),
          role: f.role,
          access_scope: f.access_scope,
          account_label: label,
          can_download: f.can_download,
          is_active: f.is_active,
        };
        if (f.password) body.password = f.password;
        return api.patch<User>(`/api/users/${user.id}`, body);
      }
      return api.post<User>("/api/users", {
        email: f.email.trim(),
        name: f.name.trim(),
        password: f.password,
        role: f.role,
        access_scope: f.access_scope,
        account_label: label,
        can_download: f.can_download,
      });
    },
    onSuccess: () => {
      toast.success(editing ? "User updated" : "User created");
      void qc.invalidateQueries({ queryKey: ["users"] });
      onOpenChange(false);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "validation_error") setError("Please check the fields: a valid email and a password of at least 10 characters.");
      else setError(e instanceof ApiError ? e.message : "Could not save the user.");
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!editing && f.password.length < MIN_PASSWORD) return setError(`Password must be at least ${MIN_PASSWORD} characters.`);
    if (editing && f.password && f.password.length < MIN_PASSWORD) return setError(`Password must be at least ${MIN_PASSWORD} characters.`);
    save.mutate();
  };
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((s) => ({ ...s, [k]: v }));
  const labels = accounts.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit user" : "Add user"}</DialogTitle>
          <DialogDescription>
            Standard users see the meetings their Avoma account could see, plus meetings they attended.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="u-email">Email</Label>
            <Input id="u-email" type="email" required disabled={editing} value={f.email} onChange={(e) => set("email", e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="u-name">Name</Label>
            <Input id="u-name" required value={f.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="u-password">{editing ? "New password (leave blank to keep)" : "Password"}</Label>
            <Input
              id="u-password"
              type="password"
              autoComplete="new-password"
              required={!editing}
              minLength={editing ? undefined : MIN_PASSWORD}
              value={f.password}
              onChange={(e) => set("password", e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>Role</Label>
              <Select value={f.role} onValueChange={(v) => set("role", v as Role)}>
                <SelectTrigger aria-label="Role"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">Standard user</SelectItem>
                  <SelectItem value="admin">Administrator</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>Meeting access</Label>
              <Select value={f.access_scope} onValueChange={(v) => set("access_scope", v as Scope)}>
                <SelectTrigger aria-label="Meeting access"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="own">Own meetings</SelectItem>
                  <SelectItem value="all">All meetings</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label>Avoma account</Label>
            <Select value={f.account_label} onValueChange={(v) => set("account_label", v)}>
              <SelectTrigger aria-label="Avoma account">
                <SelectValue placeholder={accounts.isPending ? "Loading…" : "None"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None</SelectItem>
                {f.account_label !== NONE && !labels.includes(f.account_label) && (
                  <SelectItem value={f.account_label}>{f.account_label}</SelectItem>
                )}
                {labels.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <Label htmlFor="u-download" className="font-normal">Can download recordings</Label>
            <Switch id="u-download" checked={f.can_download} onCheckedChange={(v) => set("can_download", v)} />
          </div>
          {editing && (
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="u-active" className="font-normal">Account active</Label>
              <Switch id="u-active" checked={f.is_active} onCheckedChange={(v) => set("is_active", v)} />
            </div>
          )}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending && <Loader2 className="size-4 animate-spin" />} {editing ? "Save" : "Create user"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UsersSection() {
  const { data, isPending, error, refetch } = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/api/users") });
  const [dialog, setDialog] = useState<{ open: boolean; user?: User; key: number }>({ open: false, key: 0 });
  const openFor = (user?: User) => setDialog((d) => ({ open: true, user, key: d.key + 1 }));

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Users</h2>
          <p className="text-xs text-muted-foreground">Who can sign in, and which meetings they can see.</p>
        </div>
        <Button size="sm" onClick={() => openFor()}><UserPlus className="size-4" /> Add user</Button>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : data.length === 0 ? (
        <EmptyState title="No users" />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Access</TableHead>
                <TableHead>Avoma account</TableHead>
                <TableHead>Download</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last sign-in</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.name}</TableCell>
                  <TableCell className="text-muted-foreground">{u.email}</TableCell>
                  <TableCell>{u.role === "admin" ? "Administrator" : "Standard"}</TableCell>
                  <TableCell>{u.access_scope === "all" ? "All meetings" : "Own meetings"}</TableCell>
                  <TableCell className="text-muted-foreground">{u.account_label ?? "—"}</TableCell>
                  <TableCell>{u.can_download ? "Yes" : "No"}</TableCell>
                  <TableCell>
                    <Badge variant={u.is_active ? "secondary" : "outline"}>{u.is_active ? "Active" : "Disabled"}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{u.last_login_at ? formatDate(u.last_login_at) : "Never"}</TableCell>
                  <TableCell>
                    <Button size="icon" variant="ghost" aria-label={`Edit ${u.name}`} onClick={() => openFor(u)}>
                      <Pencil className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <UserDialog
        key={dialog.key}
        user={dialog.user}
        open={dialog.open}
        onOpenChange={(open) => setDialog((d) => ({ ...d, open }))}
      />
    </section>
  );
}
