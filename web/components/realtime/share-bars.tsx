import { formatNumber } from "@/lib/format";
import type { BreakdownRow, OkSite } from "@/lib/types";

// 内訳の帯グラフ（100% の積み上げ）。サイトごとに1本並べ、割合を比べる（design_guideline.md §5）。
// 区分の色は墨色の濃淡で、サイトの色とは混ぜない。濃い2段は白い文字、薄い2段は墨色の文字
const SHADES = [
  { fill: "var(--share-1)", text: "#ffffff" },
  { fill: "var(--share-2)", text: "#ffffff" },
  { fill: "var(--share-3)", text: "var(--ink)" },
  { fill: "var(--share-4)", text: "var(--ink)" },
];
const LABEL_MIN_SHARE = 0.12; // これより細い区分には、帯の中に割合を書かない（凡例とホバーで読む）

export type Category = { key: string; label: string };

function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
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
      <ul className="space-y-3 px-4 py-4">
        {sites.map((site) => {
          const values = new Map<string, number>();
          for (const row of rowsOf(site)) {
            const key = categoryOf(row.key);
            values.set(key, (values.get(key) ?? 0) + row.page_views);
          }
          const total = [...values.values()].reduce((a, b) => a + b, 0);
          return (
            <li key={site.site_id} className="flex items-center gap-3">
              <span className="flex w-32 shrink-0 items-center gap-2 truncate sm:w-40">
                <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
                <span className="truncate" title={site.name}>
                  {site.name}
                </span>
              </span>
              {total === 0 ? (
                <span className="text-ink-3">直近30分の PV はありません</span>
              ) : (
                // 区分の間に 2px のすき間を空け、細い区分でも区切りがわかるようにする
                <div className="flex h-6 min-w-0 flex-1 gap-0.5" role="img" aria-label={`${site.name}の${title}`}>
                  {categories.map((category, i) => {
                    const value = values.get(category.key) ?? 0;
                    if (value === 0) return null;
                    const share = value / total;
                    return (
                      <div
                        key={category.key}
                        className="flex items-center overflow-hidden px-1.5 text-xs leading-none tabular-nums first:rounded-l-[4px] last:rounded-r-[4px]"
                        style={{ flexGrow: value, flexBasis: 0, backgroundColor: SHADES[i].fill, color: SHADES[i].text }}
                        title={`${category.label}: PV ${formatNumber(value)}（${percent(share)}）`}
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
      </ul>
      {note && <p className="border-t px-4 py-2.5 text-xs leading-normal text-ink-3">{note}</p>}
    </section>
  );
}
