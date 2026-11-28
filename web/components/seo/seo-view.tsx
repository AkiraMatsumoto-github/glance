"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { LoadingIndicator } from "@/components/loading-indicator";
import { Notice } from "@/components/notice";
import { PageBar, PageBody } from "@/components/page-bar";
import { Segmented } from "@/components/segmented";
import { COMPARE_OPACITY, type DateRow, DateLineChart, type Series } from "@/components/seo/date-line-chart";
import {
  METRIC_LABELS,
  type SeoMetric,
  addTotals,
  formatMetric,
  formatMetricAxis,
  metricValue,
} from "@/lib/seo-metrics";
import { IndexSection } from "@/components/seo/index-section";
import { RankingTable } from "@/components/seo/ranking-table";
import { SeoCards } from "@/components/seo/seo-cards";
import { SeriesLegend } from "@/components/series-legend";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api, errorMessage } from "@/lib/api";
import { countDays, formatDate, formatRange, siteColor } from "@/lib/format";
import type { Seo, SeoCompareName, SeoEngine, SeoPeriodName, SeoSite } from "@/lib/types";

// 最後に取った結果（URL ごと）。ほかの画面から戻ったときや条件を変えたときに、取り終えるまでの間これを出す
// （ブラウザのメモリだけ。読み込み直すと消える）
const lastResults = new Map<string, Seo>();

const PERIODS: { value: SeoPeriodName; label: string }[] = [
  { value: "last_7_days", label: "直近7日" },
  { value: "last_28_days", label: "直近28日" },
  { value: "this_month", label: "今月" },
  { value: "last_month", label: "先月" },
  { value: "custom", label: "指定" },
];

const COMPARES: { value: SeoCompareName; label: string }[] = [
  { value: "previous_period", label: "前の期間" },
  { value: "previous_year", label: "前年" },
  { value: "none", label: "比べない" },
];


const ENGINE_LABELS: Record<SeoEngine, string> = { google: "Search Console", bing: "Bing" };

const TOTAL_KEY = "total";
const TOTAL_COLOR = "var(--ink)"; // 合計はサイトの色を使わず墨色（design_guideline.md §2.2）

const CONTROL = "h-8 rounded-md border bg-surface px-2 text-sm text-ink";

// 指定の期間は、始まりと終わりがそろうまで取らない
function buildUrl(endpoint: string, engine: SeoEngine, period: SeoPeriodName, compare: SeoCompareName, start: string, end: string) {
  const params = new URLSearchParams({ engine, period, compare });
  if (period === "custom") {
    if (!start || !end) return null;
    params.set("start", start);
    params.set("end", end);
  }
  return `${endpoint}?${params}`;
}

// 日ごとの推移の行。比べる期間は、期間の何日目かでそろえて同じ行に入れる
function dailyRows(sites: SeoSite[], metric: SeoMetric, withCompare: boolean): DateRow[] {
  const days = sites[0]?.daily ?? [];
  return days.map((day, i) => {
    const row: DateRow = { date: day.date, compare_date: withCompare ? sites[0].compare_daily?.[i]?.date : null };
    for (const site of sites) {
      row[`s${site.site_id}`] = metricValue(site.daily[i], metric);
      const before = site.compare_daily?.[i];
      if (withCompare && before) row[`s${site.site_id}_cmp`] = metricValue(before, metric);
    }
    row[TOTAL_KEY] = metricValue(addTotals(sites.map((s) => s.daily[i])), metric);
    if (row.compare_date) {
      row[`${TOTAL_KEY}_cmp`] = metricValue(addTotals(sites.flatMap((s) => s.compare_daily?.[i] ?? [])), metric);
    }
    return row;
  });
}

// SEO の画面の中身（docs/01_design/screen_design.md §7）。条件を変えるたびに取る。
// 本物（/api/seo。2番目の段階で作る）とデモ（/api/demo/seo）で共通にし、取り元だけを変える
export function SeoView({ endpoint }: { endpoint: string }) {
  const [engine, setEngine] = useState<SeoEngine>("google");
  const [period, setPeriod] = useState<SeoPeriodName>("last_28_days");
  const [compare, setCompare] = useState<SeoCompareName>("previous_period");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const url = buildUrl(endpoint, engine, period, compare, start, end);

  const [data, setData] = useState<Seo | null>(() => (url && lastResults.get(url)) || null);
  // 「更新」を押した回数。同じ条件でも取り直すため、取る条件の印に入れる
  const [reloads, setReloads] = useState(0);
  const request = url === null ? null : `${url}#${reloads}`;
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loading = request !== null && request !== done;

  const [metric, setMetric] = useState<SeoMetric>("clicks");
  // 外したサイトと合計の線。条件を変えても保つ（開き直すと全部オンに戻る）
  const [unselected, setUnselected] = useState<Set<number>>(new Set());
  const [showTotal, setShowTotal] = useState(true);
  // 日ごとの推移に比べる期間の破線を重ねるか。線が倍になって読みにくくなるので、初めは重ねない
  const [overlayCompare, setOverlayCompare] = useState(false);

  // 開いたとき・条件を変えたとき・「更新」を押したときに取る
  useEffect(() => {
    if (url === null) return;
    const key = `${url}#${reloads}`;
    // 条件を続けて変えたときは、最後の条件の結果だけを出す
    let cancelled = false;
    api<Seo>(url).then(
      (result) => {
        if (cancelled) return;
        lastResults.set(url, result);
        setData(result);
        setError(null);
        setDone(key);
      },
      (e: unknown) => {
        if (cancelled) return;
        setError(errorMessage(e));
        setDone(key);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url, reloads]);

  function choosePeriod(value: SeoPeriodName) {
    // 指定に切り替えたときは、いま出している期間を初めの値にする
    if (value === "custom" && data) {
      setStart(data.period.start);
      setEnd(data.period.end);
    }
    setPeriod(value);
  }

  function toggle(siteId: number, checked: boolean) {
    setUnselected((prev) => {
      const next = new Set(prev);
      if (checked) next.delete(siteId);
      else next.add(siteId);
      return next;
    });
  }

  const colors = useMemo(() => new Map((data?.sites ?? []).map((site, i) => [site.site_id, siteColor(i)])), [data]);
  const selected = (data?.sites ?? []).filter((s) => !unselected.has(s.site_id));
  const hasCompare = data?.compare != null;
  // 日ごとの推移に比べる期間を重ねるのは、選んだときだけ
  const showCompare = hasCompare && overlayCompare;
  // Bing は日ごとの掲載順位がなく、推移はクリックと表示回数だけ（CTR も出さない）
  const metrics: SeoMetric[] = data?.engine === "bing" ? ["clicks", "impressions"] : ["clicks", "impressions", "ctr", "position"];
  const chartMetric = metrics.includes(metric) ? metric : "clicks";

  const dailySeries: Series[] = [
    ...selected.map((s) => ({
      key: `s${s.site_id}`,
      name: s.name,
      color: colors.get(s.site_id),
      compareKey: showCompare ? `s${s.site_id}_cmp` : undefined,
    })),
    ...(showTotal
      ? [{ key: TOTAL_KEY, name: "合計", color: TOTAL_COLOR, compareKey: showCompare ? `${TOTAL_KEY}_cmp` : undefined, total: true }]
      : []),
  ];

  const dataUntil = data?.data_until ? `${formatDate(data.data_until)}までのデータ` : null;

  return (
    <>
      {/* Google/Bing・期間・比べる・「更新」は固定バーに置き、スクロールしても常に出す（screen_design.md §1・§7）。
          左端は Google/Bing、右端は「更新」（リアルタイムとそろえる） */}
      <PageBar>
        {/* PC は「左の操作｜右の更新」の下に実際の期間。スマホは操作で1行を使い、「更新」は2行目の右に回す（バーを低く保つ） */}
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 [grid-template-areas:'controls_controls'_'range_refresh'] sm:[grid-template-areas:'controls_refresh'_'range_range']">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 [grid-area:controls] sm:gap-x-5">
            <Segmented
              label="検索エンジン"
              options={[
                { value: "google", label: "Google" },
                { value: "bing", label: "Bing" },
              ]}
              value={engine}
              onChange={setEngine}
            />
            <label className="flex items-center gap-2 text-ink-2">
              {/* スマホでは1行に収めるため、名前は読み上げだけにする */}
              <span className="max-sm:sr-only">期間</span>
              <select className={CONTROL} value={period} onChange={(e) => choosePeriod(e.target.value as SeoPeriodName)}>
                {PERIODS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            {period === "custom" && (
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  aria-label="期間の始まり"
                  className={CONTROL}
                  value={start}
                  max={data?.data_until ?? undefined}
                  onChange={(e) => setStart(e.target.value)}
                />
                〜
                <input
                  type="date"
                  aria-label="期間の終わり"
                  className={CONTROL}
                  value={end}
                  max={data?.data_until ?? undefined}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </div>
            )}
            <label className="flex items-center gap-2 text-ink-2">
              <span className="max-sm:sr-only">比べる</span>
              <select className={CONTROL} value={compare} onChange={(e) => setCompare(e.target.value as SeoCompareName)}>
                {COMPARES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {/* いつまでのデータかは「更新」の隣に置く（リアルタイムの「◯ に取得」と同じ位置） */}
          <div className="flex items-center gap-3 justify-self-end [grid-area:refresh]">
            {dataUntil && <span className="text-ink-3 max-sm:hidden">{dataUntil}</span>}
            <Button onClick={() => setReloads((n) => n + 1)} disabled={loading}>
              {loading ? "取得中…" : "更新"}
            </Button>
          </div>
          {data && (
            <p className="text-xs text-ink-3 [grid-area:range]">
              {formatRange(data.period.start, data.period.end)}（{countDays(data.period.start, data.period.end)}日間）
              {data.compare && `を ${formatRange(data.compare.start, data.compare.end)} と比べる`}
              {/* スマホでは、いつまでのデータかをこの行に回す */}
              {dataUntil && <span className="sm:hidden">（{dataUntil}）</span>}
            </p>
          )}
        </div>
      </PageBar>
      <PageBody>
        {/* 題は、ヘッダーのメニューでどの画面かわかるので画面には出さず、読み上げ用だけにする */}
        <h1 className="sr-only">SEO</h1>

        {error && <Notice>{error}</Notice>}

        {/* 取っている間は、前の数字はそのまま出し、画面の真ん中に印を出すだけにする */}
        {loading && <LoadingIndicator />}

        {/* 本物で、まだ連携していないとき・まだ取り込んでいないとき（デモは、いつも数字がある） */}
        {data && data.sites.length === 0 && (
          <div className="rounded-xl border bg-surface px-6 py-10 text-center">
            <p>{ENGINE_LABELS[data.engine]}と連携しているサイトがありません。サイト設定で連携してください。</p>
            <Link href="/settings/sites" className="mt-3 inline-block font-medium underline underline-offset-4">
              サイト設定へ
            </Link>
          </div>
        )}
        {data && data.sites.length > 0 && data.data_until === null && (
          <Notice kind="warning">
            まだ{ENGINE_LABELS[data.engine]}の数字を取り込んでいません。取り込みのコマンド（uv run python -m glance.sync）を動かすと出ます。
          </Notice>
        )}

        {data && data.sites.length > 0 && (
          <div className="space-y-5">
            <SeoCards
              engine={data.engine}
              sites={data.sites}
              selected={selected}
              colors={colors}
              hasCompare={hasCompare}
              onToggle={toggle}
              showTotal={showTotal}
              onToggleTotal={setShowTotal}
            />

            <section className="rounded-xl border bg-surface">
              <div className="border-b px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-base font-medium">日ごとの推移</h2>
                  <Segmented
                    label="指標"
                    options={metrics.map((m) => ({ value: m, label: METRIC_LABELS[m] }))}
                    value={chartMetric}
                    onChange={setMetric}
                  />
                  {/* 比べないときは、重ねるものがないので出さない */}
                  {hasCompare && (
                    <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm text-ink-2">
                      <Checkbox checked={overlayCompare} onCheckedChange={setOverlayCompare} />
                      比べる期間を重ねる
                    </label>
                  )}
                </div>
                {selected.length > 0 && (
                  <SeriesLegend sites={selected} colors={colors} showTotal={showTotal}>
                    {showCompare && (
                      <li className="flex items-center gap-1.5">
                        <span
                          className="w-4 border-t-2 border-dashed border-ink-3"
                          style={{ opacity: COMPARE_OPACITY }}
                          aria-hidden
                        />
                        比べる期間
                      </li>
                    )}
                  </SeriesLegend>
                )}
              </div>
              <div className="px-2 py-4">
                {selected.length > 0 ? (
                  <DateLineChart
                    rows={dailyRows(selected, chartMetric, showCompare)}
                    series={dailySeries}
                    title={METRIC_LABELS[chartMetric]}
                    format={(v) => formatMetric(v, chartMetric)}
                    axisFormat={(v) => formatMetricAxis(v, chartMetric)}
                    // 掲載順位も、数字が小さいほど下に描く（縦軸を逆にしない。2026-11-27 利用者の決定）
                    fitToValues={chartMetric === "position"}
                  />
                ) : (
                  <SelectPrompt />
                )}
              </div>
            </section>

            {/* インデックス（Google は検索に出たページ、Bing はインデックス数）とサイトマップ。日ごとの推移のすぐ下 */}
            <IndexSection engine={data.engine} sites={selected} colors={colors} />

            {/* Bing のクエリは今は取らない（data_sources.md §4） */}
            {data.engine === "google" && <RankingTable kind="query" sites={selected} colors={colors} hasCompare={hasCompare} />}
            <RankingTable kind="page" sites={selected} colors={colors} hasCompare={hasCompare} />

          </div>
        )}
      </PageBody>
    </>
  );
}

function SelectPrompt() {
  return <p className="px-4 py-10 text-center text-ink-3">サイトを選んでください。</p>;
}
