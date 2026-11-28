"use client";

import Link from "next/link";
import { type ReactNode, useMemo, useState } from "react";

import { siteColor } from "@/lib/format";

// リアルタイムと SEO の画面で共通の、サイトの選び方と色（docs/01_design/screen_design.md §3・§7）

// サイトの色と、選んでいるサイト・合計の線。外したサイトと合計の線は、条件を変えても「更新」を押しても保つ
// （開き直すと全部オンに戻る）
export function useSiteSelection(sites: { site_id: number }[] | undefined) {
  const colors = useMemo(() => new Map((sites ?? []).map((site, i) => [site.site_id, siteColor(i)])), [sites]);
  const [unselected, setUnselected] = useState<Set<number>>(new Set());
  const [showTotal, setShowTotal] = useState(true);

  function toggle(siteId: number, checked: boolean) {
    setUnselected((prev) => {
      const next = new Set(prev);
      if (checked) next.delete(siteId);
      else next.add(siteId);
      return next;
    });
  }

  return { colors, unselected, toggle, showTotal, setShowTotal };
}

// サイトを1つも選んでいないときの、グラフ・表の代わり
export function SelectPrompt() {
  return <p className="px-4 py-10 text-center text-ink-3">サイトを選んでください。</p>;
}

// 出すサイトがないとき。サイト設定へ案内する
export function EmptySites({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border bg-surface px-6 py-10 text-center">
      <p>{children}</p>
      <Link href="/settings/sites" className="mt-3 inline-block font-medium underline underline-offset-4">
        サイト設定へ
      </Link>
    </div>
  );
}
