import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";

// お知らせ。状態の色は、必ずアイコンと文と一緒に出す（docs/01_design/design_guideline.md §2.3・§6）
const STYLES = {
  error: { box: "border-error-border bg-error-bg text-error", Icon: CircleAlert },
  warning: { box: "border-warning-border bg-warning-bg text-warning", Icon: TriangleAlert },
  success: { box: "border-success-border bg-success-bg text-success", Icon: CircleCheck },
} as const;

export function Notice({
  kind = "error",
  className,
  children,
}: {
  kind?: keyof typeof STYLES;
  className?: string;
  children: React.ReactNode;
}) {
  const { box, Icon } = STYLES[kind];
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={cn("flex items-start gap-2 rounded-xl border px-4 py-3 text-sm", box, className)}
    >
      <Icon className="mt-[0.2rem] size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}
