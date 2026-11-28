"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "リアルタイム" },
  { href: "/seo", label: "SEO" },
  { href: "/settings/sites", label: "サイト設定" },
];

// ヘッダーのメニュー。いま開いている画面を灰色の面にする。デモのヘッダーでも使う
export function HeaderNav({ items }: { items: { href: string; label: string }[] }) {
  const pathname = usePathname();
  return (
    // 入りきらない狭い画面では、メニューの中だけ横にスクロールさせる（ページの幅は広げない）
    <nav className="flex min-w-0 items-center gap-1 overflow-x-auto text-sm">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "rounded-md px-1.5 py-1.5 whitespace-nowrap text-ink-2 hover:bg-hover hover:text-ink sm:px-3",
            pathname === item.href && "bg-hover font-medium text-ink",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

export function AppHeader() {
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
    // スクロールしても上に固定する。ダイアログ（z-50）より下、本文より上
    <header className="sticky top-0 z-40 border-b bg-surface">
      {/* スマホでは横幅が足りないので、間を詰め、「Glance」の字を出さず、「ログアウト」は印だけにする（デモのヘッダーと同じ） */}
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-6 sm:px-6">
        <Link href="/" className="text-lg font-semibold tracking-tight max-sm:hidden">
          Glance
        </Link>
        <HeaderNav items={NAV} />
        <div className="ml-auto flex items-center gap-3 text-sm">
          {me && <span className="hidden text-ink-3 sm:inline">{me.email}</span>}
          <Button variant="ghost" size="sm" onClick={logout} aria-label="ログアウト" title="ログアウト">
            <LogOut className="sm:hidden" aria-hidden />
            <span className="max-sm:hidden">ログアウト</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
