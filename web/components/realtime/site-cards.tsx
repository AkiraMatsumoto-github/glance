"use client";

import { CircleAlert } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { formatNumber } from "@/lib/format";
import type { OkSite, RealtimeErrorKind, RealtimeSite, Totals } from "@/lib/types";
import { cn } from "@/lib/utils";

// 数字のカード（docs/01_design/screen_design.md §3）。直近30分の PV・UU・キーイベント。
// 上に選んだサイトの合計を横いっぱいに、その下にサイトごとのカードを並べる。
// カードのチェックボックスが、出すサイトの選択とグラフの凡例を兼ねる

const ERROR_LABELS: Record<RealtimeErrorKind, string> = {
  timeout: "時間切れ",
  permission_denied: "権限がない",
  quota: "上限に当たった",
  error: "その他",
};

// 大きな数字は、幅をそろえない数字のまま出す（design_guideline.md §3）
function Stat({ label, value, size }: { label: string; value: number; size: "lg" | "md" | "sm" }) {
  return (
    <div>
      <div className="text-xs text-ink-3">{label}</div>
      <div
        className={cn(
          "leading-tight text-ink",
          size === "lg" && "text-4xl font-semibold",
          size === "md" && "text-2xl font-semibold",
          size === "sm" && "text-base font-medium",
        )}
      >
        {formatNumber(value)}
      </div>
    </div>
  );
}

// 色の付いたチェックボックスと名前。枠と塗りを線の色にする。
// 名前（ラベル）の当たり判定を、疑似要素でカード全体に広げる（カードは relative にする）。
// カード全体をラベルにすると、読み上げの名前が数字まで含んだ長い文になるため、この形にする
function Toggle({
  name,
  color,
  checked,
  disabled,
  onChange,
  title,
  className,
}: {
  name: string;
  color: string | undefined;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  title?: string;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex min-w-0 items-center gap-2 font-medium",
        // 薄くした数字（opacity）より上に出すため z-10 にする
        !disabled && "cursor-pointer after:absolute after:inset-0 after:z-10 after:rounded-xl after:content-['']",
        className,
      )}
      title={title}
    >
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={onChange}
        style={{ borderColor: color, backgroundColor: checked ? color : undefined, color: "white" }}
      />
      <span className="truncate" title={name}>
        {name}
      </span>
    </label>
  );
}

const CARD = "relative rounded-xl border bg-surface";
// 押せるカードは、ホバーで面を灰色にする
const CARD_CLICKABLE = `${CARD} cursor-pointer transition-colors hover:bg-hover`;

function sum(sites: OkSite[]): Totals {
  return {
    page_views: sites.reduce((a, s) => a + s.last_30_min.page_views, 0),
    active_users: sites.reduce((a, s) => a + s.last_30_min.active_users, 0),
    key_events: sites.reduce((a, s) => a + s.last_30_min.key_events, 0),
  };
}

export function SiteCards({
  sites,
  selected,
  colors,
  isSelected,
  onToggle,
  showTotal,
  onToggleTotal,
}: {
  sites: RealtimeSite[];
  selected: OkSite[];
  colors: Map<number, string>;
  isSelected: (siteId: number) => boolean;
  onToggle: (siteId: number, checked: boolean) => void;
  showTotal: boolean;
  onToggleTotal: (checked: boolean) => void;
}) {
  const total = sum(selected);
  return (
    <div className="space-y-3">
      {/* 合計。選んだサイトを足す（UU はサイトごとの人数を足したもの）。チェックボックスはグラフの合計の線 */}
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
          <Stat label="PV" value={total.page_views} size="lg" />
          <Stat label="UU" value={total.active_users} size="lg" />
          <Stat label="キーイベント" value={total.key_events} size="sm" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {sites.map((site) => {
          const checked = isSelected(site.site_id);
          return (
            <div
              key={site.site_id}
              className={cn(site.status === "ok" ? CARD_CLICKABLE : CARD, "flex min-w-0 flex-col gap-3 p-4")}
            >
              <Toggle
                name={site.name}
                color={colors.get(site.site_id)}
                checked={checked}
                disabled={site.status !== "ok"}
                onChange={(value) => onToggle(site.site_id, value)}
                title={site.status === "ok" ? "グラフ・内訳・イベント・ページの一覧と合計に入れる" : "取得できなかったサイトは選べません"}
              />
              {site.status === "ok" ? (
                // 外したサイトは、数字を薄くして「合計などに入っていない」ことを示す
                <div className={cn("space-y-3", !checked && "opacity-50")}>
                  <div className="flex gap-6">
                    <Stat label="PV" value={site.last_30_min.page_views} size="md" />
                    <Stat label="UU" value={site.last_30_min.active_users} size="md" />
                  </div>
                  <div className="text-xs text-ink-3">キーイベント {formatNumber(site.last_30_min.key_events)}</div>
                </div>
              ) : (
                <p className="flex items-start gap-1.5 text-ink-2">
                  <CircleAlert className="mt-[0.2rem] size-3.5 shrink-0 text-error" aria-hidden />
                  取得できませんでした（{ERROR_LABELS[site.error]}）
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
