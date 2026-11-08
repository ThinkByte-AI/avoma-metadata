import {
  BarChart3,
  CalendarDays,
  Database,
  LayoutDashboard,
  Search,
  Settings,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
}

// Order follows the spec's sidebar list.
export const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/search", label: "Search Meetings", icon: Search },
  { href: "/meetings", label: "All Meetings", icon: CalendarDays },
  { href: "/participants", label: "Participants", icon: Users },
  { href: "/assistant", label: "AI Assistant", icon: Sparkles },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/ingestion", label: "Data Ingestion", icon: Database, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function visibleNavItems(isAdmin: boolean): NavItem[] {
  return NAV_ITEMS.filter((i) => isAdmin || !i.adminOnly);
}
