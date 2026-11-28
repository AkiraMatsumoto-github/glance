"use client";

import { useState } from "react";

import { LoadingIndicator } from "@/components/loading-indicator";
import { Notice } from "@/components/notice";
import { PageBar, PageBody } from "@/components/page-bar";
import { DailySection } from "@/components/seo/daily-section";
import { IndexSection } from "@/components/seo/index-section";
import { RankingTable } from "@/components/seo/ranking-table";
import { DEFAULT_FILTER, SeoBar, type SeoFilter, seoUrl } from "@/components/seo/seo-bar";
import { SeoCards } from "@/components/seo/seo-cards";
import { EmptySites, useSiteSelection } from "@/components/site-selection";
import type { Seo, SeoEngine } from "@/lib/types";
import { useCachedData } from "@/lib/use-data";

// 最後に取った結果（URL ごと）。ほかの画面から戻ったときや条件を変えたときに、取り終えるまでの間これを出す
const lastResults = new Map<string, Seo>();

const ENGINE_LABELS: Record<SeoEngine, string> = { google: "Search Console", bing: "Bing" };

// SEO の画面の中身（docs/01_design/screen_design.md §7）。開いたとき・条件を変えたとき・「更新」を押したときに取る。
// 本物（/api/seo）とデモ（/api/demo/seo）で共通にし、取り元だけを変える
export function SeoView({ endpoint }: { endpoint: string }) {
  const [filter, setFilter] = useState<SeoFilter>(DEFAULT_FILTER);
  const { data, error, loading, reload } = useCachedData<Seo>(seoUrl(endpoint, filter), lastResults);
  const { colors, unselected, toggle, showTotal, setShowTotal } = useSiteSelection(data?.sites);
  const selected = (data?.sites ?? []).filter((s) => !unselected.has(s.site_id));
  const hasCompare = data?.compare != null;

  return (
    <>
      {/* 条件と「更新」は固定バーに置き、スクロールしても常に出す（screen_design.md §1・§7） */}
      <PageBar>
        <SeoBar
          filter={filter}
          onChange={(next) => setFilter((prev) => ({ ...prev, ...next }))}
          data={data}
          loading={loading}
          onReload={reload}
        />
      </PageBar>
      <PageBody>
        {/* 題は、ヘッダーのメニューでどの画面かわかるので画面には出さず、読み上げ用だけにする */}
        <h1 className="sr-only">SEO</h1>

        {error && <Notice>{error}</Notice>}

        {/* 取っている間は、前の数字はそのまま出し、画面の真ん中に印を出すだけにする */}
        {loading && <LoadingIndicator />}

        {/* 本物で、まだ連携していないとき・まだ取り込んでいないとき（デモは、いつも数字がある） */}
        {data && data.sites.length === 0 && (
          <EmptySites>{ENGINE_LABELS[data.engine]}と連携しているサイトがありません。サイト設定で連携してください。</EmptySites>
        )}
        {data && data.sites.length > 0 && data.data_until === null && (
          <Notice kind="warning">
            まだ{ENGINE_LABELS[data.engine]}の数字を取り込んでいません。取り込みのコマンド（uv run python -m glance.sync）を動かすと出ます。
          </Notice>
        )}

        {data && data.sites.length > 0 && (
          <div className="space-y-5">
            <SeoCards
              engine={data.engine}
              sites={data.sites}
              selected={selected}
              colors={colors}
              hasCompare={hasCompare}
              onToggle={toggle}
              showTotal={showTotal}
              onToggleTotal={setShowTotal}
            />

            <DailySection
              engine={data.engine}
              sites={selected}
              colors={colors}
              showTotal={showTotal}
              hasCompare={hasCompare}
            />

            {/* インデックス（Google は検索に出たページ、Bing はインデックス数）とサイトマップ。日ごとの推移のすぐ下 */}
            <IndexSection engine={data.engine} sites={selected} colors={colors} />

            {/* Bing のクエリは今は取らない（data_sources.md §4） */}
            {data.engine === "google" && <RankingTable kind="query" sites={selected} colors={colors} hasCompare={hasCompare} />}
            <RankingTable kind="page" sites={selected} colors={colors} hasCompare={hasCompare} />
          </div>
        )}
      </PageBody>
    </>
  );
}
