"use client";

import { cn } from "@/lib/utils";

// 切り替え（PV / UU、グラフ / 表）。枠の中に並べ、選んだほうを墨色の面に白い文字にする（design_guideline.md §6）
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex rounded-lg border p-0.5" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-md px-3 py-0.5 text-sm",
            value === option.value ? "bg-ink text-white" : "text-ink-2 hover:bg-hover",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
