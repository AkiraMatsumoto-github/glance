# glance

GA4・Search Console・Bing のデータを日次で取り込み、管理コンソールで AI に質問すると集計結果をグラフ・表で返す分析ツール。最初は LogiShift で使い、将来は外販する。

## 手元で動かす

今できているのは1番目の段階（リアルタイム画面）。Google でログインし、GA4 のリアルタイムの数字を出す。Google を使わずにダミーの数字で動かすこともできる（フェイクモード。[technical_design.md](docs/01_design/technical_design.md) §11）。

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

**テスト**: `uv run pytest`（手元の DB コンテナに `glance_test` を作って使う）、`cd web && npm run lint`

**本番と同じ形で見る**: `cd web && npm run build` で `web/out` に書き出すと、API（8101）が画面も出す。http://127.0.0.1:8101 を開く。

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
