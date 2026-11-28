#!/usr/bin/env bash
# VPS の上で、送られてきたコミットを新しいリリースとして出す。**root で動く**。
# 人が直接は実行しない。手元の scripts/deploy_prod.sh が送り込んで sudo で呼ぶ（開設手順 deploy/vps_setup.md §6）。
#
#   sudo bash release.sh <コミット（40桁）> <アーカイブ（コードと書き出した画面）>
#
# 1. /srv/glance/releases/<日時>-<コミット>/ に展開する。動いているリリースには触らない
# 2. Python の環境を作る（uv.lock のとおり。テスト用のパッケージは入れない）
# 3. DB のマイグレーションを当てる（alembic upgrade head）。⚠️ 自動では戻さない。
#    当てた後も、切り替えるまでは前のリリースが動くので、マイグレーションは前のコードを壊さない形で書く
# 4. current を向け替えて API を再起動する → 画面と API が答えるまで待つ。答えなければ前のリリースに戻す
# 5. 古いリリースを消す（新しい順に KEEP 個と、動いているものを残す）
#
# 1〜3 で失敗したら、何も切り替えずに止まる（前のリリースが動いたまま）。毎日の取り込み（glance-sync）も current を使う
set -eEuo pipefail

commit=${1:?コミットを渡してください}
archive=${2:?アーカイブを渡してください}
ROOT=/srv/glance
ENV_FILE=/etc/glance/glance.env
PORT=8101
KEEP=3

[[ $commit =~ ^[0-9a-f]{40}$ ]] || { echo "コミットの形が違います: $commit" >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo "root で実行してください" >&2; exit 1; }

# 環境変数のファイルを読む（マイグレーションが GLANCE_DATABASE_URL を使う）。シェルとして評価しない
# （パスワードに $ などがあっても崩れない）
while IFS= read -r line || [ -n "$line" ]; do
  if [[ $line =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]]; then export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"; fi
done < "$ENV_FILE"

# glance ユーザーで動かす。HOME を合わせないと uv のキャッシュと Python の置き場所が root の場所を向く
as_app() { runuser -u glance -- env HOME="$ROOT" "$@"; }
# リンクを一度に向け替える（途中で無い瞬間を作らない）
switch() { ln -sfn "$2" "$ROOT/$1.tmp" && mv -Tf "$ROOT/$1.tmp" "$ROOT/$1"; }

rel=$ROOT/releases/$(date -u +%Y%m%d%H%M%S)-${commit:0:7}
echo "── 1. 展開: $rel"
install -d -o glance -g glance "$ROOT/releases" "$rel"
tar -xzf "$archive" -C "$rel"
chown -R glance:glance "$rel"
# 作業はリリースの中で行う（sudo は呼んだ人のホームにいたままなので、uv がそこの設定ファイルを探しに行かないように）
cd "$rel"

echo "── 2. Python の環境"
# Python 3.14 が無ければ、uv が最初に入れる（/srv/glance の下。2回目からは使い回す）
as_app uv sync --quiet --frozen --no-dev --no-editable

echo "── 3. マイグレーション"
as_app "$rel/.venv/bin/alembic" upgrade head

echo "── 4. 切り替え"
prev=$(readlink -f "$ROOT/current" || true)
restore() {
  if [ -n "$prev" ] && [ -d "$prev" ]; then
    echo "⚠️ 新しいリリースが答えないので、前のリリースに戻します: $prev" >&2
    switch current "$prev"
    systemctl restart glance-api
  fi
}
trap restore ERR
switch current "$rel"
systemctl restart glance-api
login=000
me=000
for _ in $(seq 1 30); do
  login=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login" || true)
  me=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/me" || true)
  [ "$login" = 200 ] && [ "$me" = 401 ] && break
  sleep 1
done
echo "   /login → $login（200 のはず）、/api/me → $me（ログインしていないので 401 のはず）"
if [ "$login" != 200 ] || [ "$me" != 401 ]; then
  echo "API が30秒たっても答えません（sudo journalctl -u glance-api -n 50 で原因を見る）" >&2
  false
fi
trap - ERR
echo "   ${commit:0:7} で動いています"

echo "── 5. 古いリリースを消す（新しい順に $KEEP 個と、動いているものを残す）"
cur=$(readlink -f "$ROOT/current")
find "$ROOT/releases" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +$((KEEP + 1)) | while read -r d; do
  if [ "$d" != "$cur" ]; then rm -rf "$d"; echo "   消した: $d"; fi
done
rm -f "$archive"
echo "完了: ${commit:0:7} を出しました"
