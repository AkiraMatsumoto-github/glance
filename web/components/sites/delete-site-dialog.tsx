"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Site } from "@/lib/types";

// サイトを削除する前の確かめ（docs/01_design/screen_design.md §4）。site が null なら閉じている
export function DeleteSiteDialog({
  site,
  onClose,
  onDelete,
}: {
  site: Site | null;
  onClose: () => void;
  onDelete: (site: Site) => void;
}) {
  return (
    <Dialog open={site !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>サイトを削除しますか？</DialogTitle>
          <DialogDescription>
            「{site?.name}」を削除します。取り込んだ Search Console・Bing の数字も一緒に消えます。Bing
            の過去の数字は取り直せません。GA4・Search Console・Bing の側のデータは消えません。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            やめる
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              onClose();
              if (site) onDelete(site);
            }}
          >
            削除する
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
