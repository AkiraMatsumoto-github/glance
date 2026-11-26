import type { OkSite } from "@/lib/types";

// グラフの凡例（design_guideline.md §5）。題のすぐ下に、選んでいるサイトの色の丸と名前を並べる。
// 選ぶのは数字のカードのチェックボックスで、凡例は見るだけ
export function SeriesLegend({
  sites,
  colors,
  showTotal = false,
}: {
  sites: OkSite[];
  colors: Map<number, string>;
  showTotal?: boolean;
}) {
  return (
    <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {sites.map((site) => (
        <li key={site.site_id} className="flex items-center gap-1.5">
          <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
          {site.name}
        </li>
      ))}
      {showTotal && (
        <li className="flex items-center gap-1.5 font-medium text-ink">
          <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: "var(--ink)" }} />
          合計
        </li>
      )}
    </ul>
  );
}
