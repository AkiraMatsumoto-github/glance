import { formatCompact, formatNumber, formatPercent } from "@/lib/format";
import type { SeoTotals } from "@/lib/types";

// SEO の指標の計算と書き方（docs/01_design/screen_design.md §7）

export type SeoMetric = "clicks" | "impressions" | "ctr" | "position";

export const METRIC_LABELS: Record<SeoMetric, string> = {
  clicks: "クリック",
  impressions: "表示回数",
  ctr: "CTR",
  position: "掲載順位",
};

// サイト（または日）を足す。掲載順位は表示回数の重みつき平均（database_design.md §6）
export function addTotals(list: SeoTotals[]): SeoTotals {
  let clicks = 0;
  let impressions = 0;
  let positionSum = 0;
  let positionWeight = 0;
  for (const t of list) {
    clicks += t.clicks;
    impressions += t.impressions;
    if (t.position !== null) {
      positionSum += t.position * t.impressions;
      positionWeight += t.impressions;
    }
  }
  return { clicks, impressions, position: positionWeight ? positionSum / positionWeight : null };
}

// CTR は「クリック ÷ 表示回数」
export function ctr(t: SeoTotals): number | null {
  return t.impressions ? t.clicks / t.impressions : null;
}

export function metricValue(t: SeoTotals, metric: SeoMetric): number | null {
  if (metric === "ctr") return ctr(t);
  if (metric === "position") return t.position;
  return t[metric];
}

export function formatMetric(value: number | null, metric: SeoMetric): string {
  if (value === null) return "—";
  if (metric === "ctr") return formatPercent(value);
  if (metric === "position") return value.toFixed(1);
  return formatNumber(value);
}

// 縦軸の目盛り
export function formatMetricAxis(value: number, metric: SeoMetric): string {
  if (metric === "ctr") return formatPercent(value);
  if (metric === "position") return String(Number(value.toFixed(1)));
  return formatCompact(value);
}

function signed(value: number, digits: number, unit: string): string {
  const text = Math.abs(value).toFixed(digits);
  if (Number(text) === 0) return `±0${unit}`;
  return `${value > 0 ? "+" : "-"}${text}${unit}`;
}

// 比べる期間との差。クリック・表示回数は増減率、CTR は pt。
// 掲載順位は数字が小さいほど上なので「◯ 上がった／下がった」と書く（+／- は使わない）
export function formatChange(current: SeoTotals, previous: SeoTotals | null, metric: SeoMetric): string | null {
  if (previous === null) return null;
  if (metric === "clicks" || metric === "impressions") {
    const before = previous[metric];
    return before ? signed(((current[metric] - before) / before) * 100, 1, "%") : "—";
  }
  const now = metricValue(current, metric);
  const before = metricValue(previous, metric);
  if (now === null || before === null) return "—";
  if (metric === "ctr") return signed((now - before) * 100, 1, "pt");
  const moved = Math.abs(before - now).toFixed(1);
  if (Number(moved) === 0) return "変わらない";
  return `${moved} ${before > now ? "上がった" : "下がった"}`;
}
