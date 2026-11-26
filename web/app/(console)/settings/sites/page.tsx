"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Notice } from "@/components/notice";
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

// サイト設定（docs/01_design/screen_design.md §4）
export default function SitesPage() {
  const [sites, setSites] = useState<Site[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<Site | null>(null);

  const load = useCallback(
    () =>
      api<Site[]>("/api/sites").then(setSites, (e: unknown) => {
        setError(errorMessage(e));
      }),
    [],
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

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">サイト設定</h1>
        <Button className="ml-auto" onClick={() => setAdding(true)}>
          サイトを追加
        </Button>
      </div>

      {error && <Notice>{error}</Notice>}

      <div className="rounded-xl border bg-surface">
        {sites === null ? (
          <p className="px-4 py-10 text-center text-ink-3">読み込み中…</p>
        ) : sites.length === 0 ? (
          <p className="px-4 py-10 text-center text-ink-3">
            まだサイトがありません。「サイトを追加」から GA4 のプロパティを選んでください。
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24 pl-4">並び</TableHead>
                <TableHead>名前</TableHead>
                <TableHead>GA4 プロパティ ID</TableHead>
                <TableHead>タイムゾーン</TableHead>
                <TableHead className="w-20 pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sites.map((site, i) => (
                <TableRow key={site.id}>
                  <TableCell className="pl-4">
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`${site.name}を上へ`}
                        disabled={i === 0}
                        onClick={() => move(site, i - 1)}
                      >
                        <ArrowUp />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`${site.name}を下へ`}
                        disabled={i === sites.length - 1}
                        onClick={() => move(site, i + 1)}
                      >
                        <ArrowDown />
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>
                    <NameInput key={site.name} site={site} onSave={(name) => rename(site, name)} />
                  </TableCell>
                  <TableCell className="tabular-nums">{site.ga4_property_id}</TableCell>
                  <TableCell>{site.timezone}</TableCell>
                  <TableCell className="pr-4 text-right">
                    <Button variant="destructive" size="sm" onClick={() => setDeleting(site)}>
                      削除
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <AddSiteDialog
        open={adding}
        onOpenChange={setAdding}
        onAdded={async () => {
          setAdding(false);
          await load();
        }}
      />

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
    </div>
  );
}

// 名前はその場で編集し、Enter か欄を離れたときに保存する
function NameInput({ site, onSave }: { site: Site; onSave: (name: string) => void }) {
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

// GA4 のプロパティを、アカウントごとにまとめて選ぶ。追加済みは選べない
function AddSiteDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => Promise<void>;
}) {
  const [accounts, setAccounts] = useState<GaAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api<GaAccount[]>("/api/ga4/properties").then(
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
  }, [open]);

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
          <DialogDescription>ログインしたアカウントが見られる GA4 のプロパティから選びます。</DialogDescription>
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
                  <li key={p.property_id} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate" title={p.name}>
                      {p.name}
                    </span>
                    <span className="text-xs text-ink-3 tabular-nums">{p.property_id}</span>
                    {p.added ? (
                      <span className="w-14 text-right text-xs text-ink-3">追加済み</span>
                    ) : (
                      <Button size="sm" className="w-14" disabled={busy} onClick={() => add(p.property_id)}>
                        追加
                      </Button>
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
