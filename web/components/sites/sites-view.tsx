"use client";

import { ArrowDown, ArrowUp, CircleCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Notice } from "@/components/notice";
import { PageBar, PageBody } from "@/components/page-bar";
import { BingDialog, GscDialog } from "@/components/sites/link-dialogs";
import { LOCKED, Locked } from "@/components/sites/locked";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import type { GaAccount, Site } from "@/lib/types";

// サイト設定の中身（docs/01_design/screen_design.md §4・§6）。
// 本物は /api のサイトを扱う。デモは /api/demo のダミーを見るだけで、追加・名前・並び・削除・紐づけはできない。
// Search Console・Bing の列は、API が紐づけ（links）を返すときだけ出す（今はデモだけ）。
// GA4・Search Console・Bing は、見やすさのため列を分ける
export function SitesView({ demo = false }: { demo?: boolean }) {
  const base = demo ? "/api/demo" : "/api";
  const [sites, setSites] = useState<Site[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<Site | null>(null);
  const [gscSite, setGscSite] = useState<Site | null>(null);
  const [bingSite, setBingSite] = useState<Site | null>(null);

  const load = useCallback(
    () =>
      api<Site[]>(`${base}/sites`).then(setSites, (e: unknown) => {
        setError(errorMessage(e));
      }),
    [base],
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    }
    await load();
  }

  const rename = (site: Site, name: string) =>
    run(() => api(`/api/sites/${site.id}`, { method: "PATCH", json: { name } }));
  const move = (site: Site, position: number) =>
    run(() => api(`/api/sites/${site.id}`, { method: "PATCH", json: { position } }));

  const linking = sites?.some((s) => s.links !== null) ?? false;

  return (
    <>
      {/* 「サイトを追加」は固定バーに置き、スクロールしても常に出す（screen_design.md §1・§4） */}
      <PageBar>
        <div className="flex items-center">
          <Button className="ml-auto" onClick={() => setAdding(true)}>
            サイトを追加
          </Button>
        </div>
      </PageBar>
      <PageBody>
        {/* 題は、ヘッダーのメニューでどの画面かわかるので画面には出さず、読み上げ用だけにする */}
        <h1 className="sr-only">サイト設定</h1>

        {error && <Notice>{error}</Notice>}

        <div className="rounded-xl border bg-surface">
          {sites === null ? (
            <p className="px-4 py-10 text-center text-ink-3">読み込み中…</p>
          ) : sites.length === 0 ? (
            <p className="px-4 py-10 text-center text-ink-3">
              まだサイトがありません。「サイトを追加」から GA4 のプロパティを選んでください。
            </p>
          ) : (
            // スマホでは名前の欄が潰れないよう、表に最小の幅を付けて横にスクロールさせる（ほかの表と同じ）
            <Table className={linking ? "min-w-[800px]" : "min-w-[560px]"}>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24 pl-4">並び</TableHead>
                  <TableHead className="w-72">名前</TableHead>
                  <TableHead>GA4</TableHead>
                  {linking && <TableHead>Search Console</TableHead>}
                  {linking && <TableHead>Bing</TableHead>}
                  <TableHead className="w-20 pr-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sites.map((site, i) => (
                  <TableRow key={site.id}>
                    <TableCell className="pl-4">
                      <div className="flex gap-1">
                        <Locked demo={demo}>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`${site.name}を上へ`}
                            disabled={demo || i === 0}
                            onClick={() => move(site, i - 1)}
                          >
                            <ArrowUp />
                          </Button>
                        </Locked>
                        <Locked demo={demo}>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`${site.name}を下へ`}
                            disabled={demo || i === sites.length - 1}
                            onClick={() => move(site, i + 1)}
                          >
                            <ArrowDown />
                          </Button>
                        </Locked>
                      </div>
                    </TableCell>
                    <TableCell>
                      <NameInput key={site.name} site={site} readOnly={demo} onSave={(name) => rename(site, name)} />
                    </TableCell>
                    <TableCell className="tabular-nums">{site.ga4_property_id}</TableCell>
                    {linking && (
                      <TableCell>
                        <LinkCell url={site.links?.gsc_site_url ?? null} onEdit={() => setGscSite(site)} />
                      </TableCell>
                    )}
                    {linking && (
                      <TableCell>
                        <LinkCell url={site.links?.bing_site_url ?? null} onEdit={() => setBingSite(site)} />
                      </TableCell>
                    )}
                    <TableCell className="pr-4 text-right">
                      <Locked demo={demo}>
                        <Button variant="destructive" size="sm" disabled={demo} onClick={() => setDeleting(site)}>
                          削除
                        </Button>
                      </Locked>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <AddSiteDialog
          propertiesUrl={`${base}/ga4/properties`}
          demo={demo}
          open={adding}
          onOpenChange={setAdding}
          onAdded={async () => {
            setAdding(false);
            await load();
          }}
        />

        <GscDialog site={gscSite} url={`${base}/gsc/sites`} demo={demo} onClose={() => setGscSite(null)} />
        <BingDialog site={bingSite} url={`${base}/bing/sites`} demo={demo} onClose={() => setBingSite(null)} />

        <Dialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>サイトを削除しますか？</DialogTitle>
              <DialogDescription>「{deleting?.name}」を削除します。GA4 のデータは消えません。</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDeleting(null)}>
                やめる
              </Button>
              <Button
                variant="destructive"
                onClick={async () => {
                  const target = deleting;
                  setDeleting(null);
                  if (target) await run(() => api(`/api/sites/${target.id}`, { method: "DELETE" }));
                }}
              >
                削除する
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </PageBody>
    </>
  );
}

// 名前はその場で編集し、Enter か欄を離れたときに保存する
function NameInput({ site, readOnly, onSave }: { site: Site; readOnly: boolean; onSave: (name: string) => void }) {
  const [value, setValue] = useState(site.name);

  function save() {
    const name = value.trim();
    if (!name) {
      setValue(site.name);
      return;
    }
    if (name !== site.name) onSave(name);
  }

  return (
    <Input
      aria-label={`${site.name}の名前`}
      value={value}
      readOnly={readOnly}
      title={readOnly ? LOCKED : undefined}
      maxLength={200}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          setValue(site.name);
          e.currentTarget.blur();
        }
      }}
      className="max-w-64"
    />
  );
}

// Search Console・Bing の紐づけ。サイトの URL は出さず「連携あり／連携なし」だけにする（ホバーで紐づけ先）。
// 状態の色は、アイコンと文と一緒に使う（design_guideline.md §2.3）
function LinkCell({ url, onEdit }: { url: string | null; onEdit: () => void }) {
  return (
    <div className="flex items-center gap-3">
      {url ? (
        <span className="flex items-center gap-1.5 whitespace-nowrap" title={url}>
          <CircleCheck className="size-4 shrink-0 text-success" aria-hidden />
          連携あり
        </span>
      ) : (
        <span className="whitespace-nowrap text-ink-3">連携なし</span>
      )}
      <Button variant="outline" size="xs" onClick={onEdit}>
        {url ? "変更" : "設定する"}
      </Button>
    </div>
  );
}

// GA4 のプロパティを、アカウントごとにまとめて選ぶ。追加済みは選べない。
// 紐づけの API があるときは、同じドメインの Search Console のサイトも一緒に紐づける（見つからなければ選ぶ）
function AddSiteDialog({
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
  const [accounts, setAccounts] = useState<GaAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const withGsc = accounts?.some((a) => a.properties.some((p) => p.search_console !== null)) ?? false;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api<GaAccount[]>(propertiesUrl).then(
      (result) => {
        if (!cancelled) setAccounts(result);
      },
      (e: unknown) => {
        if (!cancelled) setError(errorMessage(e));
      },
    );
    return () => {
      cancelled = true;
      setAccounts(null);
      setError(null);
    };
  }, [open, propertiesUrl]);

  async function add(propertyId: string) {
    setBusy(true);
    setError(null);
    try {
      await api("/api/sites", { method: "POST", json: { property_id: propertyId } });
      await onAdded();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>サイトを追加</DialogTitle>
          <DialogDescription>
            ログインしたアカウントが見られる GA4 のプロパティから選びます。
            {withGsc && "同じドメインの Search Console のサイトも一緒に紐づけます。"}
          </DialogDescription>
        </DialogHeader>
        {error && <Notice>{error}</Notice>}
        <div className="max-h-96 space-y-4 overflow-y-auto">
          {accounts === null && !error && <p className="text-ink-3">読み込み中…</p>}
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
                          <Button size="sm" className="w-14" disabled={demo || busy} onClick={() => add(p.property_id)}>
                            追加
                          </Button>
                        </Locked>
                      )}
                    </div>
                    {/* 一緒に紐づける Search Console のサイト。初めは同じドメインのもの（なければ「紐づけない」）。
                        選んだ値を追加と一緒に送るのは、本物の紐づけの API を作るときに足す（今はデモだけが出す） */}
                    {!p.added && p.search_console && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
                        <span>Search Console</span>
                        <Locked demo={demo}>
                          <select
                            aria-label={`${p.name}と一緒に紐づける Search Console のサイト`}
                            defaultValue={p.search_console.site_url ?? ""}
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
      </DialogContent>
    </Dialog>
  );
}
