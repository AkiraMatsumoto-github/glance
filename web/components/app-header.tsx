"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "リアルタイム" },
  { href: "/settings/sites", label: "サイト設定" },
];

export function AppHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/api/me").then(setMe, () => undefined);
  }, []);

  async function logout() {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }

  return (
    <header className="border-b bg-surface">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:gap-6 sm:px-6">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Glance
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-md px-2 py-1.5 whitespace-nowrap text-ink-2 hover:bg-hover hover:text-ink sm:px-3",
                pathname === item.href && "bg-hover font-medium text-ink",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {me && <span className="hidden text-ink-3 sm:inline">{me.email}</span>}
          <Button variant="ghost" size="sm" onClick={logout}>
            ログアウト
          </Button>
        </div>
      </div>
    </header>
  );
}
