"use client";

import { Checkbox } from "@/components/ui/checkbox";
import type { RealtimeSite } from "@/lib/types";

// 出すサイトの選択。分ごとの推移・デバイスと国の内訳・いま読まれている記事に効く。グラフの凡例も兼ねる。
// 最後の「合計」は、分ごとの推移に合計の線を出すかどうか
export function SiteFilter({
  sites,
  colors,
  isSelected,
  onToggle,
  showTotal,
  onToggleTotal,
}: {
  sites: RealtimeSite[];
  colors: Map<number, string>;
  isSelected: (siteId: number) => boolean;
  onToggle: (siteId: number, checked: boolean) => void;
  showTotal: boolean;
  onToggleTotal: (checked: boolean) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <span className="text-ink-3">出すサイト</span>
      {sites.map((site) => {
        const color = colors.get(site.site_id);
        const disabled = site.status !== "ok";
        return (
          <label
            key={site.site_id}
            className={disabled ? "flex items-center gap-2 text-ink-3" : "flex cursor-pointer items-center gap-2"}
            title={disabled ? "取得できなかったサイトは選べません" : undefined}
          >
            <Checkbox
              checked={isSelected(site.site_id)}
              disabled={disabled}
              onCheckedChange={(checked) => onToggle(site.site_id, checked)}
              // 枠と塗りをサイトの線の色にする
              style={{ borderColor: color, backgroundColor: isSelected(site.site_id) ? color : undefined, color: "white" }}
            />
            {site.name}
          </label>
        );
      })}
      <label className="flex cursor-pointer items-center gap-2 font-medium" title="分ごとの推移に、選んだサイトの合計を出す">
        <Checkbox
          checked={showTotal}
          onCheckedChange={(checked) => onToggleTotal(checked)}
          // 合計はサイトの色を使わず墨色
          style={{ borderColor: "var(--ink)", backgroundColor: showTotal ? "var(--ink)" : undefined, color: "white" }}
        />
        合計
      </label>
    </div>
  );
}
