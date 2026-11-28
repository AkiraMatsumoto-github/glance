"use client";

import { useState } from "react";

import { Notice } from "@/components/notice";
import { Locked } from "@/components/sites/locked";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import type { GaAccount, GaProperty } from "@/lib/types";
import { useData, useSave } from "@/lib/use-data";

// サイトを追加するダイアログ（docs/01_design/screen_design.md §4）。
// GA4 のプロパティを、アカウントごとにまとめて選ぶ。追加済みは選べない。
// 紐づけの API があるときは、同じドメインの Search Console のサイトも一緒に紐づける（見つからなければ選ぶ）
export function AddSiteDialog({
  propertiesUrl,
  demo,
  open,
  onOpenChange,
  onAdded,
}: {
  propertiesUrl: string;
  demo: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {/* 開くたびに作り直し、プロパティの一覧を取り直す（追加済みの印を新しくする） */}
        {open && <AddSiteBody propertiesUrl={propertiesUrl} demo={demo} onAdded={onAdded} />}
      </DialogContent>
    </Dialog>
  );
}

function AddSiteBody({
  propertiesUrl,
  demo,
  onAdded,
}: {
  propertiesUrl: string;
  demo: boolean;
  onAdded: () => Promise<void>;
}) {
  const loaded = useData<GaAccount[]>(propertiesUrl);
  const accounts = loaded?.data ?? null;
  const { busy, error, save } = useSave(onAdded);
  // プロパティごとに選んだ Search Console のサイト。選んでいなければ、同じドメインのサイト
  const [gscPicked, setGscPicked] = useState<Record<string, string>>({});
  const withGsc = accounts?.some((a) => a.properties.some((p) => p.search_console !== null)) ?? false;
  // 追加できるプロパティがあるのに Search Console のサイトの一覧を取れなかった（API を有効にしていないなど）
  const gscUnavailable = !withGsc && (accounts?.some((a) => a.properties.some((p) => !p.added)) ?? false);

  function gscValue(p: GaProperty): string {
    return gscPicked[p.property_id] ?? p.search_console?.site_url ?? "";
  }

  function add(p: GaProperty) {
    void save(() =>
      api("/api/sites", {
        method: "POST",
        json: { property_id: p.property_id, gsc_site_url: p.search_console ? gscValue(p) || null : null },
      }),
    );
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>サイトを追加</DialogTitle>
        <DialogDescription>
          ログインしたアカウントが見られる GA4 のプロパティから選びます。
          {withGsc && "同じドメインの Search Console のサイトも一緒に紐づけます。"}
        </DialogDescription>
      </DialogHeader>
      {loaded?.error && <Notice>{loaded.error}</Notice>}
      {error && <Notice>{error}</Notice>}
      {gscUnavailable && (
        <Notice kind="warning">
          Search Console のサイトの一覧を取れませんでした（Search Console API を有効にしていないなど）。追加した後に、表の「設定する」から選べます。
        </Notice>
      )}
      <div className="max-h-96 space-y-4 overflow-y-auto">
        {loaded === null && <p className="text-ink-3">読み込み中…</p>}
        {accounts?.length === 0 && <p className="text-ink-3">見られるプロパティがありません。</p>}
        {accounts?.map((account) => (
          <div key={account.account_id}>
            <div className="mb-1.5 text-xs font-medium text-ink-3">{account.name}</div>
            <ul className="divide-y rounded-lg border">
              {account.properties.map((p) => (
                <li key={p.property_id} className="px-3 py-2 text-sm">
                  <div className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 truncate" title={p.name}>
                      {p.name}
                    </span>
                    <span className="text-xs text-ink-3 tabular-nums">{p.property_id}</span>
                    {p.added ? (
                      <span className="w-14 text-right text-xs text-ink-3">追加済み</span>
                    ) : (
                      <Locked demo={demo}>
                        <Button size="sm" className="w-14" disabled={demo || busy} onClick={() => add(p)}>
                          追加
                        </Button>
                      </Locked>
                    )}
                  </div>
                  {/* 一緒に紐づける Search Console のサイト。初めは同じドメインのもの（なければ「紐づけない」） */}
                  {!p.added && p.search_console && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
                      <span>Search Console</span>
                      <Locked demo={demo}>
                        <select
                          aria-label={`${p.name}と一緒に紐づける Search Console のサイト`}
                          value={gscValue(p)}
                          onChange={(e) => setGscPicked((prev) => ({ ...prev, [p.property_id]: e.target.value }))}
                          disabled={demo}
                          className="h-7 max-w-64 rounded-md border bg-surface px-2 text-xs text-ink"
                        >
                          {p.search_console.candidates.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                          <option value="">紐づけない</option>
                        </select>
                      </Locked>
                      {p.search_console.site_url === null && <span>同じドメインのサイトが見つかりません</span>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}
