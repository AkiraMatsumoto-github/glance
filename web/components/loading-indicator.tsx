import { LoaderCircle } from "lucide-react";

// 読み込み中の印（design_guideline.md §6）。画面の真ん中に小さく出し、クリックは下の画面に通す
// （取っている間も、前の数字を見たり操作したりできるようにするため）
export function LoadingIndicator({ label = "取得中…" }: { label?: string }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-30 flex items-center justify-center" role="status" aria-live="polite">
      <div className="flex items-center gap-2 rounded-xl border bg-surface px-4 py-3 text-sm text-ink-2 shadow-pop">
        <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
        {label}
      </div>
    </div>
  );
}
