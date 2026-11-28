"use client";

import { type ReactNode, useState } from "react";

import { Notice } from "@/components/notice";
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
import { api, errorMessage } from "@/lib/api";
import type { BingKey, GscChoice, Site } from "@/lib/types";
import { useData, useSave } from "@/lib/use-data";

// サイト設定の、Search Console と Bing の紐づけのダイアログ（docs/01_design/screen_design.md §4）。
// 本物は /api、デモは /api/demo から一覧を取る。デモは見るだけで、保存などのボタンは押せない

const NONE = ""; // 「紐づけない」

type DialogProps = {
  site: Site | null; // 開いているサイト。null なら閉じている
  base: string; // /api か /api/demo
  demo: boolean;
  onClose: () => void;
  onSaved: () => void; // 保存したら一覧を読み直す
};

// サイトの一覧から1つ選ぶ。最後に「紐づけない」
function SiteChoices({
  name,
  options,
  value,
  onChange,
  demo,
  badge,
}: {
  name: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
  demo: boolean;
  badge?: (option: string) => ReactNode;
}) {
  return (
    <fieldset disabled={demo} title={demo ? LOCKED : undefined}>
      <legend className="mb-1.5 text-xs font-medium text-ink-3">サイト</legend>
      {options.length === 0 && <p className="mb-2 text-ink-3">見られるサイトがありません。</p>}
      <ul className="max-h-60 divide-y overflow-y-auto rounded-lg border">
        {[...options, NONE].map((option) => (
          <li key={option || "none"}>
            <label className="flex cursor-pointer items-center gap-2.5 px-3 py-2 text-sm in-disabled:cursor-default">
              <input
                type="radio"
                name={name}
                value={option}
                checked={value === option}
                onChange={() => onChange(option)}
                className="accent-ink"
              />
              {option ? <span className="truncate">{option}</span> : <span className="text-ink-3">紐づけない</span>}
              {option && badge?.(option)}
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

function LinkDialog({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}

// disabled は、まだ保存できないとき（Bing でキーを保存していないなど）。busy は送っている間だけ
function Footer({
  demo,
  busy,
  disabled = false,
  onCancel,
  onSave,
}: {
  demo: boolean;
  busy: boolean;
  disabled?: boolean;
  onCancel: () => void;
  onSave: () => void;
}) {
  return (
    <DialogFooter>
      <Button variant="outline" onClick={onCancel}>
        やめる
      </Button>
      <Locked demo={demo}>
        <Button disabled={demo || busy || disabled} onClick={onSave}>
          {busy ? "保存中…" : "保存"}
        </Button>
      </Locked>
    </DialogFooter>
  );
}

// --- Search Console -------------------------------------------------------------------------

// ログインしたアカウントが見られるサイトから選ぶ。連携なしなら、同じドメインのサイトを初めから選んでおく
export function GscDialog({ site, base, demo, onClose, onSaved }: DialogProps) {
  return (
    <LinkDialog
      open={site !== null}
      onClose={onClose}
      title="Search Console のサイトを選ぶ"
      description={`「${site?.name ?? ""}」に紐づける Search Console のサイトを、ログインしたアカウントが見られるサイトから選びます。`}
    >
      {site && <GscBody key={site.id} site={site} base={base} demo={demo} onClose={onClose} onSaved={onSaved} />}
    </LinkDialog>
  );
}

function GscBody({ site, base, demo, onClose, onSaved }: DialogProps & { site: Site }) {
  const loaded = useData<GscChoice>(`${base}/sites/${site.id}/gsc`);
  const [picked, setPicked] = useState<string | null>(null);
  const { busy, error, save } = useSave(() => {
    onSaved();
    onClose();
  });
  if (!loaded) return <p className="text-ink-3">読み込み中…</p>;
  if (!loaded.data) return <Notice>{loaded.error}</Notice>;
  const choice = loaded.data;
  const value = picked ?? choice.current ?? choice.suggested ?? NONE;
  return (
    <>
      {error && <Notice>{error}</Notice>}
      <SiteChoices
        name="gsc"
        options={choice.candidates}
        value={value}
        onChange={setPicked}
        demo={demo}
        badge={(option) =>
          option === choice.suggested && <span className="ml-auto shrink-0 text-xs text-ink-3">同じドメイン</span>
        }
      />
      <Footer
        demo={demo}
        busy={busy}
        onCancel={onClose}
        onSave={() =>
          save(() => api(`/api/sites/${site.id}/gsc`, { method: "PUT", json: { site_url: value || null } }))
        }
      />
    </>
  );
}

// --- Bing -----------------------------------------------------------------------------------

// 使う API キーを選び（初めてなら名前を付けて入れる）、そのキーで見られるサイトから選ぶ。
// キーは顧客ごとに複数持て、画面には名前と末尾4文字だけを出す
export function BingDialog({ site, base, demo, onClose, onSaved }: DialogProps) {
  return (
    <LinkDialog
      open={site !== null}
      onClose={onClose}
      title="Bing を設定"
      description={`Bing Webmaster Tools の API キーで見られるサイトから、「${site?.name ?? ""}」に紐づけるサイトを選びます。`}
    >
      {site && <BingBody key={site.id} site={site} base={base} demo={demo} onClose={onClose} onSaved={onSaved} />}
    </LinkDialog>
  );
}

const NEW_KEY = "new";
type KeyChoice = number | typeof NEW_KEY;

function BingBody({ site, base, demo, onClose, onSaved }: DialogProps & { site: Site }) {
  const loadedKeys = useData<BingKey[]>(`${base}/bing/keys`);
  const [added, setAdded] = useState<BingKey[]>([]); // このダイアログで保存したキー
  const [picked, setPicked] = useState<KeyChoice | null>(null);
  const [pickedSite, setPickedSite] = useState<string | null>(null);
  // キーを保存・入れ直したら、そのキーで見られるサイトを取り直す（入れ直しは同じ url なので、印を増やす）
  const [sitesReload, setSitesReload] = useState(0);
  const keys = loadedKeys?.data ? [...loadedKeys.data.filter((k) => !added.some((a) => a.id === k.id)), ...added] : null;
  const keyChoice = picked ?? site.links.bing_key_id ?? keys?.[0]?.id ?? NEW_KEY;
  const loadedSites = useData<string[]>(
    keys && keyChoice !== NEW_KEY ? `${base}/bing/keys/${keyChoice}/sites` : null,
    sitesReload,
  );
  const sites = loadedSites?.data ?? null;
  const current = keyChoice === site.links.bing_key_id ? site.links.bing_site_url : null;
  const siteValue = pickedSite !== null && (pickedSite === NONE || sites?.includes(pickedSite)) ? pickedSite : (current ?? NONE);
  const { busy, error, save } = useSave(() => {
    onSaved();
    onClose();
  });

  // キーを選び直したら、サイトは選び直す（初めは、そのキーで紐づけているサイト）
  function pickKey(choice: KeyChoice) {
    setPicked(choice);
    setPickedSite(null);
  }

  function keySaved(key: BingKey) {
    setAdded((prev) => [...prev.filter((k) => k.id !== key.id), key]);
    pickKey(key.id);
    setSitesReload((n) => n + 1);
  }

  if (!loadedKeys) return <p className="text-ink-3">読み込み中…</p>;
  if (!keys) return <Notice>{loadedKeys.error}</Notice>;
  return (
    <>
      {error && <Notice>{error}</Notice>}
      <BingKeyPicker keys={keys} value={keyChoice} demo={demo} onPick={pickKey} onKeySaved={keySaved} />

      {keyChoice === NEW_KEY ? (
        <p className="text-ink-3">キーを保存すると、そのキーで見られるサイトが出ます。</p>
      ) : !loadedSites ? (
        <p className="text-ink-3">読み込み中…</p>
      ) : !sites ? (
        <Notice>{loadedSites.error}</Notice>
      ) : (
        <SiteChoices name="bing" options={sites} value={siteValue} onChange={setPickedSite} demo={demo} />
      )}

      <Footer
        demo={demo}
        busy={busy}
        disabled={keyChoice === NEW_KEY}
        onCancel={onClose}
        onSave={() =>
          save(() =>
            api(`/api/sites/${site.id}/bing`, {
              method: "PUT",
              json: { key_id: keyChoice === NEW_KEY ? null : keyChoice, site_url: siteValue || null },
            }),
          )
        }
      />
    </>
  );
}

// 使うキーを選ぶ。選んだキーは入れ直せ、最後の「新しいキーを追加」で名前を付けて入れる。
// 保存したキー（新しく入れた・入れ直した）は onKeySaved で返す
function BingKeyPicker({
  keys,
  value,
  demo,
  onPick,
  onKeySaved,
}: {
  keys: BingKey[];
  value: KeyChoice;
  demo: boolean;
  onPick: (choice: KeyChoice) => void;
  onKeySaved: (key: BingKey) => void;
}) {
  const [rekeying, setRekeying] = useState(false);

  function pick(choice: KeyChoice) {
    setRekeying(false);
    onPick(choice);
  }

  function saved(key: BingKey) {
    setRekeying(false);
    onKeySaved(key);
  }

  return (
    <fieldset disabled={demo} title={demo ? LOCKED : undefined} className="space-y-2">
      <legend className="mb-1.5 text-xs font-medium text-ink-3">API キー</legend>
      <ul className="divide-y rounded-lg border">
        {keys.map((key) => (
          <li key={key.id} className="px-3 py-2 text-sm">
            <div className="flex items-center gap-2.5">
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 in-disabled:cursor-default">
                <input
                  type="radio"
                  name="bing-key"
                  checked={value === key.id}
                  onChange={() => pick(key.id)}
                  className="accent-ink"
                />
                <span className="truncate">{key.name}</span>
                <span className="shrink-0 text-xs text-ink-3 tabular-nums">末尾 {key.last4}</span>
              </label>
              {value === key.id && !rekeying && (
                <Button variant="outline" size="xs" onClick={() => setRekeying(true)}>
                  入れ直す
                </Button>
              )}
            </div>
            {value === key.id && rekeying && (
              <KeyForm
                submitLabel="入れ直す"
                onCancel={() => setRekeying(false)}
                onSubmit={(_name, secret) =>
                  api<BingKey>(`/api/bing/keys/${key.id}`, { method: "PUT", json: { key: secret } }).then(saved)
                }
              />
            )}
          </li>
        ))}
        <li className="px-3 py-2 text-sm">
          <label className="flex cursor-pointer items-center gap-2.5 in-disabled:cursor-default">
            <input
              type="radio"
              name="bing-key"
              checked={value === NEW_KEY}
              onChange={() => pick(NEW_KEY)}
              className="accent-ink"
            />
            新しいキーを追加
          </label>
          {value === NEW_KEY && (
            <KeyForm
              withName
              submitLabel="キーを保存"
              onSubmit={(name, secret) =>
                api<BingKey>("/api/bing/keys", { method: "POST", json: { name, key: secret } }).then(saved)
              }
            />
          )}
        </li>
      </ul>
      <p className="text-xs text-ink-3">
        キーは Bing Webmaster Tools の「設定」→「API アクセス」で発行します。キーは画面に出さず、末尾4文字だけを出します。入れ直すと、そのキーを使う全サイトに効きます。
      </p>
    </fieldset>
  );
}

// キーを入れる欄。名前は新しいキーのときだけ。保存したら呼び出し元が欄を閉じる
function KeyForm({
  withName = false,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  withName?: boolean;
  submitLabel: string;
  onSubmit: (name: string, key: string) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(name.trim(), key.trim());
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 space-y-2 pl-6">
      {error && <Notice>{error}</Notice>}
      {withName && (
        <Input
          aria-label="キーの名前"
          placeholder="名前（例: LogiShift 用）"
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
      )}
      <div className="flex gap-2">
        <Input
          aria-label="API キー"
          type="password"
          autoComplete="off"
          placeholder="API キーを貼り付ける"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={busy || !key.trim() || (withName && !name.trim())}
          onClick={submit}
        >
          {busy ? "確かめ中…" : submitLabel}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            やめる
          </Button>
        )}
      </div>
    </div>
  );
}
