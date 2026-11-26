"use client";

import { addTotals, ctr, formatChange, formatMetric } from "@/components/seo/metrics";
import { CARD_CLICKABLE, Stat, Toggle } from "@/components/selectable-card";
import { formatCompact, formatNumber } from "@/lib/format";
import type { SeoEngine, SeoSite } from "@/lib/types";
import { cn } from "@/lib/utils";

// SEO の数字のカード（docs/01_design/screen_design.md §7）。作りはリアルタイムと同じで、
// 上に選んだサイトの合計を横いっぱいに、その下にサイトごとのカードを並べる。
// カードのチェックボックスが、出すサイトの選択とグラフの凡例を兼ねる。小さな字は比べる期間との差
export function SeoCards({
  engine,
  sites,
  selected,
  colors,
  hasCompare,
  onToggle,
  showTotal,
  onToggleTotal,
}: {
  engine: SeoEngine;
  sites: SeoSite[];
  selected: SeoSite[];
  colors: Map<number, string>;
  hasCompare: boolean;
  onToggle: (siteId: number, checked: boolean) => void;
  showTotal: boolean;
  onToggleTotal: (checked: boolean) => void;
}) {
  const total = addTotals(selected.map((s) => s.totals));
  const before = hasCompare ? addTotals(selected.flatMap((s) => s.compare_totals ?? [])) : null;
  return (
    <div className="space-y-3">
      {/* 合計。チェックボックスはグラフの合計の線 */}
      <div className={CARD_CLICKABLE + " p-5"}>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Toggle
            name="合計"
            color="var(--ink)"
            checked={showTotal}
            onChange={onToggleTotal}
            title="グラフに合計の線を出す"
            className="text-base"
          />
          <span className="text-xs text-ink-3">選んだ {selected.length} サイト</span>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-x-10 gap-y-3">
          <Stat label="クリック" value={formatNumber(total.clicks)} size="lg" sub={formatChange(total, before, "clicks")} />
          <Stat label="表示回数" value={formatCompact(total.impressions)} size="lg" sub={formatChange(total, before, "impressions")} />
          <Stat label="CTR" value={formatMetric(ctr(total), "ctr")} size="lg" sub={formatChange(total, before, "ctr")} />
          {/* Bing は日ごとの掲載順位が取れないので出さない */}
          {engine === "google" && (
            <Stat
              label="平均掲載順位"
              value={formatMetric(total.position, "position")}
              size="lg"
              sub={formatChange(total, before, "position")}
            />
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {sites.map((site) => {
          const checked = selected.includes(site);
          const lastIndexed = site.crawl?.at(-1)?.indexed;
          return (
            <div key={site.site_id} className={cn(CARD_CLICKABLE, "flex min-w-0 flex-col gap-3 p-4")}>
              <Toggle
                name={site.name}
                color={colors.get(site.site_id)}
                checked={checked}
                onChange={(value) => onToggle(site.site_id, value)}
                title="グラフ・クエリ・ページの一覧と合計に入れる"
              />
              {/* 外したサイトは、数字を薄くして「合計などに入っていない」ことを示す */}
              <div className={cn("space-y-3", !checked && "opacity-50")}>
                <Stat
                  label="クリック"
                  value={formatNumber(site.totals.clicks)}
                  size="md"
                  sub={formatChange(site.totals, site.compare_totals, "clicks")}
                />
                <div className="space-y-0.5 text-xs text-ink-3">
                  <div>表示回数 {formatCompact(site.totals.impressions)}</div>
                  {engine === "google" ? (
                    <div>掲載順位 {formatMetric(site.totals.position, "position")}</div>
                  ) : (
                    // インデックス数はその日の在庫なので、期間の最後の日の値
                    lastIndexed !== undefined && <div>インデックス {formatNumber(lastIndexed)}</div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
