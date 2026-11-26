"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Notice } from "@/components/notice";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

// ログイン画面（docs/01_design/screen_design.md §2）
const MESSAGES: Record<string, string> = {
  not_allowed: "このアカウントは使えません。別の Google アカウントでログインしてください。",
  cancelled: "ログインを中止しました。",
  reauth: "Google の許可が切れました。ログインし直してください。",
  failed: "ログインできませんでした。時間をおいてもう一度試してください。",
};

// ログインは FastAPI が受ける（Google の同意画面へ送る）。許可が切れたときは、同意画面を必ず出して
// 更新トークンをもらい直す（2回目以降の同意では、Google は更新トークンを返さないため）
function LoginForm() {
  const error = useSearchParams().get("error");
  const href = error === "reauth" ? "/api/auth/login?prompt=consent" : "/api/auth/login";
  return (
    <>
      <a href={href} className={buttonVariants({ size: "lg", className: "w-full" })}>
        Google でログイン
      </a>
      {error && <Notice className="w-full text-left">{MESSAGES[error] ?? MESSAGES.failed}</Notice>}
    </>
  );
}

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 py-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Glance</h1>
          <Suspense>
            <LoginForm />
          </Suspense>
        </CardContent>
      </Card>
    </main>
  );
}
