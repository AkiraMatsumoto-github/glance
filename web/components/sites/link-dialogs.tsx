"use client";

import { type ReactNode, useEffect, useState } from "react";

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
import type { BingSites, Site } from "@/lib/types";

// サイト設定の、Search Console と Bing の紐づけのダイアログ（docs/01_design/screen_design.md §4）。
// 紐づけの保存は、本物の紐づけの API を作るときに足す。今、紐づけを返すのはデモだけなので、
// 「紐づける」「保存」などのボタンは押せないままにする（デモでは、ホバーで理由を出す）

const NONE = ""; // 「紐づけない」

// 開いたときに一覧を取る。サイトごとに作り直すので、選んだ値はサイトを変えると初めに戻る
function useList<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    api<T>(url).then(
      (result) => {
        if (!cancelled) setData(result);
      },
      (e: unknown) => {
        if (!cancelled) setError(errorMessage(e));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url]);
  return { data, error };
}

// サイトの一覧から1つ選ぶ。最後に「紐づけない」
function SiteChoices({
  name,
  options,
  value,
  onChange,
  demo,
}: {
  name: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
  demo: boolean;
}) {
  return (
    <fieldset disabled={demo} title={demo ? LOCKED : undefined}>
      <legend className="mb-1.5 text-xs font-medium text-ink-3">サイト</legend>
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
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

function LinkDialog({
  open,
  onOpenChange,
  title,
  description,
  demo,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  demo: boolean;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            やめる
          </Button>
          <Locked demo={demo}>
            <Button disabled>紐づける</Button>
          </Locked>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Search Console のサイトを選ぶ。ログインしたアカウントが見られるサイトの一覧から
export function GscDialog({
  site,
  url,
  demo,
  onClose,
}: {
  site: Site | null;
  url: string;
  demo: boolean;
  onClose: () => void;
}) {
  return (
    <LinkDialog
      open={site !== null}
      onOpenChange={(open) => !open && onClose()}
      title="Search Console のサイトを選ぶ"
      description={`「${site?.name ?? ""}」に紐づける Search Console のサイトを、ログインしたアカウントが見られるサイトから選びます。`}
      demo={demo}
    >
      {site && <GscChoices key={site.id} site={site} url={url} demo={demo} />}
    </LinkDialog>
  );
}

function GscChoices({ site, url, demo }: { site: Site; url: string; demo: boolean }) {
  const { data, error } = useList<string[]>(url);
  const [value, setValue] = useState(site.links?.gsc_site_url ?? NONE);
  if (error) return <Notice>{error}</Notice>;
  if (!data) return <p className="text-ink-3">読み込み中…</p>;
  return <SiteChoices name="gsc" options={data} value={value} onChange={setValue} demo={demo} />;
}

// Bing を設定する。API キーは利用者ごとに1つで、全サイトに使う。キーは画面に出さない（「見る」を押したときだけ）
export function BingDialog({
  site,
  url,
  demo,
  onClose,
}: {
  site: Site | null;
  url: string;
  demo: boolean;
  onClose: () => void;
}) {
  return (
    <LinkDialog
      open={site !== null}
      onOpenChange={(open) => !open && onClose()}
      title="Bing を設定"
      description={`Bing Webmaster Tools の API キーで見られるサイトから、「${site?.name ?? ""}」に紐づけるサイトを選びます。`}
      demo={demo}
    >
      {site && <BingChoices key={site.id} site={site} url={url} demo={demo} />}
    </LinkDialog>
  );
}

function BingChoices({ site, url, demo }: { site: Site; url: string; demo: boolean }) {
  const { data, error } = useList<BingSites>(url);
  const [value, setValue] = useState(site.links?.bing_site_url ?? NONE);
  if (error) return <Notice>{error}</Notice>;
  if (!data) return <p className="text-ink-3">読み込み中…</p>;
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="bing-key" className="mb-1.5 block text-xs font-medium text-ink-3">
          API キー
        </label>
        <div className="flex gap-2">
          <Input
            id="bing-key"
            type="password"
            autoComplete="off"
            placeholder={data.key_saved ? "保存済み（入れ直すときだけ入れる）" : "API キーを貼り付ける"}
            disabled={demo}
            title={demo ? LOCKED : undefined}
          />
          {data.key_saved && (
            <Locked demo={demo}>
              <Button variant="outline" disabled>
                見る
              </Button>
            </Locked>
          )}
          <Locked demo={demo}>
            <Button variant="outline" disabled>
              保存
            </Button>
          </Locked>
        </div>
        <p className="mt-1.5 text-xs text-ink-3">
          キーは1つで全サイトに使います。Bing Webmaster Tools の「設定」→「API アクセス」で発行します。
        </p>
      </div>
      <SiteChoices name="bing" options={data.sites} value={value} onChange={setValue} demo={demo} />
    </div>
  );
}
