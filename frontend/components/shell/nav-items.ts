import { FileStackIcon, FileTextIcon, FlaskConicalIcon, InboxIcon, LayoutDashboardIcon, LightbulbIcon, MessageSquareTextIcon, ReceiptIcon, ScrollTextIcon, UploadIcon } from "lucide-react";

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
  { href: "/what-if", label: "What-if", icon: FlaskConicalIcon, more: true },
  { href: "/memo", label: "CFO memo", icon: FileTextIcon, more: true },
  { href: "/paperwork", label: "Paperwork", icon: FileStackIcon, more: true },
  { href: "/transactions", label: "Transactions", icon: ReceiptIcon, more: true },
  { href: "/upload", label: "Import", icon: UploadIcon, more: true },
  { href: "/audit", label: "Audit log", icon: ScrollTextIcon, more: true },
];
