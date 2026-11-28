#!/usr/bin/env bash
# 本番（VPS）に、GitHub の main にあるコミットを出す。**手元で、人が実行する**（Claude は実行しない）。
# 開設の手順は deploy/vps_setup.md、流れは docs/01_design/technical_design.md §10。
#
#   scripts/deploy_prod.sh              # origin/main の先頭を出す
#   scripts/deploy_prod.sh <コミット>   # main にある過去のコミットを出す
#
# - 出すコミットを一時ディレクトリに書き出し、そこで画面をビルドする（npm ci・npm run build）。
#   **コミットしていない変更は混ざらない**。VPS には Node を入れない（画面は静的ファイルで、API が出す）
# - コードと書き出した画面（web/out）を1つのアーカイブにして送り、VPS で deploy/release.sh を sudo で動かす
# - VPS へは SSH の接続名で入る。**接続名は手元の .env の GLANCE_PROD_SSH から読む**（実行のときに渡した値が優先）。
#   接続名を git に入るファイルに書かない
# - SSH の鍵のパスフレーズを1回（接続を1本にまとめて使い回す）、VPS で sudo のパスワードを1回聞かれる
# - Cloudflare のキャッシュを消す手順は要らない（HTML はキャッシュされず、JS・CSS はファイル名に中身のハッシュが入る）
set -euo pipefail
cd "$(dirname "$0")/.."

CONFIRM="glance"   # 実行前に打ち込む言葉

# .env から、名前を指定した1行の値だけを取り出す。.env を丸ごとは読み込まない（ほかの鍵をシェルに入れない）。
# `export ` 付きの行も読み、行末の CR（Windows の改行）と値の前後の引用符を外す（LeadHub の scripts/deploy_prod.sh と同じ）
env_value() {
  [ -f .env ] || return 0
  local line value
  line=$(grep -E "^[[:space:]]*(export[[:space:]]+)?$1=" .env | tail -n 1) || return 0
  value=${line#*=}
  value=${value%$'\r'}
  value=${value#[\"\']}
  value=${value%[\"\']}
  printf '%s' "$value"
}
HOST="${GLANCE_PROD_SSH:-$(env_value GLANCE_PROD_SSH)}"
: "${HOST:?.env の GLANCE_PROD_SSH に SSH の接続名を書いてください}"

git fetch -q origin main
commit=$(git rev-parse --verify "${1:-origin/main}^{commit}")
if ! git merge-base --is-ancestor "$commit" origin/main; then
  echo "GitHub の main に無いコミットです。push してから流すか、main にあるコミットを指定してください: $commit" >&2
  exit 1
fi
echo "出すコミット: $(git log -1 --format='%h %ci %s' "$commit")"

# 終わったら（途中で失敗しても）、作業用のディレクトリを消し、SSH の接続を閉じる
work=$(mktemp -d)
ssh_sock="$work/cm"
cleanup() {
  ssh -o ControlPath="$ssh_sock" -O exit "$HOST" 2>/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT

# 書き出して、画面をビルドする。確認の前に行い、失敗したら本番には何も送らない
mkdir "$work/src"
git archive "$commit" | tar -x -C "$work/src"
echo "画面をビルドします（npm ci・npm run build）"
( cd "$work/src/web" && npm ci --no-audit --no-fund --loglevel=error && npm run build )
[ -f "$work/src/web/out/index.html" ] || { echo "画面の書き出し（web/out/index.html）がありません" >&2; exit 1; }
rm -rf "$work/src/web/node_modules" "$work/src/web/.next"   # 送らない（大きい・VPS では使わない）
tar -czf "$work/glance.tar.gz" -C "$work/src" .
echo "アーカイブ: $(du -h "$work/glance.tar.gz" | cut -f1)"

read -r -p "本番（glance のサーバー $HOST）に出します。よければ $CONFIRM と入力: " answer </dev/tty
if [ "$answer" != "$CONFIRM" ]; then
  echo "中止しました（本番は変えていません）"
  exit 1
fi

# SSH の接続を1本だけ張り、下の3回（送る2回・出す1回）で使い回す。手元の ~/.ssh/config は変えない
ssh -o ControlMaster=yes -o ControlPath="$ssh_sock" -o ControlPersist=600 -fN "$HOST"   # パスフレーズはここで1回
vps() { ssh -o ControlPath="$ssh_sock" "$@"; }

archive=/tmp/glance-$commit.tar.gz
script=/tmp/glance-release-${commit:0:7}.sh
vps "$HOST" "cat > $archive" < "$work/glance.tar.gz"
git show "$commit:deploy/release.sh" | vps "$HOST" "cat > $script"

# VPS で出す（sudo のパスワードを聞くので端末を割り当てる）
vps -t "$HOST" "sudo bash $script $commit $archive; rc=\$?; rm -f $script $archive; exit \$rc"
