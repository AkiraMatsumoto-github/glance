import { AppHeader } from "@/components/app-header";

// ログインした後の画面の共通部分（docs/01_design/screen_design.md §1）
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
