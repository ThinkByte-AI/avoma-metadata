"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api.get<User>("/api/auth/me"), staleTime: 5 * 60_000 });
}

export function useAppMode() {
  return useQuery({
    queryKey: ["system-info"],
    queryFn: () => api.get<{ app_mode: "production" | "dev-mock" }>("/api/system/info", { redirectOn401: false }),
    staleTime: Infinity,
  });
}
