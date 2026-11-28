"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";

import { formatDate, formatShortDate } from "@/lib/format";

// 日ごとの折れ線（docs/01_design/screen_design.md §5・§7、design_guideline.md §5）。
// 日ごとの推移と、Bing のクロールとインデックスで使う。補助線は横だけ、縦軸は右、各値に点、
// ホバーで縦線と全系列の値のカード。比べる期間は、同じ色の薄い破線で重ねる

// 比べる期間の破線の濃さ。この期間の線より目立たないよう薄くする（凡例の破線もこれに合わせる）
export const COMPARE_OPACITY = 0.45;

// compare_date は、その日と並べる比べる期間の日（期間の何日目かでそろえる）
export type DateRow = { date: string; compare_date?: string | null } & Record<string, string | number | null | undefined>;

export type Series = {
  key: string;
  name: string;
  color: string | undefined;
  compareKey?: string; // 比べる期間の値の列。あれば破線で重ねる
  total?: boolean; // 合計。ホバーのカードで区切って最後に出す
};

type ChartProps = {
  rows: DateRow[];
  series: Series[];
  title: string; // ホバーのカードの見出し（指標の名前）
  format: (value: number) => string;
  axisFormat: (value: number) => string;
  fitToValues?: boolean; // 縦軸を 0 からではなく、値のある範囲に合わせる（掲載順位。0 からだと線が潰れる）
};

function TooltipCard({ active, payload, series, title, format }: TooltipContentProps & ChartProps) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as DateRow;
  // 比べる期間の日。比べる期間のほうが短いときは、終わりのほうの日にない
  const compareDate = series.some((s) => s.compareKey) ? row.compare_date : null;
  const hasCompare = Boolean(compareDate);
  const value = (key: string | undefined) => {
    const v = key === undefined ? undefined : row[key];
    return typeof v === "number" ? format(v) : "—";
  };
  return (
    <div className="min-w-48 rounded-xl border bg-surface px-3 py-2.5 text-xs leading-normal shadow-pop">
      <div className="mb-2 font-medium text-ink">{title}</div>
      <table className="w-full tabular-nums">
        <thead className="text-ink-3">
          <tr>
            <th />
            <th className="pb-1 pl-4 text-right font-normal">{formatDate(row.date, { weekday: true })}</th>
            {compareDate && (
              // 前年と比べるときは、年が違うことがわかるよう、比べる日に年を付ける
              <th className="pb-1 pl-4 text-right font-normal">
                {formatDate(compareDate, { weekday: true, year: compareDate.slice(0, 4) !== row.date.slice(0, 4) })}
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.key} className={s.total ? "border-t font-medium text-ink" : undefined}>
              <td className="py-0.5">
                <span className="flex items-center gap-2">
                  <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: s.color }} />
                  <span className={s.total ? undefined : "text-ink-2"}>{s.name}</span>
                </span>
              </td>
              <td className="pl-4 text-right font-medium text-ink">{value(s.key)}</td>
              {hasCompare && <td className="pl-4 text-right text-ink-2">{value(s.compareKey)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DateLineChart(props: ChartProps) {
  const { rows, series, axisFormat, fitToValues = false } = props;
  // 横軸の目盛りは、始め・真ん中・終わりの3つ
  const ticks = rows.length ? [...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])].map((i) => rows[i].date) : [];

  return (
    <div className="h-72 w-full [&_.recharts-cartesian-axis-tick_text]:tabular-nums">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 800, height: 288 }}>
        {/* 左右の余白は、横軸の端の目盛りが切れない幅 */}
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 24 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="date"
            ticks={ticks}
            tickFormatter={formatShortDate}
            tickLine={false}
            axisLine={{ stroke: "var(--axis)" }}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
            interval={0}
          />
          <YAxis
            orientation="right"
            domain={fitToValues ? ["auto", "auto"] : [0, "auto"]}
            axisLine={false}
            tickLine={false}
            width={48}
            tickFormatter={axisFormat}
            tick={{ fill: "var(--ink-3)", fontSize: 12 }}
          />
          <Tooltip content={(p) => <TooltipCard {...p} {...props} />} cursor={{ stroke: "var(--ink-3)", strokeWidth: 1 }} />
          {/* 比べる期間の破線を先に描き、この期間の線の下に置く。破線には点を付けない（この期間の線と見分けるため） */}
          {series
            .filter((s) => s.compareKey)
            .map((s) => (
              <Line
                key={s.compareKey}
                dataKey={s.compareKey}
                name={`${s.name}（比べる期間）`}
                type="linear"
                stroke={s.color}
                strokeOpacity={COMPARE_OPACITY}
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
            ))}
          {/* 合計は series の最後に置き、サイトの線の上に出す */}
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.name}
              type="linear"
              stroke={s.color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={{ r: 3, fill: s.color, stroke: "var(--surface)", strokeWidth: 1.5 }}
              activeDot={{ r: 5, fill: s.color, stroke: "var(--surface)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
