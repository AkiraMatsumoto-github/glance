"use client";

import type { ReactNode } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

// 数字のカードの部品（docs/01_design/design_guideline.md §6）。リアルタイムと SEO の画面で共通に使う

export const CARD = "relative rounded-xl border bg-surface";
// 押せるカードは、ホバーで面を灰色にする
export const CARD_CLICKABLE = `${CARD} cursor-pointer transition-colors hover:bg-hover`;

// 指標名と数字。大きな数字は、幅をそろえない数字のまま出す（design_guideline.md §3）。
// sub には、比べる期間との差などを小さく添える
export function Stat({
  label,
  value,
  size,
  sub,
}: {
  label: string;
  value: ReactNode;
  size: "lg" | "md" | "sm";
  sub?: ReactNode;
}) {
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
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

// 色の付いたチェックボックスと名前。枠と塗りを線の色にする。
// 名前（ラベル）の当たり判定を、疑似要素でカード全体に広げる（カードは relative にする）。
// カード全体をラベルにすると、読み上げの名前が数字まで含んだ長い文になるため、この形にする
export function Toggle({
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
