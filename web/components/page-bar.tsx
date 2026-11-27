import type { ReactNode } from "react";

// 画面の組み立て（docs/01_design/screen_design.md §1）。ヘッダーの下に固定バー、その下に中身。

// 固定バー。画面全体に効く操作（期間・切り替え・更新・追加など）を置き、スクロールしても常に出す。
// 画面の端から端まで白い面と下の線で、ヘッダーの2段目のように見せる。
// ヘッダー（高さ 56px・z-40）のすぐ下に付け、z-20 でカードより上に出す
export function PageBar({ children }: { children: ReactNode }) {
  return (
    <div className="sticky top-14 z-20 border-b bg-surface">
      <div className="mx-auto max-w-6xl space-y-1.5 px-4 py-2.5 sm:px-6">{children}</div>
    </div>
  );
}

// 中身。幅と余白を画面の間でそろえる（design_guideline.md §4）
export function PageBody({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-6xl space-y-5 px-4 py-6 sm:px-6">{children}</div>;
}
