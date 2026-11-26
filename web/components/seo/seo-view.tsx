"use client";

import { useEffect, useMemo, useState } from "react";

import { LoadingIndicator } from "@/components/loading-indicator";
import { Notice } from "@/components/notice";
import { Segmented } from "@/components/segmented";
import { COMPARE_OPACITY, type DateRow, DateLineChart, type Series } from "@/components/seo/date-line-chart";
import {
  METRIC_LABELS,
  type SeoMetric,
  addTotals,
  formatMetric,
  formatMetricAxis,
  metricValue,
} from "@/components/seo/metrics";
import { RankingTable } from "@/components/seo/ranking-table";
import { SeoCards } from "@/components/seo/seo-cards";
import { SeriesLegend } from "@/components/series-legend";
import { Checkbox } from "@/components/ui/checkbox";
import { api, errorMessage } from "@/lib/api";
import { countDays, formatCompact, formatDate, formatNumber, formatRange, siteColor } from "@/lib/format";
import type { CrawlDay, Seo, SeoCompareName, SeoEngine, SeoPeriodName, SeoSite } from "@/lib/types";

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

type CrawlMetric = "indexed" | "crawled" | "errors";
const CRAWL_LABELS: Record<CrawlMetric, string> = { indexed: "インデックス数", crawled: "クロール数", errors: "クロールエラー" };

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

function crawlRows(sites: SeoSite[], metric: CrawlMetric): DateRow[] {
  const days: CrawlDay[] = sites[0]?.crawl ?? [];
  return days.map((day, i) => {
    const row: DateRow = { date: day.date };
    for (const site of sites) row[`s${site.site_id}`] = site.crawl?.[i]?.[metric] ?? null;
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
  const [doneUrl, setDoneUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loading = url !== null && url !== doneUrl;

  const [metric, setMetric] = useState<SeoMetric>("clicks");
  const [crawlMetric, setCrawlMetric] = useState<CrawlMetric>("indexed");
  // 外したサイトと合計の線。条件を変えても保つ（開き直すと全部オンに戻る）
  const [unselected, setUnselected] = useState<Set<number>>(new Set());
  const [showTotal, setShowTotal] = useState(true);
  // 日ごとの推移に比べる期間の破線を重ねるか。線が倍になって読みにくくなるので、初めは重ねない
  const [overlayCompare, setOverlayCompare] = useState(false);

  useEffect(() => {
    if (url === null) return;
    // 条件を続けて変えたときは、最後の条件の結果だけを出す
    let cancelled = false;
    api<Seo>(url).then(
      (result) => {
        if (cancelled) return;
        lastResults.set(url, result);
        setData(result);
        setError(null);
        setDoneUrl(url);
      },
      (e: unknown) => {
        if (cancelled) return;
        setError(errorMessage(e));
        setDoneUrl(url);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url]);

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

  const dataUntil = data && `${formatDate(data.data_until)}までのデータ`;

  return (
    <div className="space-y-5">
      {/* 期間・比べる・Google/Bing は、ヘッダーの下に固定し、スクロールしても常に出す（screen_design.md §7）。
          画面の端から端まで白い面と下の線を引いて、ヘッダーの2段目のように見せる（globals.css の bar-full-bleed）。
          -mt-6 で main の上の余白を打ち消し、初めからヘッダーに付ける。z-20 はヘッダー（z-40）より下、カードより上 */}
      <div className="bar-full-bleed sticky top-14 z-20 -mt-6 space-y-1.5 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 sm:gap-x-5">
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
                max={data?.data_until}
                onChange={(e) => setStart(e.target.value)}
              />
              〜
              <input
                type="date"
                aria-label="期間の終わり"
                className={CONTROL}
                value={end}
                max={data?.data_until}
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
          {/* いつまでのデータかは Google と Bing で違うので、切り替えの隣に置く */}
          <div className="ml-auto flex items-center gap-3">
            {dataUntil && <span className="text-ink-3 max-sm:hidden">{dataUntil}</span>}
            <Segmented
              label="検索エンジン"
              options={[
                { value: "google", label: "Google" },
                { value: "bing", label: "Bing" },
              ]}
              value={engine}
              onChange={setEngine}
            />
          </div>
        </div>
        {data && (
          <p className="text-xs text-ink-3">
            {formatRange(data.period.start, data.period.end)}（{countDays(data.period.start, data.period.end)}日間）
            {data.compare && `を ${formatRange(data.compare.start, data.compare.end)} と比べる`}
            {/* スマホでは、いつまでのデータかをこの行に回す */}
            <span className="sm:hidden">（{dataUntil}）</span>
          </p>
        )}
      </div>

      <h1 className="text-xl font-semibold">SEO</h1>

      {error && <Notice>{error}</Notice>}

      {/* 取っている間は、前の数字はそのまま出し、画面の真ん中に印を出すだけにする */}
      {loading && <LoadingIndicator />}

      {data && (
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
                  reversed={chartMetric === "position"}
                />
              ) : (
                <SelectPrompt />
              )}
            </div>
          </section>

          {/* Bing のクエリは今は取らない（data_sources.md §4） */}
          {data.engine === "google" && <RankingTable kind="query" sites={selected} colors={colors} hasCompare={hasCompare} />}
          <RankingTable kind="page" sites={selected} colors={colors} hasCompare={hasCompare} />

          {data.engine === "bing" && (
            <section className="rounded-xl border bg-surface">
              <div className="border-b px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-base font-medium">クロールとインデックス</h2>
                  <Segmented
                    label="指標"
                    options={(Object.keys(CRAWL_LABELS) as CrawlMetric[]).map((m) => ({ value: m, label: CRAWL_LABELS[m] }))}
                    value={crawlMetric}
                    onChange={setCrawlMetric}
                  />
                </div>
                {selected.length > 0 && <SeriesLegend sites={selected} colors={colors} />}
              </div>
              <div className="px-2 py-4">
                {selected.length > 0 ? (
                  // インデックス数はその日の在庫なので、サイトを足した合計の線は出さない
                  <DateLineChart
                    rows={crawlRows(selected, crawlMetric)}
                    series={selected.map((s) => ({ key: `s${s.site_id}`, name: s.name, color: colors.get(s.site_id) }))}
                    title={CRAWL_LABELS[crawlMetric]}
                    format={formatNumber}
                    axisFormat={formatCompact}
                  />
                ) : (
                  <SelectPrompt />
                )}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function SelectPrompt() {
  return <p className="px-4 py-10 text-center text-ink-3">サイトを選んでください。</p>;
}
