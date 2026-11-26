"use client";

import { useState } from "react";

import { Segmented } from "@/components/segmented";
import { SeriesLegend } from "@/components/series-legend";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber, formatPercent } from "@/lib/format";
import type { SeoSite } from "@/lib/types";

// クエリ・ページの一覧（docs/01_design/screen_design.md §7）。選んだサイトをまとめて、クリックの多い順に20件。
// 「もっと見る」で100件まで。「増えた／減った」で、比べる期間との差の大きい順に並べ替える。
// API はサイトごとの上位100件を返すので、どのサイトの組み合わせでも上位100件はこの中に入る

const NUM = "text-right tabular-nums";
const LIMIT = 20;
const MAX = 100;

type Order = "clicks" | "up" | "down";
const ORDERS: Record<Order, { label: string; empty: string }> = {
  clicks: { label: "クリックの多い順", empty: "この期間に表示された" },
  up: { label: "クリックが増えた順", empty: "クリックが増えた" },
  down: { label: "クリックが減った順", empty: "クリックが減った" },
};

type Row = {
  key: string;
  name: string;
  path: string | null;
  site: SeoSite;
  clicks: number;
  impressions: number;
  position: number;
  change: number | null; // 比べる期間との差。比べる期間の上位に入っていないときは null
};

function rowsOf(kind: "query" | "page", sites: SeoSite[]): Row[] {
  return sites.flatMap((site) => {
    const items =
      kind === "query"
        ? site.queries.map((q) => ({ ...q, name: q.query, path: null }))
        : site.pages.map((p) => ({ ...p, name: p.title, path: p.path }));
    return items.map((item) => ({
      key: `${site.site_id}:${item.path ?? item.name}`,
      name: item.name,
      path: item.path,
      site,
      clicks: item.clicks,
      impressions: item.impressions,
      position: item.position,
      change: item.compare_clicks === null ? null : item.clicks - item.compare_clicks,
    }));
  });
}

function sortRows(rows: Row[], order: Order): Row[] {
  if (order === "up") return rows.filter((r) => (r.change ?? 0) > 0).sort((a, b) => b.change! - a.change!);
  if (order === "down") return rows.filter((r) => (r.change ?? 0) < 0).sort((a, b) => a.change! - b.change!);
  return [...rows].sort((a, b) => b.clicks - a.clicks || b.impressions - a.impressions);
}

function formatChange(change: number | null): string {
  if (change === null) return "—";
  if (change === 0) return "±0";
  return `${change > 0 ? "+" : "-"}${formatNumber(Math.abs(change))}`;
}

export function RankingTable({
  kind,
  sites,
  colors,
  hasCompare,
}: {
  kind: "query" | "page";
  sites: SeoSite[];
  colors: Map<number, string>;
  hasCompare: boolean;
}) {
  const [order, setOrder] = useState<Order>("clicks");
  const [expanded, setExpanded] = useState(false);
  const noun = kind === "query" ? "クエリ" : "ページ";
  // 比べないときは、増えた・減ったで並べられない
  const activeOrder = hasCompare ? order : "clicks";
  const rows = sortRows(rowsOf(kind, sites), activeOrder);
  const shown = rows.slice(0, expanded ? MAX : LIMIT);

  return (
    <section className="rounded-xl border bg-surface">
      <div className="border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="text-base font-medium">{noun}</h2>
          <span className="text-xs text-ink-3">{ORDERS[activeOrder].label}</span>
          {hasCompare && (
            <div className="ml-auto">
              <Segmented
                label="並べ方"
                options={[
                  { value: "clicks", label: "すべて" },
                  { value: "up", label: "増えた" },
                  { value: "down", label: "減った" },
                ]}
                value={order}
                onChange={setOrder}
              />
            </div>
          )}
        </div>
        {sites.length > 0 && <SeriesLegend sites={sites} colors={colors} />}
      </div>

      {sites.length === 0 ? (
        <p className="px-4 py-10 text-center text-ink-3">サイトを選んでください。</p>
      ) : shown.length === 0 ? (
        <p className="px-4 py-6 text-ink-3">
          {ORDERS[activeOrder].empty}
          {noun}はありません。
        </p>
      ) : (
        <>
          {/* スマホでは名前が潰れないよう、表を横にスクロールさせる */}
          <Table className="min-w-[760px] table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10 pl-4">#</TableHead>
                <TableHead>{kind === "query" ? "クエリ" : "ページ（タイトル / パス）"}</TableHead>
                <TableHead className="w-36">サイト</TableHead>
                <TableHead className={`w-20 ${NUM}`}>クリック</TableHead>
                {hasCompare && <TableHead className={`w-24 ${NUM}`}>前と比べて</TableHead>}
                <TableHead className={`w-20 ${NUM}`}>表示回数</TableHead>
                <TableHead className={`w-16 ${NUM}`}>CTR</TableHead>
                <TableHead className={`w-20 ${NUM} pr-4`}>掲載順位</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((row, i) => (
                <TableRow key={row.key}>
                  <TableCell className="pl-4 text-ink-3 tabular-nums">{i + 1}</TableCell>
                  {/* 長いものは省略し、ホバーで全文 */}
                  <TableCell title={row.path ? `${row.name}\n${row.path}` : row.name}>
                    <div className="truncate">{row.name}</div>
                    {row.path && <div className="truncate text-xs text-ink-3">{row.path}</div>}
                  </TableCell>
                  <TableCell>
                    <span className="flex items-center gap-2 truncate">
                      <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(row.site.site_id) }} />
                      <span className="truncate">{row.site.name}</span>
                    </span>
                  </TableCell>
                  <TableCell className={NUM}>{formatNumber(row.clicks)}</TableCell>
                  {hasCompare && (
                    <TableCell
                      className={`${NUM} text-ink-2`}
                      title={row.change === null ? "比べる期間の上位に入っていません" : undefined}
                    >
                      {formatChange(row.change)}
                    </TableCell>
                  )}
                  <TableCell className={NUM}>{formatNumber(row.impressions)}</TableCell>
                  <TableCell className={NUM}>{row.impressions ? formatPercent(row.clicks / row.impressions) : "—"}</TableCell>
                  <TableCell className={`${NUM} pr-4`}>{row.position.toFixed(1)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {rows.length > LIMIT && (
            <div className="border-t px-4 py-2">
              <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
                {expanded ? `上位${LIMIT}件に戻す` : `もっと見る（${Math.min(rows.length, MAX)}件まで）`}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
