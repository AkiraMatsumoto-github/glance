import { LogIn } from "lucide-react";
import Link from "next/link";

import { HeaderNav } from "@/components/app-header";
import { buttonVariants } from "@/components/ui/button";

const NAV = [
  { href: "/demo", label: "リアルタイム" },
  { href: "/demo/seo", label: "SEO" },
  { href: "/demo/settings/sites", label: "サイト設定" },
];

// デモの画面の共通部分（docs/01_design/screen_design.md §6）。ログインせずに、ダミーの数字で画面を見る。
// ヘッダーは「Glance」「デモ」の印、デモの画面のメニュー、「ログイン」だけ（ログアウトは出さない）
export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="sticky top-0 z-40 border-b bg-surface">
        {/* スマホでは横幅が足りないので、間を詰め、「Glance」の字を出さず（「デモ」の印は残す）、「ログイン」は印だけにする */}
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-6 sm:px-6">
          <div className="flex shrink-0 items-center gap-2">
            <Link href="/demo" className="text-lg font-semibold tracking-tight max-sm:hidden">
              Glance
            </Link>
            <span className="rounded-md bg-hover px-2 py-0.5 text-xs font-medium whitespace-nowrap text-ink-2">デモ</span>
          </div>
          <HeaderNav items={NAV} />
          <Link
            href="/login"
            aria-label="ログイン"
            title="ログイン"
            className={buttonVariants({ size: "sm", className: "ml-auto shrink-0" })}
          >
            <LogIn className="sm:hidden" aria-hidden />
            <span className="max-sm:hidden">ログイン</span>
          </Link>
        </div>
      </header>
      {/* 幅と余白は、各画面が固定バー（PageBar）と中身（PageBody）で持つ */}
      <main className="flex-1">{children}</main>
    </>
  );
}
