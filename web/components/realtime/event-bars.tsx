"use client";

import { useState } from "react";

import { SeriesLegend } from "@/components/realtime/series-legend";
import { formatNumber } from "@/lib/format";
import type { OkSite } from "@/lib/types";

// イベント（docs/01_design/screen_design.md §3）。イベント名ごとの直近30分の回数を、
// 回数の多い順に横棒で並べる。棒の中は、選んだサイトごとの色で積み上げる（design_guideline.md §5）

const LIMIT = 10;

// GA4 が自動で送るイベントと、よく使う推奨イベントの日本語の名前。ほかは元の名前のまま出す
const EVENT_LABELS: Record<string, string> = {
  page_view: "ページ表示",
  user_engagement: "エンゲージメント",
  scroll: "スクロール",
  session_start: "セッション開始",
  first_visit: "初回訪問",
  click: "外部リンクのクリック",
  file_download: "ファイルのダウンロード",
  form_start: "フォームの入力開始",
  form_submit: "フォームの送信",
  video_start: "動画の再生開始",
  video_progress: "動画の再生途中",
  video_complete: "動画の再生完了",
  view_search_results: "サイト内検索",
  generate_lead: "リードの獲得",
  sign_up: "会員登録",
  login: "ログイン",
  purchase: "購入",
};

type EventTotal = { name: string; total: number; bySite: { site: OkSite; count: number }[] };

type Hover = { event: EventTotal; x: number; y: number; flip: boolean };

function EventName({ name }: { name: string }) {
  const label = EVENT_LABELS[name];
  // イベント名は外から送られうる文字なので、そのまま文字として出す
  return label ? (
    <>
      {label}
      <span className="ml-1.5 text-xs text-ink-3">{name}</span>
    </>
  ) : (
    <>{name}</>
  );
}

function HoverCard({ hover, colors }: { hover: Hover; colors: Map<number, string> }) {
  return (
    <div
      className="pointer-events-none absolute z-20 min-w-48 rounded-xl border bg-surface px-3 py-2.5 text-xs leading-normal shadow-pop"
      style={{
        left: hover.x,
        top: hover.y,
        transform: `translate(${hover.flip ? "calc(-100% - 12px)" : "12px"}, 12px)`,
      }}
    >
      <div className="mb-2 font-medium text-ink">
        <EventName name={hover.event.name} />
      </div>
      <ul className="space-y-1">
        {hover.event.bySite.map(({ site, count }) => (
          <li key={site.site_id} className="flex items-center gap-2">
            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colors.get(site.site_id) }} />
            <span className="text-ink-2">{site.name}</span>
            <span className="ml-auto pl-4 font-medium text-ink tabular-nums">{formatNumber(count)}</span>
          </li>
        ))}
        <li className="mt-1 flex items-center gap-2 border-t pt-1.5">
          <span className="font-medium text-ink">合計</span>
          <span className="ml-auto pl-4 font-medium text-ink tabular-nums">{formatNumber(hover.event.total)}</span>
        </li>
      </ul>
    </div>
  );
}

export function EventBars({ sites, colors }: { sites: OkSite[]; colors: Map<number, string> }) {
  const [hover, setHover] = useState<Hover | null>(null);

  // 選んだサイトを合わせてイベント名ごとに足し、回数の多い順に並べる
  const totals = new Map<string, Map<number, number>>();
  for (const site of sites) {
    for (const event of site.events) {
      const bySite = totals.get(event.name) ?? new Map<number, number>();
      bySite.set(site.site_id, (bySite.get(site.site_id) ?? 0) + event.event_count);
      totals.set(event.name, bySite);
    }
  }
  const events: EventTotal[] = [...totals.entries()]
    .map(([name, bySite]) => ({
      name,
      total: [...bySite.values()].reduce((a, b) => a + b, 0),
      // 棒の中もホバーのカードも、サイトの並び順にする
      bySite: sites.filter((s) => (bySite.get(s.site_id) ?? 0) > 0).map((s) => ({ site: s, count: bySite.get(s.site_id) ?? 0 })),
    }))
    .sort((a, b) => b.total - a.total);
  const shown = events.slice(0, LIMIT);
  const max = shown[0]?.total ?? 0;

  return (
    <section className="rounded-xl border bg-surface">
      <div className="border-b px-4 py-3">
        <h2 className="text-base font-medium">イベント（回数の多い順）</h2>
        <SeriesLegend sites={sites} colors={colors} />
      </div>
      {shown.length === 0 ? (
        <p className="px-4 py-6 text-ink-3">直近30分のイベントはありません。</p>
      ) : (
        <ul className="relative space-y-2.5 px-4 py-4" onMouseLeave={() => setHover(null)}>
          {shown.map((event) => (
            <li key={event.name} className="flex items-center gap-3">
              <span className="w-32 shrink-0 truncate sm:w-56" title={event.name}>
                <EventName name={event.name} />
              </span>
              <div className="flex min-w-0 flex-1 items-center gap-2">
                {/* 棒の長さは、いちばん多いイベントに対する比。サイトの区切りは、長さを変えない内側の白い線にする
                    （すき間にすると、回数の少ない棒で区切りが棒より長くなって崩れるため） */}
                <div
                  className="flex h-5 overflow-hidden rounded-[4px]"
                  style={{ width: `${(event.total / max) * 100}%` }}
                  role="img"
                  aria-label={`${event.name}: ${event.bySite.map(({ site, count }) => `${site.name} ${count}`).join("、")}、合計 ${event.total}`}
                  onMouseMove={(e) => {
                    const list = e.currentTarget.closest("ul");
                    if (!list) return;
                    const rect = list.getBoundingClientRect();
                    const x = e.clientX - rect.left;
                    setHover({ event, x, y: e.clientY - rect.top, flip: x > rect.width - 240 });
                  }}
                >
                  {event.bySite.map(({ site, count }) => (
                    <div
                      key={site.site_id}
                      className="shadow-[inset_-2px_0_0_var(--surface)] last:shadow-none"
                      style={{ flexGrow: count, flexBasis: 0, backgroundColor: colors.get(site.site_id) }}
                    />
                  ))}
                </div>
                <span className="shrink-0 text-xs text-ink-2 tabular-nums">{formatNumber(event.total)}</span>
              </div>
            </li>
          ))}
          {hover && <HoverCard hover={hover} colors={colors} />}
        </ul>
      )}
      {events.length > LIMIT && (
        <p className="border-t px-4 py-2.5 text-xs text-ink-3">ほかに {events.length - LIMIT} 種類のイベントがあります。</p>
      )}
    </section>
  );
}
