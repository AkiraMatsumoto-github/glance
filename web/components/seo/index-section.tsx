"use client";

import { useState } from "react";

import { Segmented } from "@/components/segmented";
import { SelectPrompt } from "@/components/site-selection";
import { DateLineChart, type DateRow } from "@/components/seo/date-line-chart";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCompact, formatDate, formatNumber, formatPercent } from "@/lib/format";
import type { SeoEngine, SeoSite } from "@/lib/types";

// インデックス（docs/01_design/screen_design.md §7）。日ごとの推移のすぐ下に、Google と Bing で同じ形で出す。
// サイトごとの表（サイトマップの URL・インデックス・割合）と、推移のグラフ。
// Google は、Search Console の API ではインデックス登録の数を取れないので、期間中に検索に1回でも出た
// （imp 1回以上の）ページを目安にする。Bing は、Bing のインデックス数（クロールの数字）を使う

const NUM = "text-right tabular-nums";

type CrawlMetric = "indexed" | "crawled" | "errors";
const CRAWL_LABELS: Record<CrawlMetric, string> = { indexed: "インデックス数", crawled: "クロール数", errors: "クロールエラー" };

function ratio(indexed: number | null, sitemap: number | null): string {
  return indexed !== null && sitemap ? formatPercent(indexed / sitemap) : "—";
}

function SiteName({ site, colors }: { site: SeoSite; colors: Map<number, string> }) {
  return (
    <span className="flex items-center gap-2">
      <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
      {site.name}
    </span>
  );
}

export function IndexSection({
  engine,
  sites,
  colors,
}: {
  engine: SeoEngine;
  sites: SeoSite[];
  colors: Map<number, string>;
}) {
  const [crawlMetric, setCrawlMetric] = useState<CrawlMetric>("indexed");
  // 合計には、サイトマップの URL とインデックスの両方がそろったサイトだけを足す
  // （片方だけのサイトを入れると、割合がずれる。Bing だけ連携してサイトマップを読めないサイトなど）
  const complete = sites.flatMap(({ index }) =>
    index.sitemap_urls !== null && index.indexed !== null ? [{ sitemap: index.sitemap_urls, indexed: index.indexed }] : [],
  );
  const totalSitemap = complete.reduce((n, c) => n + c.sitemap, 0);
  const totalIndexed = complete.reduce((n, c) => n + c.indexed, 0);
  const totalLabel = complete.length === sites.length ? "合計" : `合計（サイトマップを読めた${complete.length}サイト）`;

  // 推移: Google は日ごとの検索に出たページ数、Bing はクロールの数字（インデックス数・クロール数・クロールエラー）
  const days = engine === "google" ? (sites[0]?.index.daily ?? []) : (sites[0]?.crawl ?? []);
  const rows: DateRow[] = days.map((day, i) => {
    const row: DateRow = { date: day.date };
    for (const site of sites) {
      row[`s${site.site_id}`] = engine === "google" ? (site.index.daily?.[i]?.pages ?? null) : (site.crawl?.[i]?.[crawlMetric] ?? null);
    }
    return row;
  });
  // ホバーのカードの見出し
  const chartTitle = engine === "google" ? "検索に出たページ数" : CRAWL_LABELS[crawlMetric];

  return (
    <section className="rounded-xl border bg-surface">
      <div className="border-b px-4 py-3">
        <h2 className="text-base font-medium">インデックス</h2>
        <p className="mt-0.5 text-xs text-ink-3">
          {engine === "google"
            ? "期間中に1回以上検索に出た（imp 1回以上の）ページのうち、サイトマップにあるものの数。Search Console の API ではインデックス登録の数を取れないための目安で、出ていないページは、インデックスされていないか順位が低いかのどちらかです。"
            : "Bing のインデックス数（期間の最後の日）。"}
        </p>
      </div>

      {sites.length === 0 ? (
        <SelectPrompt />
      ) : (
        <>
          {/* サイトごとの数。スマホでは表を横にスクロールさせる */}
          <Table className="min-w-[560px]">
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">サイト</TableHead>
                <TableHead className={NUM}>サイトマップの URL</TableHead>
                <TableHead className={NUM}>{engine === "google" ? "検索に出たページ（imp 1回以上）" : "インデックス数"}</TableHead>
                <TableHead className={`${NUM} pr-4`}>割合</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sites.map((site) => {
                const index = site.index;
                return (
                  <TableRow key={site.site_id}>
                    <TableCell className="pl-4">
                      <SiteName site={site} colors={colors} />
                    </TableCell>
                    {index.sitemap_urls === null ? (
                      <TableCell className={`${NUM} text-ink-3`}>サイトマップを読めていません</TableCell>
                    ) : (
                      <TableCell
                        className={NUM}
                        title={index.sitemap_checked_at ? `${formatDate(index.sitemap_checked_at)}に読んだサイトマップ` : undefined}
                      >
                        {formatNumber(index.sitemap_urls)}
                      </TableCell>
                    )}
                    <TableCell
                      className={NUM}
                      title={
                        index.pages_shown !== null ? `サイトマップに無いページも含めると ${formatNumber(index.pages_shown)}` : undefined
                      }
                    >
                      {index.indexed === null ? "—" : formatNumber(index.indexed)}
                    </TableCell>
                    <TableCell className={`${NUM} pr-4`}>{ratio(index.indexed, index.sitemap_urls)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
            {sites.length > 1 && complete.length > 0 && (
              <TableFooter>
                <TableRow>
                  <TableCell className="pl-4">{totalLabel}</TableCell>
                  <TableCell className={NUM}>{formatNumber(totalSitemap)}</TableCell>
                  <TableCell className={NUM}>{formatNumber(totalIndexed)}</TableCell>
                  <TableCell className={`${NUM} pr-4`}>{ratio(totalIndexed, totalSitemap)}</TableCell>
                </TableRow>
              </TableFooter>
            )}
          </Table>

          {/* 推移。題と凡例は付けない（サイトの色は、すぐ上の表の色の丸で読む。2026-11-28 利用者の決定）。
              Bing は、インデックス数・クロール数・クロールエラーの切り替えだけを出す。
              インデックス数はその日の在庫なので、サイトを足した合計の線は出さない */}
          {engine === "bing" && (
            // 切り替えは中身の幅にする（横並びの枠に入れないと、横いっぱいに伸びる）
            <div className="flex border-t px-4 pt-3">
              <Segmented
                label="指標"
                options={(Object.keys(CRAWL_LABELS) as CrawlMetric[]).map((m) => ({ value: m, label: CRAWL_LABELS[m] }))}
                value={crawlMetric}
                onChange={setCrawlMetric}
              />
            </div>
          )}
          <div className={engine === "google" ? "border-t px-2 py-4" : "px-2 py-4"}>
            <DateLineChart
              rows={rows}
              series={sites.map((s) => ({ key: `s${s.site_id}`, name: s.name, color: colors.get(s.site_id) }))}
              title={chartTitle}
              format={formatNumber}
              axisFormat={formatCompact}
            />
          </div>
        </>
      )}
    </section>
  );
}
