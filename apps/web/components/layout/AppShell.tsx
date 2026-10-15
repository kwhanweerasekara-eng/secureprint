"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Topbar } from "./Topbar";

// Large page heading and a muted subline for each section. The dashboard
// gets a hero line instead of its page title.
const PAGE_COPY: { prefix: string; heading?: string; subtitle: string }[] = [
  { prefix: "/dashboard", heading: "Print security, at a glance.", subtitle: "Every document checked, classified and masked before it reaches paper." },
  { prefix: "/analyze", subtitle: "Drop a PDF to see what SecurePrint finds before you print it." },
  { prefix: "/jobs", subtitle: "Every print job, its classification and what happened to it." },
  { prefix: "/tokens", subtitle: "Access tokens for the print agents on your computers." },
  { prefix: "/audit", subtitle: "A tamper-evident record of every decision in the pipeline." },
  { prefix: "/rules", subtitle: "The patterns SecurePrint uses to find sensitive data." },
  { prefix: "/policies", subtitle: "What happens to a document at each classification level." },
  { prefix: "/printers", subtitle: "Printers that receive released, checked jobs." },
  { prefix: "/users", subtitle: "People who can sign in, and what they can do." },
  { prefix: "/settings", subtitle: "Watermark, footer and retention settings." },
];

export function AppShell({
  title,
  adminOnly = false,
  children,
}: {
  title: string;
  adminOnly?: boolean;
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    } else if (!loading && adminOnly && user?.role !== "ADMIN") {
      router.replace("/dashboard");
    }
  }, [loading, user, adminOnly, router]);

  if (loading || !user || (adminOnly && user.role !== "ADMIN")) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        Loading SecurePrint&hellip;
      </div>
    );
  }

  const copy = PAGE_COPY.find((p) => pathname === p.prefix || pathname?.startsWith(p.prefix + "/"));
  const isDetail = pathname?.startsWith("/jobs/");
  const heading = (!isDetail && copy?.heading) || title;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Topbar />
      <main className="flex-1 px-4 pt-10 pb-16 sm:px-6 sm:pt-14">
        <div className="mx-auto w-full max-w-6xl">
          <header className="mb-10">
            <h1 className="text-[32px] leading-[1.1] font-semibold tracking-[-0.022em] text-foreground sm:text-[40px]">
              {heading}
            </h1>
            {copy && !isDetail && (
              <p className="mt-2 max-w-2xl text-[17px] leading-relaxed text-muted-foreground sm:text-[19px]">
                {copy.subtitle}
              </p>
            )}
          </header>
          {children}
        </div>
      </main>
    </div>
  );
}
