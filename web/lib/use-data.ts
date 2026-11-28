"use client";

import { useEffect, useState } from "react";

import { api, errorMessage } from "@/lib/api";

// API から取る・API に送るときの共通の部品

// ダイアログの一覧を取る。url が null のあいだは取らない。url か reload が変われば取り直し、
// 取り終えるまでは null を返す（前の url の一覧は出さない。選んだキーと違うサイトを選べてしまうため）。
// reload は、同じ url でも取り直したいとき（キーを入れ直したときなど）に増やす
export function useData<T>(url: string | null, reload = 0) {
  const request = url === null ? null : `${url}#${reload}`;
  const [result, setResult] = useState<{ request: string; data?: T; error?: string } | null>(null);
  useEffect(() => {
    if (url === null) return;
    const key = `${url}#${reload}`;
    let cancelled = false;
    api<T>(url).then(
      (data) => {
        if (!cancelled) setResult({ request: key, data });
      },
      (e: unknown) => {
        if (!cancelled) setResult({ request: key, error: errorMessage(e) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url, reload]);
  return result !== null && result.request === request ? result : null;
}

// 画面の数字を取る。開いたとき・url が変わったとき・reload() で取る。取り終えるまでは前の数字を出したままにする
// （条件を続けて変えたときは、最後の条件の結果だけを出す）。
// cache は最後に取った結果（url ごと）。ほかの画面から戻ったときに、取り終えるまでの間これを出す
// （ブラウザのメモリだけ。読み込み直すと消える）。本物とデモで url が違うので、数字は混ざらない
export function useCachedData<T>(url: string | null, cache: Map<string, T>) {
  const [data, setData] = useState<T | null>(() => (url === null ? null : (cache.get(url) ?? null)));
  const [error, setError] = useState<string | null>(null);
  // 「更新」を押した回数。同じ条件でも取り直すため、取る条件の印に入れる
  const [reloads, setReloads] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const request = url === null ? null : `${url}#${reloads}`;

  useEffect(() => {
    if (url === null) return;
    const key = `${url}#${reloads}`;
    let cancelled = false;
    api<T>(url).then(
      (result) => {
        if (cancelled) return;
        cache.set(url, result);
        setData(result);
        setError(null);
        setDone(key);
      },
      (e: unknown) => {
        if (cancelled) return;
        setError(errorMessage(e));
        setDone(key);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [url, reloads, cache]);

  return { data, error, loading: request !== null && request !== done, reload: () => setReloads((n) => n + 1) };
}

// 保存の送信。送っている間はボタンを押せなくし、失敗したら理由を出す
export function useSave(onDone: () => unknown) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, save };
}
