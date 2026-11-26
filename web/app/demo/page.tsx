import Link from "next/link";

import { RealtimeView } from "@/components/realtime/realtime-view";
import { buttonVariants } from "@/components/ui/button";

// デモ（docs/01_design/screen_design.md §6）。ログインせずに、ダミーの数字でリアルタイムの画面を見る。
// 数字は /api/demo/realtime（ダミーだけを返す。DB・Google・利用者のデータには触れない）から取る
export default function DemoPage() {
  return (
    <>
      <header className="sticky top-0 z-40 border-b bg-surface">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Link href="/demo" className="text-lg font-semibold tracking-tight">
            Glance
          </Link>
          <span className="rounded-md bg-hover px-2 py-0.5 text-xs font-medium text-ink-2">デモ</span>
          <Link href="/login" className={buttonVariants({ size: "sm", className: "ml-auto" })}>
            ログイン
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        <RealtimeView
          endpoint="/api/demo/realtime"
          intro={
            <p className="rounded-xl border bg-surface px-4 py-3 text-ink-2">
              デモ用のダミーの数字です（サイトも架空です）。ログインすると、あなたの GA4 の数字が出ます。
            </p>
          }
        />
      </main>
    </>
  );
}
