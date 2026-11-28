# glance

GA4・Search Console・Bing のデータを日次で取り込み、管理コンソールで AI に質問すると集計結果をグラフ・表で返す分析ツール。最初は LogiShift で使い、将来は外販する。

## 手元で動かす

今できているのは次のとおり（[roadmap.md](docs/01_design/roadmap.md) §1）。Google・Bing を使わずにダミーの数字で動かすこともできる（フェイクモード。[technical_design.md](docs/01_design/technical_design.md) §11）。

- リアルタイム: Google でログインし、GA4 のリアルタイムの数字を出す
- SEO: Search Console・Bing から取り込んだ数字（合計・日ごとの推移・インデックス・クエリ・ページ）
- サイト設定: GA4 のプロパティの追加と、Search Console・Bing の連携
- デモ: ログインせずに、ダミーの数字で上の画面を見る（`/demo`）

1. `.env.example` を `.env` に写し、値を入れる。
   - `GLANCE_DB_PASSWORD`: 手元で決めた長いランダムな文字列
   - `GLANCE_DATABASE_URL`: `postgresql+psycopg://glance:<GLANCE_DB_PASSWORD の値>@127.0.0.1:5434/glance`
   - `GLANCE_ALLOWED_EMAILS`: ログインに使う Google アカウントのメールアドレス（フェイクモードでは、最初のアドレスとしてログインする）
   - `GLANCE_PUBLIC_URL`: `http://localhost:3100`
   - Google でログインするとき: `GLANCE_GOOGLE_CLIENT_ID`・`GLANCE_GOOGLE_CLIENT_SECRET`（GCP の OAuth クライアント。リダイレクト URI に `http://localhost:3100/api/auth/callback` を登録）と、`GLANCE_TOKEN_KEY`（作り方は technical_design.md §5）。`GLANCE_FAKE_GOOGLE` は空
   - ダミーの数字で動かすとき: `GLANCE_FAKE_GOOGLE` を `1`
2. DB を起動し、テーブルを作る。

   ```bash
   docker compose up -d
   uv sync
   uv run alembic upgrade head
   ```

3. API と画面を起動する（端末を2つ使う）。

   ```bash
   uv run uvicorn glance.main:create_app --factory --host 127.0.0.1 --port 8101 --reload
   cd web && npm install && npm run dev
   ```

4. http://localhost:3100 を開き、「Google でログイン」→「サイト設定」で GA4 のプロパティを追加 →「リアルタイム」。
5. Search Console・Bing の数字を見るときは、「サイト設定」で連携してから取り込む（VPS に出すまでは手元で、数週間に1回は動かす。Bing は古い日から消えていくため）。

   ```bash
   uv run python -m glance.sync                 # 連携した全サイトの Search Console と Bing
   uv run python -m glance.sync --source bing   # Bing だけ（--site <サイト ID> で絞れる）
   ```

**暗号化の鍵を入れ替えたとき**: `GLANCE_TOKEN_KEY` を「新しい鍵,古い鍵」にしてから `uv run python -m glance.rekey`。`--check` で 0件になったら古い鍵を外す（手順は technical_design.md §5）

**テスト**: `uv run pytest`（手元の DB コンテナに `glance_test` を作って使う）、`cd web && npm run lint`。いつ何を流すかは下の「テストの決まり」

**画面の自動テスト**（ブラウザで動かす。ふだんの `uv run pytest` では飛ばす）: `cd web && npm run build` で画面を書き出してから、`GLANCE_E2E=1 uv run pytest tests/e2e`。ブラウザは `uv run playwright install chromium` で入れる（別の場所のものを使うときは `GLANCE_E2E_CHROMIUM` に実行ファイルのパス）

**本番と同じ形で見る**: `cd web && npm run build` で `web/out` に書き出すと、API（8101）が画面も出す。http://127.0.0.1:8101 を開く。

**本番（VPS）に出す**: 最初の1回は [deploy/vps_setup.md](deploy/vps_setup.md) の手順。その後は、main に push してから `scripts/deploy_prod.sh`（手元の `.env` に `GLANCE_PROD_SSH` を書いておく）

## テストの決まり

CI は使わず、直した人（Claude も含む）が手で流す。

**直し終えたら流すもの**（変えたものに当てはまる行を全部）

| 変えたもの | 流すもの |
|---|---|
| 設計書・README・コメントだけ | なし |
| Python（`src/`・`tests/`・`migrations/`） | `uv run pytest` と `uvx pyflakes src tests`。pytest は全部で十数秒なので、ファイルを絞らない |
| 画面（`web/`） | `cd web && npm run lint && npx tsc --noEmit && npm run build` |
| 画面の動き（画面の移動・ボタン・API の呼び方）、API の応答の形、ログイン | 上に加えて、画面の自動テスト（`npm run build` の後に `GLANCE_E2E=1 uv run pytest tests/e2e`） |

- 迷ったら `scripts/check.sh` で全部流す（1分ほど）。
- 直している途中は、関係するファイルだけ流してよい。

**結果の扱い**

- 報告には、流したものと結果（通った・飛ばした・失敗した件数）を書く。流さなかったものがあれば、そう書く。
- 失敗したら直してから報告する。直せなければ、失敗したまま、その出力を付けて報告する。

**テストを足すとき**

- 不具合を直したら、その不具合が起きる形のテストを足す（同じ不具合を2度出さないため）。
- API・取り込みを足したら、決めた動きに加えて「ログインが要る」「ほかの顧客のものに触れない」を確かめる。デモの API は「DB・Google・Bing に触れない」を確かめる。
- テストでは本物の Google・Bing につながない（ダミーか差し替え。`tests/conftest.py` の `google`・`bing`）。

**注意**: pytest は `.env` の DB サーバーに `glance_test` を作り直す。`.env` の DB を本番に向けたまま流さない。

## 設計書

| ファイル | 内容 |
|---|---|
| [docs/01_design/overview.md](docs/01_design/overview.md) | 企画・システム概要（ターゲット、目的、競合との差別化、全体の構成） |
| [docs/01_design/roadmap.md](docs/01_design/roadmap.md) | 開発計画（いまの状態、段階ごとの作業、決めること） |
| [docs/01_design/data_sources.md](docs/01_design/data_sources.md) | データ取得（GA4・GSC・Bing のバッチ、GA4 リアルタイム） |
| [docs/01_design/database_design.md](docs/01_design/database_design.md) | DB 設計 |
| [docs/01_design/api_design.md](docs/01_design/api_design.md) | 集計 API（問い合わせ指定） |
| [docs/01_design/ai_query_design.md](docs/01_design/ai_query_design.md) | 生成 AI（全体サマリー・会話） |
| [docs/01_design/infrastructure_design.md](docs/01_design/infrastructure_design.md) | インフラ（ホスティング、ドメイン、ログイン、秘密の置き場所、バックアップ） |
| [docs/01_design/technical_design.md](docs/01_design/technical_design.md) | 技術構成（ライブラリ、ログインの手順、API、反映の手順） |
| [docs/01_design/screen_design.md](docs/01_design/screen_design.md) | 画面設計 |
| [docs/01_design/design_guideline.md](docs/01_design/design_guideline.md) | デザインガイドライン（色、文字、グラフの描き方） |
