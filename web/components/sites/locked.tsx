import type { ReactNode } from "react";

// デモでは変更できない操作。押せなくし、ホバーで理由を出す
// （押せないボタンはホバーを受けないので、理由は外側の枠に付ける）
export const LOCKED = "デモでは変更できません";

export function Locked({ demo, children }: { demo: boolean; children: ReactNode }) {
  return demo ? (
    <span title={LOCKED} className="inline-flex">
      {children}
    </span>
  ) : (
    children
  );
}
