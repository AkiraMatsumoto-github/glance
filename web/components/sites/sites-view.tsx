"use client";

import { ArrowDown, ArrowUp, CircleCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Notice } from "@/components/notice";
import { PageBar, PageBody } from "@/components/page-bar";
import { AddSiteDialog } from "@/components/sites/add-site-dialog";
import { DeleteSiteDialog } from "@/components/sites/delete-site-dialog";
import { BingDialog, GscDialog } from "@/components/sites/link-dialogs";
import { LOCKED, Locked } from "@/components/sites/locked";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import type { Site } from "@/lib/types";

// サイト設定の中身（docs/01_design/screen_design.md §4・§6）。
// 本物は /api のサイトを扱う。デモは /api/demo のダミーを見るだけで、追加・名前・並び・削除・紐づけはできない。
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
  const remove = (site: Site) => run(() => api(`/api/sites/${site.id}`, { method: "DELETE" }));

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
            <Table className="min-w-[800px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24 pl-4">並び</TableHead>
                  <TableHead className="w-72">名前</TableHead>
                  <TableHead>GA4</TableHead>
                  <TableHead>Search Console</TableHead>
                  <TableHead>Bing</TableHead>
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
                    <TableCell>
                      <LinkCell url={site.links.gsc_site_url} onEdit={() => setGscSite(site)} />
                    </TableCell>
                    <TableCell>
                      <LinkCell url={site.links.bing_site_url} onEdit={() => setBingSite(site)} />
                    </TableCell>
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

        <GscDialog site={gscSite} base={base} demo={demo} onClose={() => setGscSite(null)} onSaved={load} />
        <BingDialog site={bingSite} base={base} demo={demo} onClose={() => setBingSite(null)} onSaved={load} />

        <DeleteSiteDialog site={deleting} onClose={() => setDeleting(null)} onDelete={remove} />
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
