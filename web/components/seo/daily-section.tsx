"use client";

import { useState } from "react";

import { Segmented } from "@/components/segmented";
import { COMPARE_OPACITY, type DateRow, DateLineChart, type Series } from "@/components/seo/date-line-chart";
import { SeriesLegend } from "@/components/series-legend";
import { SelectPrompt } from "@/components/site-selection";
import { Checkbox } from "@/components/ui/checkbox";
import { TOTAL_COLOR, TOTAL_KEY } from "@/lib/format";
import {
  METRIC_LABELS,
  type SeoMetric,
  addTotals,
  formatMetric,
  formatMetricAxis,
  metricValue,
} from "@/lib/seo-metrics";
import type { SeoEngine, SeoSite } from "@/lib/types";

// SEO の画面の「日ごとの推移」（docs/01_design/screen_design.md §7）。選んだサイトと合計の線

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

export function DailySection({
  engine,
  sites,
  colors,
  showTotal,
  hasCompare,
}: {
  engine: SeoEngine;
  sites: SeoSite[]; // 選んだサイト
  colors: Map<number, string>;
  showTotal: boolean;
  hasCompare: boolean;
}) {
  const [metric, setMetric] = useState<SeoMetric>("clicks");
  // 比べる期間の破線を重ねるか。線が倍になって読みにくくなるので、初めは重ねない
  const [overlayCompare, setOverlayCompare] = useState(false);
  const showCompare = hasCompare && overlayCompare;
  // Bing は日ごとの掲載順位がなく、推移はクリックと表示回数だけ（CTR も出さない）
  const metrics: SeoMetric[] = engine === "bing" ? ["clicks", "impressions"] : ["clicks", "impressions", "ctr", "position"];
  const chartMetric = metrics.includes(metric) ? metric : "clicks";

  const series: Series[] = [
    ...sites.map((s) => ({
      key: `s${s.site_id}`,
      name: s.name,
      color: colors.get(s.site_id),
      compareKey: showCompare ? `s${s.site_id}_cmp` : undefined,
    })),
    ...(showTotal
      ? [{ key: TOTAL_KEY, name: "合計", color: TOTAL_COLOR, compareKey: showCompare ? `${TOTAL_KEY}_cmp` : undefined, total: true }]
      : []),
  ];

  return (
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
        {sites.length > 0 && (
          <SeriesLegend sites={sites} colors={colors} showTotal={showTotal}>
            {showCompare && (
              <li className="flex items-center gap-1.5">
                <span className="w-4 border-t-2 border-dashed border-ink-3" style={{ opacity: COMPARE_OPACITY }} aria-hidden />
                比べる期間
              </li>
            )}
          </SeriesLegend>
        )}
      </div>
      <div className="px-2 py-4">
        {sites.length > 0 ? (
          <DateLineChart
            rows={dailyRows(sites, chartMetric, showCompare)}
            series={series}
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
  );
}
