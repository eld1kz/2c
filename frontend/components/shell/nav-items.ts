import { InboxIcon, LayoutDashboardIcon, LightbulbIcon, MessageSquareTextIcon, ScrollTextIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: "approvals";
  more?: true; // on phones, listed under "More" instead of the tab bar
};

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboardIcon },
  { href: "/chat", label: "Ask the CFO", icon: MessageSquareTextIcon },
  { href: "/approvals", label: "Approvals", icon: InboxIcon, badge: "approvals" },
  { href: "/insights", label: "Insights", icon: LightbulbIcon },
  { href: "/audit", label: "Audit log", icon: ScrollTextIcon, more: true },
];
