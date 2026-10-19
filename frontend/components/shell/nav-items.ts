import { FileStackIcon, FileTextIcon, FlaskConicalIcon, InboxIcon, LayoutDashboardIcon, LightbulbIcon, MessageSquareTextIcon, ReceiptIcon, ScrollTextIcon, SunIcon, UploadIcon, UsersIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: "approvals";
  more?: true; // listed under "More": in the phone menu and below the main items on desktop
};

export const NAV: NavItem[] = [
  { href: "/today", label: "Today", icon: SunIcon },
  { href: "/chat", label: "Ask", icon: MessageSquareTextIcon },
  { href: "/approvals", label: "Approvals", icon: InboxIcon, badge: "approvals" },
  { href: "/dashboard", label: "Overview", icon: LayoutDashboardIcon, more: true },
  { href: "/insights", label: "Insights", icon: LightbulbIcon, more: true },
  { href: "/what-if", label: "What-if", icon: FlaskConicalIcon, more: true },
  { href: "/memo", label: "CFO memo", icon: FileTextIcon, more: true },
  { href: "/paperwork", label: "Paperwork", icon: FileStackIcon, more: true },
  { href: "/team", label: "Team", icon: UsersIcon, more: true },
  { href: "/transactions", label: "Transactions", icon: ReceiptIcon, more: true },
  { href: "/upload", label: "Import", icon: UploadIcon, more: true },
  { href: "/audit", label: "Audit log", icon: ScrollTextIcon, more: true },
];
