import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import type { RealtimeSite } from "@/lib/types";

type OkSite = Extract<RealtimeSite, { status: "ok" }>;

const NUM = "text-right tabular-nums";
const LIMIT = 20;

// いま読まれている記事。選んだサイトの記事をまとめて PV の多い順に20件（docs/01_design/screen_design.md §3）。
// API はサイトごとの上位20件を返すので、どのサイトの組み合わせでも上位20件はこの中に入る
export function TopPages({ sites, colors }: { sites: OkSite[]; colors: Map<number, string> }) {
  const rows = sites
    .flatMap((site) => site.top_pages.map((page) => ({ ...page, site })))
    .sort((a, b) => b.page_views - a.page_views || b.active_users - a.active_users)
    .slice(0, LIMIT);

  if (rows.length === 0) {
    return <p className="px-4 py-6 text-sm text-muted-foreground">直近30分に読まれた記事はありません。</p>;
  }
  return (
    // スマホではタイトルが潰れないよう、表を横にスクロールさせる
    <Table className="min-w-[640px] table-fixed">
      <TableHeader>
        <TableRow>
          <TableHead className="w-10 pl-4">#</TableHead>
          <TableHead>タイトル</TableHead>
          <TableHead className="w-36">サイト</TableHead>
          <TableHead className={`w-20 ${NUM}`}>PV 30分</TableHead>
          <TableHead className={`w-20 ${NUM} pr-4`}>UU 30分</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={`${row.site.site_id}-${row.title}`}>
            <TableCell className="pl-4 text-muted-foreground tabular-nums">{i + 1}</TableCell>
            {/* タイトルは文字として出す。長いものは省略し、ホバーで全文 */}
            <TableCell className="truncate" title={row.title}>
              {row.title}
            </TableCell>
            <TableCell>
              <span className="flex items-center gap-2 truncate">
                <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(row.site.site_id) }} />
                <span className="truncate">{row.site.name}</span>
              </span>
            </TableCell>
            <TableCell className={NUM}>{formatNumber(row.page_views)}</TableCell>
            <TableCell className={`${NUM} pr-4`}>{formatNumber(row.active_users)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
