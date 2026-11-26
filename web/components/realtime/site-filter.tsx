"use client";

import { Checkbox } from "@/components/ui/checkbox";
import type { RealtimeSite } from "@/lib/types";

// 出すサイトの選択。分ごとの推移と、いま読まれている記事の両方に効く。グラフの凡例も兼ねる
export function SiteFilter({
  sites,
  colors,
  isSelected,
  onToggle,
}: {
  sites: RealtimeSite[];
  colors: Map<number, string>;
  isSelected: (siteId: number) => boolean;
  onToggle: (siteId: number, checked: boolean) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
      <span className="text-muted-foreground">出すサイト</span>
      {sites.map((site) => {
        const color = colors.get(site.site_id);
        const disabled = site.status !== "ok";
        return (
          <label
            key={site.site_id}
            className={disabled ? "flex items-center gap-2 text-muted-foreground" : "flex cursor-pointer items-center gap-2"}
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
    </div>
  );
}
