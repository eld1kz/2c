import { FileStackIcon, FileTextIcon, FlaskConicalIcon, InboxIcon, LayoutDashboardIcon, LightbulbIcon, MessageSquareTextIcon, ReceiptIcon, ScrollTextIcon, ShieldCheckIcon, SunIcon, UploadIcon, UsersIcon } from "lucide-react";

export type NavGroup = "Money" | "Records" | "Safety";

export type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: "approvals";
  more?: NavGroup; // under "More", in this group: the phone menu and below the main items on desktop
};

export const GROUPS: NavGroup[] = ["Money", "Records", "Safety"];

export const NAV: NavItem[] = [
  { href: "/today", label: "Today", icon: SunIcon },
  { href: "/chat", label: "Ask", icon: MessageSquareTextIcon },
  { href: "/approvals", label: "Approvals", icon: InboxIcon, badge: "approvals" },
  { href: "/team", label: "Team", icon: UsersIcon },
  { href: "/dashboard", label: "Overview", icon: LayoutDashboardIcon, more: "Money" },
  { href: "/insights", label: "Findings", icon: LightbulbIcon, more: "Money" },
  { href: "/what-if", label: "What-if", icon: FlaskConicalIcon, more: "Money" },
  { href: "/paperwork", label: "Paperwork", icon: FileStackIcon, more: "Money" },
  { href: "/memo", label: "CFO memo", icon: FileTextIcon, more: "Money" },
  { href: "/transactions", label: "Transactions", icon: ReceiptIcon, more: "Records" },
  { href: "/upload", label: "Import", icon: UploadIcon, more: "Records" },
  { href: "/audit", label: "Audit log", icon: ScrollTextIcon, more: "Safety" },
  { href: "/trust", label: "Trust", icon: ShieldCheckIcon, more: "Safety" },
];
