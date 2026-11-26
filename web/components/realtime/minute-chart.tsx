"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";

import { formatAxis, formatNumber } from "@/lib/format";
import type { Metric, OkSite } from "@/lib/types";

const METRIC_LABELS: Record<Metric, string> = { page_views: "PV", active_users: "UU" };
const TOTAL_KEY = "total";
const TOTAL_COLOR = "var(--ink)"; // 合計はサイトの色を使わず墨色（design_guideline.md §2.2）

function minuteLabel(minutesAgo: number): string {
  return minutesAgo === 0 ? "今" : `${minutesAgo}分前`;
}

type ChartProps = {
  sites: OkSite[];
  colors: Map<number, string>;
  metric: Metric;
  showTotal: boolean;
};

// ホバーで出すカード。その時点の全系列の値を、サイトの並び順に並べ、最後に合計
function TooltipCard({ active, payload, label, sites, colors, metric, showTotal }: TooltipContentProps & ChartProps) {
  if (!active || !payload?.length) return null;
  const value = (key: string) => formatNumber(Number(payload.find((p) => p.dataKey === key)?.value ?? 0));
  return (
    <div className="min-w-44 rounded-xl border bg-surface px-3 py-2.5 text-xs leading-normal shadow-pop">
      <div className="mb-2 font-medium text-ink">
        {minuteLabel(Number(label))}の{METRIC_LABELS[metric]}
      </div>
      <ul className="space-y-1">
        {sites.map((site) => (
          <li key={site.site_id} className="flex items-center gap-2">
            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
            <span className="text-ink-2">{site.name}</span>
            <span className="ml-auto pl-4 font-medium text-ink tabular-nums">{value(`s${site.site_id}`)}</span>
          </li>
        ))}
        {showTotal && (
          <li className="mt-1 flex items-center gap-2 border-t pt-1.5">
            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: TOTAL_COLOR }} />
            <span className="font-medium text-ink">合計</span>
            <span className="ml-auto pl-4 font-medium text-ink tabular-nums">{value(TOTAL_KEY)}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

// 各値に丸い点を出し、どこで折れているかを見えるようにする。周りの白い縁で、重なっても区切りがわかる
function dotStyle(color: string | undefined) {
  return { r: 3, fill: color, stroke: "var(--surface)", strokeWidth: 1.5 };
}

// 分ごとの推移（docs/01_design/screen_design.md §3、design_guideline.md §5）。
// 補助線は横だけ、縦軸は右、各値に点、ホバーで縦線と全系列の値のカード
export function MinuteChart({ sites, colors, metric, showTotal }: ChartProps) {
  // 29分前から今まで30点。合計は、選んだサイトを足した値
  const rows = Array.from({ length: 30 }, (_, i) => {
    const minutesAgo = 29 - i;
    const point: Record<string, number> = { minutes_ago: minutesAgo, [TOTAL_KEY]: 0 };
    for (const site of sites) {
      const value = site.per_minute.find((m) => m.minutes_ago === minutesAgo)?.[metric] ?? 0;
      point[`s${site.site_id}`] = value;
      point[TOTAL_KEY] += value;
    }
    return point;
  });

  const line = (key: string, name: string, color: string | undefined) => (
    <Line
      key={key}
      dataKey={key}
      name={name}
      type="linear"
      stroke={color}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      dot={dotStyle(color)}
      activeDot={{ r: 5, fill: color, stroke: "var(--surface)", strokeWidth: 2 }}
      isAnimationActive={false}
    />
  );

  return (
    <div className="h-72 w-full [&_.recharts-cartesian-axis-tick_text]:tabular-nums">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 800, height: 288 }}>
        {/* 左右の余白は、横軸の端の目盛り（29分前・今）が切れない幅 */}
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 24 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="minutes_ago"
            ticks={[29, 15, 0]}
            tickFormatter={minuteLabel}
            tickLine={false}
            axisLine={{ stroke: "var(--axis)" }}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
            interval={0}
          />
          <YAxis
            orientation="right"
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            width={44}
            tickFormatter={formatAxis}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
          />
          <Tooltip
            content={(props) => (
              <TooltipCard {...props} sites={sites} colors={colors} metric={metric} showTotal={showTotal} />
            )}
            cursor={{ stroke: "var(--ink-3)", strokeWidth: 1 }}
          />
          {sites.map((site) => line(`s${site.site_id}`, site.name, colors.get(site.site_id)))}
          {/* 合計は最後に描いて、サイトの線の上に出す */}
          {showTotal && line(TOTAL_KEY, "合計", TOTAL_COLOR)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
