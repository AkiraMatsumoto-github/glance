# glance

GA4・Search Console・Bing のデータを日次で取り込み、管理コンソールで AI に質問すると集計結果をグラフ・表で返す分析ツール。最初は LogiShift で使い、将来は外販する。

## 設計書

| ファイル | 内容 |
|---|---|
| [docs/01_design/overview.md](docs/01_design/overview.md) | 企画・システム概要（ターゲット、目的、競合との差別化、全体の構成） |
| [docs/01_design/data_sources.md](docs/01_design/data_sources.md) | データ取得（GA4・GSC・Bing のバッチ） |
| [docs/01_design/database_design.md](docs/01_design/database_design.md) | DB 設計 |
| [docs/01_design/api_design.md](docs/01_design/api_design.md) | 集計 API（問い合わせ指定） |
| [docs/01_design/ai_query_design.md](docs/01_design/ai_query_design.md) | 生成 AI（全体サマリー・会話） |
