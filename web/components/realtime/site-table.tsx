import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import type { Realtime, RealtimeErrorKind } from "@/lib/types";

export const ERROR_LABELS: Record<RealtimeErrorKind, string> = {
  timeout: "時間切れ",
  permission_denied: "権限がない",
  quota: "上限に当たった",
  error: "その他",
};

const NUM = "text-right tabular-nums";

// サイト別の表。いつも全サイトを出す（サイトの選択は効かない）
export function SiteTable({ data, colors }: { data: Realtime; colors: Map<number, string> }) {
  const failed = data.sites.filter((s) => s.status === "error").length;
  const { last_30_min: t30, last_5_min: t5 } = data.total;
  return (
    <div className="rounded-xl border bg-background">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">サイト</TableHead>
            <TableHead className={NUM}>PV 30分</TableHead>
            <TableHead className={NUM}>PV 5分</TableHead>
            <TableHead className={NUM}>UU 30分</TableHead>
            <TableHead className={NUM}>UU 5分</TableHead>
            <TableHead className={`${NUM} pr-4`}>キーイベント</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.sites.map((site) => (
            <TableRow key={site.site_id}>
              <TableCell className="pl-4">
                <span className="flex items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
                  {site.name}
                </span>
              </TableCell>
              {site.status === "ok" ? (
                <>
                  <TableCell className={NUM}>{formatNumber(site.last_30_min.page_views)}</TableCell>
                  <TableCell className={NUM}>{formatNumber(site.last_5_min.page_views)}</TableCell>
                  <TableCell className={NUM}>{formatNumber(site.last_30_min.active_users)}</TableCell>
                  <TableCell className={NUM}>{formatNumber(site.last_5_min.active_users)}</TableCell>
                  <TableCell className={`${NUM} pr-4`}>{formatNumber(site.last_30_min.key_events)}</TableCell>
                </>
              ) : (
                <TableCell colSpan={5} className="pr-4 text-muted-foreground">
                  取得できませんでした（{ERROR_LABELS[site.error]}）
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell className="pl-4 font-medium">
              合計
              {failed > 0 && <span className="ml-1 font-normal text-muted-foreground">（{failed}サイトを除く）</span>}
            </TableCell>
            <TableCell className={NUM}>{formatNumber(t30.page_views)}</TableCell>
            <TableCell className={NUM}>{formatNumber(t5.page_views)}</TableCell>
            <TableCell className={NUM}>{formatNumber(t30.active_users)}</TableCell>
            <TableCell className={NUM}>{formatNumber(t5.active_users)}</TableCell>
            <TableCell className={`${NUM} pr-4`}>{formatNumber(t30.key_events)}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}
