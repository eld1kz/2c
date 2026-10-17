import { LayoutDashboardIcon, MessageSquareTextIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: "approvals";
};

// Grows as Phase 5 pages ship.
export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboardIcon },
  { href: "/chat", label: "Ask the CFO", icon: MessageSquareTextIcon },
];
