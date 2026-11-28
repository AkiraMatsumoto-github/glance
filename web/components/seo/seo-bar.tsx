"use client";

import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { countDays, formatDate, formatRange } from "@/lib/format";
import type { Seo, SeoCompareName, SeoEngine, SeoPeriodName } from "@/lib/types";

// SEO の画面の固定バーの中身（docs/01_design/screen_design.md §1・§7）。Google/Bing・期間・比べる・「更新」。
// 左端は Google/Bing、右端は「更新」（リアルタイムとそろえる）

export type SeoFilter = {
  engine: SeoEngine;
  period: SeoPeriodName;
  compare: SeoCompareName;
  start: string; // 指定の期間のときだけ使う
  end: string;
};

export const DEFAULT_FILTER: SeoFilter = {
  engine: "google",
  period: "last_28_days",
  compare: "previous_period",
  start: "",
  end: "",
};

// 取る URL。指定の期間は、始まりと終わりがそろうまで取らない（null）
export function seoUrl(endpoint: string, filter: SeoFilter): string | null {
  const params = new URLSearchParams({ engine: filter.engine, period: filter.period, compare: filter.compare });
  if (filter.period === "custom") {
    if (!filter.start || !filter.end) return null;
    params.set("start", filter.start);
    params.set("end", filter.end);
  }
  return `${endpoint}?${params}`;
}

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

const CONTROL = "h-8 rounded-md border bg-surface px-2 text-sm text-ink";

export function SeoBar({
  filter,
  onChange,
  data,
  loading,
  onReload,
}: {
  filter: SeoFilter;
  onChange: (next: Partial<SeoFilter>) => void;
  data: Seo | null; // いま出している数字（期間といつまでのデータかを出す）
  loading: boolean;
  onReload: () => void;
}) {
  function choosePeriod(period: SeoPeriodName) {
    // 指定に切り替えたときは、いま出している期間を初めの値にする
    onChange(period === "custom" && data ? { period, start: data.period.start, end: data.period.end } : { period });
  }

  const dataUntil = data?.data_until ? `${formatDate(data.data_until)}までのデータ` : null;

  return (
    // PC は「左の操作｜右の更新」の下に実際の期間。スマホは操作で1行を使い、「更新」は2行目の右に回す（バーを低く保つ）
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 [grid-template-areas:'controls_controls'_'range_refresh'] sm:[grid-template-areas:'controls_refresh'_'range_range']">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 [grid-area:controls] sm:gap-x-5">
        <Segmented
          label="検索エンジン"
          options={[
            { value: "google", label: "Google" },
            { value: "bing", label: "Bing" },
          ]}
          value={filter.engine}
          onChange={(engine) => onChange({ engine })}
        />
        <label className="flex items-center gap-2 text-ink-2">
          {/* スマホでは1行に収めるため、名前は読み上げだけにする */}
          <span className="max-sm:sr-only">期間</span>
          <select className={CONTROL} value={filter.period} onChange={(e) => choosePeriod(e.target.value as SeoPeriodName)}>
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        {filter.period === "custom" && (
          <div className="flex items-center gap-2">
            <input
              type="date"
              aria-label="期間の始まり"
              className={CONTROL}
              value={filter.start}
              max={data?.data_until ?? undefined}
              onChange={(e) => onChange({ start: e.target.value })}
            />
            〜
            <input
              type="date"
              aria-label="期間の終わり"
              className={CONTROL}
              value={filter.end}
              max={data?.data_until ?? undefined}
              onChange={(e) => onChange({ end: e.target.value })}
            />
          </div>
        )}
        <label className="flex items-center gap-2 text-ink-2">
          <span className="max-sm:sr-only">比べる</span>
          <select
            className={CONTROL}
            value={filter.compare}
            onChange={(e) => onChange({ compare: e.target.value as SeoCompareName })}
          >
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
        <Button onClick={onReload} disabled={loading}>
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
  );
}
