"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";

import { formatNumber } from "@/lib/format";
import type { Metric, RealtimeSite } from "@/lib/types";

type OkSite = Extract<RealtimeSite, { status: "ok" }>;

const METRIC_LABELS: Record<Metric, string> = { page_views: "PV", active_users: "UU" };

function minuteLabel(minutesAgo: number): string {
  return minutesAgo === 0 ? "今" : `${minutesAgo}分前`;
}

type ChartProps = {
  sites: OkSite[];
  colors: Map<number, string>;
  metric: Metric;
};

// ホバーで出すカード。その時点の全系列の値を、サイトの並び順に並べる
function TooltipCard({ active, payload, label, sites, colors, metric }: TooltipContentProps & ChartProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-40 rounded-lg border bg-background px-3 py-2 text-xs shadow-md">
      <div className="mb-1.5 font-medium">
        {minuteLabel(Number(label))}の{METRIC_LABELS[metric]}
      </div>
      <ul className="space-y-1">
        {sites.map((site) => {
          const entry = payload.find((p) => p.dataKey === `s${site.site_id}`);
          return (
            <li key={site.site_id} className="flex items-center gap-2">
              <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
              <span className="text-muted-foreground">{site.name}</span>
              <span className="ml-auto pl-4 font-medium tabular-nums">{formatNumber(Number(entry?.value ?? 0))}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// 分ごとの推移（docs/01_design/screen_design.md §3・§5）。GA4 に近い見た目にする:
// 補助線は横だけ、縦軸は右、普段は点を出さず、ホバーで縦線と全系列の値のカード
export function MinuteChart({ sites, colors, metric }: ChartProps) {
  const rows = Array.from({ length: 30 }, (_, i) => {
    const minutesAgo = 29 - i;
    const row: Record<string, number> = { minutes_ago: minutesAgo };
    for (const site of sites) {
      row[`s${site.site_id}`] = site.per_minute.find((m) => m.minutes_ago === minutesAgo)?.[metric] ?? 0;
    }
    return row;
  });

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 800, height: 288 }}>
        {/* 左右の余白は、横軸の端の目盛り（29分前・今）が切れない幅 */}
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 24 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="minutes_ago"
            ticks={[29, 15, 0]}
            tickFormatter={minuteLabel}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
            interval={0}
          />
          <YAxis
            orientation="right"
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            width={40}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <Tooltip
            content={(props) => <TooltipCard {...props} sites={sites} colors={colors} metric={metric} />}
            cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
          />
          {sites.map((site) => (
            <Line
              key={site.site_id}
              dataKey={`s${site.site_id}`}
              name={site.name}
              type="linear"
              stroke={colors.get(site.site_id)}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
