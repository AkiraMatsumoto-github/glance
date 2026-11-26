import Link from "next/link";

import { HeaderNav } from "@/components/app-header";
import { buttonVariants } from "@/components/ui/button";

const NAV = [
  { href: "/demo", label: "リアルタイム" },
  { href: "/demo/seo", label: "SEO" },
];

// デモの画面の共通部分（docs/01_design/screen_design.md §6）。ログインせずに、ダミーの数字で画面を見る。
// ヘッダーは「Glance」「デモ」の印、デモの画面のメニュー、「ログイン」だけ（サイト設定とログアウトは出さない）
export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="sticky top-0 z-40 border-b bg-surface">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:gap-6 sm:px-6">
          <div className="flex items-center gap-2">
            <Link href="/demo" className="text-lg font-semibold tracking-tight">
              Glance
            </Link>
            <span className="rounded-md bg-hover px-2 py-0.5 text-xs font-medium text-ink-2">デモ</span>
          </div>
          <HeaderNav items={NAV} />
          <Link href="/login" className={buttonVariants({ size: "sm", className: "ml-auto" })}>
            ログイン
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">{children}</main>
    </>
  );
}
