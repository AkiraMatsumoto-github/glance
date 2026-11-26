"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Notice } from "@/components/notice";
import { CountryBars, DeviceBars } from "@/components/realtime/breakdowns";
import { EventBars } from "@/components/realtime/event-bars";
import { MinuteChart } from "@/components/realtime/minute-chart";
import { SeriesLegend } from "@/components/realtime/series-legend";
import { SiteCards } from "@/components/realtime/site-cards";
import { TopPages } from "@/components/realtime/top-pages";
import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { formatTime, siteColor } from "@/lib/format";
import type { Metric, OkSite, Realtime } from "@/lib/types";
import { cn } from "@/lib/utils";

// リアルタイム（docs/01_design/screen_design.md §3）。開いたときと「更新」を押したときだけ取る
export default function RealtimePage() {
  const [data, setData] = useState<Realtime | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<Metric>("page_views");
  // 外したサイト。初めは全部オンで、「更新」を押しても保つ（開き直すと全部オンに戻る）
  const [unselected, setUnselected] = useState<Set<number>>(new Set());
  // 合計の線。初めはオンで、「更新」を押しても保つ
  const [showTotal, setShowTotal] = useState(true);

  const fetchRealtime = useCallback(
    () =>
      api<Realtime>("/api/realtime")
        .then(
          (result) => {
            setData(result);
            setError(null);
          },
          (e: unknown) => setError(errorMessage(e)),
        )
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    // 開いたときに1回取る
    void fetchRealtime();
  }, [fetchRealtime]);

  function refresh() {
    setLoading(true);
    void fetchRealtime();
  }

  const colors = useMemo(
    () => new Map((data?.sites ?? []).map((site, i) => [site.site_id, siteColor(i)])),
    [data],
  );
  const okSites = (data?.sites ?? []).filter((s): s is OkSite => s.status === "ok");
  const selected = okSites.filter((s) => !unselected.has(s.site_id));
  const allFailed = data !== null && data.sites.length > 0 && okSites.length === 0;

  function toggle(siteId: number, checked: boolean) {
    setUnselected((prev) => {
      const next = new Set(prev);
      if (checked) next.delete(siteId);
      else next.add(siteId);
      return next;
    });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">リアルタイム（直近30分）</h1>
        <div className="ml-auto flex items-center gap-3 text-ink-3">
          {data && <span>{formatTime(data.fetched_at)} に取得</span>}
          <Button onClick={refresh} disabled={loading}>
            {loading ? "取得中…" : "更新"}
          </Button>
        </div>
      </div>

      {error && <Notice>{error}</Notice>}

      {data === null && loading && <LoadingBlocks />}

      {data !== null && data.sites.length === 0 && (
        <div className="rounded-xl border bg-surface px-6 py-10 text-center">
          <p>サイト設定から GA4 のプロパティを追加してください。</p>
          <Link href="/settings/sites" className="mt-3 inline-block font-medium underline underline-offset-4">
            サイト設定へ
          </Link>
        </div>
      )}

      {data !== null && data.sites.length > 0 && (
        <div className={cn("space-y-5 transition-opacity", loading && "opacity-50")}>
          {allFailed && <Notice>取得できませんでした。時間をおいて更新してください。</Notice>}

          <SiteCards
            sites={data.sites}
            selected={selected}
            colors={colors}
            isSelected={(id) => okSites.some((s) => s.site_id === id) && !unselected.has(id)}
            onToggle={toggle}
            showTotal={showTotal}
            onToggleTotal={setShowTotal}
          />

          <section className="rounded-xl border bg-surface">
            <div className="border-b px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-base font-medium">分ごとの推移</h2>
                <Segmented
                  label="指標"
                  options={[
                    { value: "page_views", label: "PV" },
                    { value: "active_users", label: "UU" },
                  ]}
                  value={metric}
                  onChange={setMetric}
                />
              </div>
              {selected.length > 0 && <SeriesLegend sites={selected} colors={colors} showTotal={showTotal} />}
            </div>
            <div className="px-2 py-4">
              {selected.length > 0 ? (
                <MinuteChart sites={selected} colors={colors} metric={metric} showTotal={showTotal} />
              ) : (
                <SelectPrompt />
              )}
            </div>
          </section>

          {/* デバイス・国の内訳とイベント。サイトの選択が効く */}
          {selected.length > 0 && (
            <>
              <div className="grid gap-5 lg:grid-cols-2">
                <DeviceBars sites={selected} colors={colors} />
                <CountryBars sites={selected} colors={colors} />
              </div>
              <EventBars sites={selected} colors={colors} />
            </>
          )}

          <section className="rounded-xl border bg-surface">
            <h2 className="border-b px-4 py-3 text-base font-medium">いま見られているページ（選んだサイトの PV の上位20）</h2>
            {selected.length > 0 ? <TopPages sites={selected} colors={colors} /> : <SelectPrompt />}
          </section>
        </div>
      )}
    </div>
  );
}

function SelectPrompt() {
  return <p className="px-4 py-10 text-center text-ink-3">サイトを選んでください。</p>;
}

function LoadingBlocks() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="読み込み中">
      {[40, 72, 64].map((h) => (
        <div key={h} className="animate-pulse rounded-xl border bg-surface" style={{ height: `${h * 4}px` }} />
      ))}
    </div>
  );
}
