#!/usr/bin/env bash
# テストと検査を全部流す（README の「テストの決まり」）。手元で使う。
# 画面の自動テストのブラウザを別の場所から使うときは、GLANCE_E2E_CHROMIUM に実行ファイルのパスを入れておく。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Python の検査"
uvx pyflakes src tests
echo "== API・取り込みのテスト"
uv run pytest -q
echo "== 画面の lint・型チェック・ビルド"
(cd web && npm run lint && npx tsc --noEmit && npm run build)
echo "== 画面の自動テスト"
GLANCE_E2E=1 uv run pytest -q tests/e2e
echo "全部通りました"
