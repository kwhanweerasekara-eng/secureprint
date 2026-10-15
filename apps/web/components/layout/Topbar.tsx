"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, ShieldCheck, User as UserIcon } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

const WORKSPACE_NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/analyze", label: "Analyze" },
  { href: "/jobs", label: "Jobs" },
  { href: "/tokens", label: "Tokens" },
];

const ADMIN_NAV = [
  { href: "/audit", label: "Audit" },
  { href: "/rules", label: "Rules" },
  { href: "/policies", label: "Policies" },
  { href: "/printers", label: "Printers" },
  { href: "/users", label: "Users" },
  { href: "/settings", label: "Settings" },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
}

// Frosted top navigation: logo on the left, the page links centred, the
// user menu on the right. Below lg the links move into a menu.
export function Topbar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const nav = user?.role === "ADMIN" ? [...WORKSPACE_NAV, ...ADMIN_NAV] : WORKSPACE_NAV;
  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + "/");

  async function signOut() {
    await logout();
    router.push("/login");
  }

  return (
    <header className="sticky top-0 z-20 border-b border-black/[0.06] bg-white/80 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-12 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/dashboard" className="flex shrink-0 items-center gap-2 text-foreground">
          <ShieldCheck size={18} strokeWidth={2.2} />
          <span className="text-[15px] font-semibold tracking-tight">SecurePrint</span>
        </Link>

        <nav className="hidden flex-1 items-center justify-center gap-1 lg:flex">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-full px-3 py-1 text-[13px] transition-colors",
                isActive(item.href)
                  ? "font-medium text-foreground"
                  : "text-foreground/60 hover:text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {user && (
          <div className="flex shrink-0 items-center gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger
                aria-label="Open navigation"
                className="flex h-8 w-8 items-center justify-center rounded-full text-foreground/70 outline-none hover:bg-black/5 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
              >
                <Menu size={18} />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuGroup>
                  {nav.map((item) => (
                    <DropdownMenuItem
                      key={item.href}
                      onClick={() => router.push(item.href)}
                      className={cn(isActive(item.href) && "font-medium text-primary")}
                    >
                      {item.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-2 rounded-full p-0.5 text-sm outline-none hover:bg-black/5 focus-visible:ring-2 focus-visible:ring-ring">
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-secondary text-[11px] font-medium text-foreground">
                    {initials(user.full_name || user.username)}
                  </AvatarFallback>
                </Avatar>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-60">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="flex flex-col gap-0.5">
                    <span className="font-medium text-foreground">{user.full_name || user.username}</span>
                    <span className="text-xs font-normal text-muted-foreground">{user.email}</span>
                  </DropdownMenuLabel>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuItem disabled>
                  <UserIcon />
                  {user.username} &middot; {user.role.toLowerCase()}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={signOut}>
                  <LogOut />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
    </header>
  );
}
