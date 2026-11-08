"use client";

import { Search } from "lucide-react";
import Link from "next/link";

// Replaced by the full command palette in Task 12.
export function GlobalSearch() {
  return (
    <Link
      href="/search"
      className="flex h-9 w-full max-w-md items-center gap-2 rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground hover:bg-muted"
    >
      <Search className="size-4" aria-hidden /> Search meetings, people, topics…
    </Link>
  );
}
