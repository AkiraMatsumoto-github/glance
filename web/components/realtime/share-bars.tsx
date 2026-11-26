"use client";

import { useState } from "react";

import { formatNumber } from "@/lib/format";
import type { BreakdownRow, OkSite } from "@/lib/types";

// 内訳の帯グラフ（100% の積み上げ）。サイトごとに1本並べ、UU の割合を比べる（design_guideline.md §5）。
// デバイス・国はユーザーの属性なので、PV は出さない。割合は区分の UU を足した数に対する割合
// （同じ人が複数の区分から見ると、それぞれに数える）。
// 区分の色は墨色の濃淡で、サイトの色とは混ぜない。濃い2段は白い文字、薄い2段は墨色の文字
const SHADES = [
  { fill: "var(--share-1)", text: "#ffffff" },
  { fill: "var(--share-2)", text: "#ffffff" },
  { fill: "var(--share-3)", text: "var(--ink)" },
  { fill: "var(--share-4)", text: "var(--ink)" },
];
const LABEL_MIN_SHARE = 0.12; // これより細い区分には、帯の中に割合を書かない（凡例とホバーのカードで読む）

export type Category = { key: string; label: string };

function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

type Hover = {
  site: string;
  category: string;
  shade: string;
  activeUsers: number;
  share: number;
  x: number; // 帯の並びの左上からの位置（px）
  y: number;
  flip: boolean; // 右端に近いときは、カーソルの左に出す
};

// ホバーで出すカード。折れ線グラフのカードと同じ見た目にする（design_guideline.md §5）
function HoverCard({ hover }: { hover: Hover }) {
  return (
    <div
      className="pointer-events-none absolute z-20 min-w-44 rounded-xl border bg-surface px-3 py-2.5 text-xs leading-normal shadow-pop"
      style={{
        left: hover.x,
        top: hover.y,
        transform: `translate(${hover.flip ? "calc(-100% - 12px)" : "12px"}, 12px)`,
      }}
    >
      <div className="mb-2 flex items-center gap-1.5 font-medium text-ink">
        <span className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: hover.shade }} />
        {hover.category}
        <span className="font-normal text-ink-3">（{hover.site}）</span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4">
        <dt className="text-ink-2">UU</dt>
        <dd className="text-right font-medium text-ink tabular-nums">
          {formatNumber(hover.activeUsers)}
          <span className="ml-1 font-normal text-ink-3">（{percent(hover.share)}）</span>
        </dd>
      </dl>
    </div>
  );
}

export function ShareBars({
  title,
  note,
  sites,
  colors,
  categories,
  categoryOf,
  rowsOf,
}: {
  title: string;
  note?: string;
  sites: OkSite[];
  colors: Map<number, string>;
  // 区分の並び（4つまで。最後は「その他」など）。帯もこの順に左から並べる
  categories: Category[];
  // API の行の key を、どの区分に入れるか
  categoryOf: (key: string) => string;
  rowsOf: (site: OkSite) => BreakdownRow[];
}) {
  const [hover, setHover] = useState<Hover | null>(null);

  return (
    <section className="rounded-xl border bg-surface">
      <div className="border-b px-4 py-3">
        <h2 className="text-base font-medium">{title}</h2>
        <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          {categories.map((category, i) => (
            <li key={category.key} className="flex items-center gap-1.5">
              <span className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: SHADES[i].fill }} />
              {category.label}
            </li>
          ))}
        </ul>
      </div>
      <ul className="relative space-y-3 px-4 py-4" onMouseLeave={() => setHover(null)}>
        {sites.map((site) => {
          const values = new Map<string, number>();
          for (const row of rowsOf(site)) {
            const key = categoryOf(row.key);
            values.set(key, (values.get(key) ?? 0) + row.active_users);
          }
          const total = [...values.values()].reduce((a, b) => a + b, 0);
          // 読み上げでは、帯全体を「区分 割合」の並びとして読む
          const description = categories
            .filter((c) => (values.get(c.key) ?? 0) > 0)
            .map((c) => `${c.label} ${percent((values.get(c.key) ?? 0) / total)}`)
            .join("、");
          return (
            <li key={site.site_id} className="flex items-center gap-3">
              <span className="flex w-32 shrink-0 items-center gap-2 truncate sm:w-40">
                <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
                <span className="truncate" title={site.name}>
                  {site.name}
                </span>
              </span>
              {total === 0 ? (
                <span className="text-ink-3">直近30分に来た人はいません</span>
              ) : (
                // 区分の間に 2px のすき間を空け、細い区分でも区切りがわかるようにする
                <div
                  className="flex h-6 min-w-0 flex-1 gap-0.5"
                  role="img"
                  aria-label={`${site.name}の${title}: ${description}`}
                >
                  {categories.map((category, i) => {
                    const value = values.get(category.key) ?? 0;
                    if (value === 0) return null;
                    const share = value / total;
                    return (
                      <div
                        key={category.key}
                        className="flex items-center overflow-hidden px-1.5 text-xs leading-none tabular-nums first:rounded-l-[4px] last:rounded-r-[4px]"
                        style={{ flexGrow: value, flexBasis: 0, backgroundColor: SHADES[i].fill, color: SHADES[i].text }}
                        onMouseMove={(event) => {
                          const list = event.currentTarget.closest("ul");
                          if (!list) return;
                          const rect = list.getBoundingClientRect();
                          const x = event.clientX - rect.left;
                          setHover({
                            site: site.name,
                            category: category.label,
                            shade: SHADES[i].fill,
                            activeUsers: value,
                            share,
                            x,
                            y: event.clientY - rect.top,
                            flip: x > rect.width - 220,
                          });
                        }}
                      >
                        {share >= LABEL_MIN_SHARE && percent(share)}
                      </div>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
        {hover && <HoverCard hover={hover} />}
      </ul>
      {note && <p className="border-t px-4 py-2.5 text-xs leading-normal text-ink-3">{note}</p>}
    </section>
  );
}
