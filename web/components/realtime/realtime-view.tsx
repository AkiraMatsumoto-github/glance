"use client";

import { useState } from "react";

import { LoadingIndicator } from "@/components/loading-indicator";
import { Notice } from "@/components/notice";
import { PageBar, PageBody } from "@/components/page-bar";
import { CountryBars, DeviceBars } from "@/components/realtime/breakdowns";
import { EventBars } from "@/components/realtime/event-bars";
import { MinuteChart } from "@/components/realtime/minute-chart";
import { SiteCards } from "@/components/realtime/site-cards";
import { TopPages } from "@/components/realtime/top-pages";
import { Segmented } from "@/components/segmented";
import { SeriesLegend } from "@/components/series-legend";
import { EmptySites, SelectPrompt, useSiteSelection } from "@/components/site-selection";
import { Button } from "@/components/ui/button";
import { formatTime } from "@/lib/format";
import type { Metric, OkSite, Realtime } from "@/lib/types";
import { useCachedData } from "@/lib/use-data";

// 最後に取った結果（取り元ごと）。ほかの画面から戻ったときに、取り直すまでの間これを出す
const lastResults = new Map<string, Realtime>();

// リアルタイムの画面の中身（docs/01_design/screen_design.md §3）。開いたときと「更新」を押したときだけ取る。
// 本物（/api/realtime）とデモ（/api/demo/realtime）で共通にし、取り元だけを変える
export function RealtimeView({ endpoint }: { endpoint: string }) {
  const { data, error, loading, reload } = useCachedData<Realtime>(endpoint, lastResults);
  const [metric, setMetric] = useState<Metric>("page_views");
  const { colors, unselected, toggle, showTotal, setShowTotal } = useSiteSelection(data?.sites);
  const okSites = (data?.sites ?? []).filter((s): s is OkSite => s.status === "ok");
  const selected = okSites.filter((s) => !unselected.has(s.site_id));
  const allFailed = data !== null && data.sites.length > 0 && okSites.length === 0;

  return (
    <>
      {/* 「更新」は固定バーに置き、スクロールしても常に出す（screen_design.md §1・§3）。
          左は数字の期間（SEO の画面の期間と同じ位置）、右はいつ取ったかと「更新」 */}
      <PageBar>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-ink-2">直近30分</span>
          <div className="ml-auto flex items-center gap-3 text-ink-3">
            {data && <span>{formatTime(data.fetched_at)} に取得</span>}
            <Button onClick={reload} disabled={loading}>
              {loading ? "取得中…" : "更新"}
            </Button>
          </div>
        </div>
      </PageBar>
      <PageBody>
        {/* 題は、ヘッダーのメニューでどの画面かわかるので画面には出さず、読み上げ用だけにする */}
        <h1 className="sr-only">リアルタイム</h1>

        {error && <Notice>{error}</Notice>}

        {/* 取っている間は、前の数字はそのまま出し、画面の真ん中に印を出すだけにする */}
        {loading && <LoadingIndicator />}

        {data !== null && data.sites.length === 0 && (
          <EmptySites>サイト設定から GA4 のプロパティを追加してください。</EmptySites>
        )}

        {data !== null && data.sites.length > 0 && (
          <div className="space-y-5">
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
      </PageBody>
    </>
  );
}
