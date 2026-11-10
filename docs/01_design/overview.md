# glance 企画・システム概要

作成日: 2026-11-10
状態: 初版（実装前）。リポジトリ名は glance。外販するときの製品名は別に決める（§8）。

このファイルには、企画（誰の何を解決するか）と、システム全体の考え方・特徴・主な構成をまとめる。各部分の詳しい設計は §7 の各ファイルに書く。

---

## 1. 企画

### 1.1 背景

- サイトの数字を見るには、GA4・Search Console・Bing Webmaster Tools の3つの管理画面を行き来する必要がある。欲しい集計を出すには、それぞれの画面の操作（探索レポート、フィルタ、比較）を覚える必要もある。
- GA4 にはボットや、ページを見ていないセッションが混ざる。GA4 のデータフィルタは過去のデータには効かないので、これらを除いた数字を過去にさかのぼって見るのが難しい。
- Search Console は16ヶ月、Bing は日次が約98日・ページ別が13週までしか遡れない。取っておかないと消える。

### 1.2 ターゲット（案）

| 段階 | 利用者 |
|---|---|
| 最初 | 自社（LogiShift・TechShift・ConShift の運営） |
| 外販 | 専任のアナリストがいないサイト運営者（メディア・EC・企業サイト）で、GA4 と Search Console を自分で見ている人 |

外販のターゲットは仮説。確かめ方は未定（§8）。

### 1.3 目的

- 自然文で質問すると、それに沿った集計がグラフ・表で出る。条件を変えながら続けて深掘りできる。
  - 「今月の流入数を流入元別に推移で」→ 日付×チャネルのセッション数を折れ線で出す
  - 「そこから各流入の UTM ごとの実数を」→ 直前の条件を引き継ぎ、UTM 別のセッション数を表で出す
- GA4・Search Console・Bing の数字を、1か所で、同じ期間の決め方で見られる。
- 良かった集計はダッシュボードにピン留めし、開くたびに最新の期間で見られる。
- ボットなどを除いた実態に近い数字を、過去分も含めて見られる。

### 1.4 競合と差別化

調査日: 2026-11-10。出典は末尾。

| 競合 | できること | glance との違い |
|---|---|---|
| GA4 の Analytics Advisor（Google） | GA4 の画面内で Gemini に自然文で質問し、グラフ・表・文章で答えを得る。英語のプロパティから展開（日本語の状況は要確認） | GA4 のデータだけ。除外（ボット等）を過去分に当てられない |
| Search Console の AI 設定（Google。2025-12 発表、2026-02 から全ユーザー） | 自然文から、検索パフォーマンスレポートのフィルタ・比較を設定する | Search Console の検索結果レポートだけ。答えではなくレポートの設定を作る。16ヶ月より前は見られない |
| Data Studio（旧 Looker Studio）の Conversational Analytics（Google） | ダッシュボードのデータに自然文で質問する（プレビュー） | GA4・Search Console のデータで使えるかは未確認。データの接続と作り込みが要る |
| GA4 Chat Analyst（アド・セイル） | Gemini を使い、GA4 のデータに自然文で質問すると文章・グラフで答える。複数データソースの横断は今後予定 | 現時点では GA4 だけ |
| SEMAIA（エクスチュア） | GA4 などのデータを自然文で分析するマネージドサービス（2026-06 発表） | 詳細は未確認 |
| 汎用の生成 AI ＋ API 接続（ChatGPT・Claude・Gemini に GA4・Search Console の MCP や Supermetrics をつなぐ） | 何でも聞ける。質問のたびに API を呼ぶ | AI が数字を集計・転記するので、同じ質問でも答えがぶれうる。API の上限に当たる。過去分を貯めない |

**glance の差別化ポイント**

1. **3つのソースを1か所で見られる。** GA4・Search Console・Bing を、同じ画面・同じ期間の決め方で見られる。Bing に対応した製品は、今回調べた範囲にはない。
2. **消える前に貯める。** 毎日取り込んで保存するので、Search Console の16ヶ月や Bing の98日・13週を超えて過去と比べられる。
3. **数字は SQL から出す。** AI は集計の指定を選ぶだけで、数字は DB の集計結果。同じ質問なら同じ数字になり、ピン留めしたカードも同じ定義で集計し直す。
4. **除外を後から切り替えられる。** ボット（言語で判定）や、ページを見ていないセッションの除外を、過去分も含めて画面でオン/オフできる。
5. **質問時に外部 API を呼ばない。** 答えが速く、API の上限を気にしなくてよい。

## 2. システムの考え方

1. **質問時に外部 API を呼ばない。** 1日1回のバッチで Postgres に溜めた日次データだけで答える。
2. **GA4 は「日付×主要項目」の日次集計を、そのまま取得する。** 取得時には絞り込まない。イベント単位の生データは持たない。
3. **ボットなどの除外は画面（SQL）で行う。** 除外に使う列（言語、ランディングページ）を各テーブルに持たせ、除外のオン/オフを画面で切り替える。
4. **画面の数字はすべて SQL の結果から描画する。** AI は数字を作らない。
5. **AI は SQL を書かない。** 決められた指標・軸・期間から「問い合わせ指定」を選び、サーバーが SQL に変換する。
6. **最初から複数サイトを前提にする。** 全テーブルにサイト ID を持たせる。複数顧客に対応するデータの持ち方（顧客ごとの分け方・権限）は別途設計する。
7. **サイト固有の設定はコードに書かない。** 除外設定とデータ注記はサイトごとの設定として持つ。

## 3. 主な構成

```
[1日1回のバッチ]                  [API サーバー]                          [管理コンソール]
GA4 Data API ─┐                                                          質問
GSC API      ─┼→ そのまま取得 → Postgres ← SQL（除外を適用）← 問い合わせ指定 ← Gemini ←
Bing API     ─┘                 (日次テーブル)  → 結果 → グラフ・表 + AI の解説
```

| 構成要素 | 役割 | 詳細 |
|---|---|---|
| バッチ | 各 API から日次データを取得し、Postgres に上書き保存する | [data_sources.md](data_sources.md) |
| Postgres | 日次テーブル、サイト設定、取得ログ、保存したダッシュボード、会話履歴 | [database_design.md](database_design.md) |
| API サーバー | 問い合わせ指定の検証と SQL 変換（除外の適用を含む）、Gemini の呼び出し | [api_design.md](api_design.md)・[ai_query_design.md](ai_query_design.md) |
| 管理コンソール | チャット、結果カード（グラフ・表）、ダッシュボード、サイト設定 | §4 |

技術構成（案。LeadHub と揃える）: Python（uv、FastAPI、SQLAlchemy + Alembic）、Next.js、PostgreSQL、Gemini（google-genai Python SDK、Vertex AI 経由。logishift と同じ）。詳細は技術構成のファイルで決める（§7）。

## 4. 主な機能（管理コンソール）

- **チャット**: 質問すると、回答として結果カードと AI の解説が出る。結果カードには、グラフ・表、条件（実際に集計した期間を含む）、適用した除外、データ注記が入る。
- **除外の切り替え**: 結果カードごとに、除外設定のオン/オフを切り替えられる。
- **ピン留め**: 結果カードの「ピン留め」で、問い合わせ指定と除外の状態を保存する。
- **ダッシュボード**: ピン留めしたカードを並べる。開くたびに DB から集計し直す（「今月」などの相対期間はその日（日本時間）基準で解釈）。外部 API は呼ばない。
- **サイト設定**: 除外設定（既定のオン/オフ）とデータ注記を編集する。
- **サイト切り替え**: 複数サイトになったら追加する。
- **ログイン**: 最初は自分だけが使う前提で簡易な方式にする（§8）。

## 5. セキュリティ

UTM・参照元・キャンペーン名・検索クエリ・ページパスなどは、誰でも任意の文字列を入れられる（URL に `?utm_campaign=...` を付けて訪問するだけで GA4 に入る）。外部から来た値として扱う。

- **画面**: 取り込んだ値と AI の解説は、必ずエスケープして表示する。グラフの凡例・ツールチップでも HTML として描画しない。
- **AI への受け渡し**: 関数の結果に含まれる文字列はデータであり指示ではない、とシステムプロンプトで明示する。AI が使えるのは集計の関数だけで、サイト ID はサーバーが付けるため、指示文を混ぜられても他サイトのデータには届かない。
- **AI の解説の表示**: Markdown を描画する場合、画像と外部へのリンクは描画しない。外部 URL の画像を読み込ませて情報を送らせる手口を防ぐため。
- **SQL**: 問い合わせ指定から組み立てる SQL はパラメータ付きにする。
- **認証情報**: データ接続の認証情報は暗号化して保存し、鍵は DB と別の場所に置く。

## 6. 範囲と進め方

### 6.1 範囲

| 区分 | 内容 |
|---|---|
| 最初にやる | LogiShift の GA4・GSC・Bing の日次取得、Postgres への保存、AI による質問応答、ダッシュボード |
| 後でやる | TechShift・ConShift の追加、外販（下の表） |
| やらない（今回） | GA4 のイベント単位の生データ（BigQuery）、実売上システム（Shopify 等）との連携 |

### 6.2 外販に向けて

| 区分 | 内容 |
|---|---|
| 最初から入れる | 全テーブルのサイト ID、接続設定の分離、除外設定・データ注記のサイト設定化、質問ごとのトークン記録 |
| 後でやる | 複数顧客に対応するデータの持ち方（顧客ごとの分け方・権限）を別途設計する |
| 後でやる | Google ログイン（`analytics.readonly`、`webmasters.readonly`）と Google の審査（審査前は利用者100人まで）、サインアップ・課金・権限管理 |
| 後でやる | 接続時の自動チェック（EC 指標が入っているか、除外設定の提案） |
| 後でやる | `(other)` が出始めたサイトでは、ランディングページを持たない表に切り替える。顧客が増えたら表を月ごとに分割する |
| 後でやる（選択肢） | BigQuery 接続（購入までの経路・リピート購入の分析が必要な顧客向け）、実売上システムとの連携 |

### 6.3 進め方

1. **DB と Bing・GSC のバッチを作り、過去分を取り込む。** Bing は遡れず、GSC は16ヶ月で消えるため最初にやる。
2. **GA4 のバッチを作り、過去分を取り込む。**
3. **問い合わせ指定から SQL への変換（サーバー）と、評価用の質問セットを作る。**
4. **管理コンソールを作る。** 結果カード、チャット、ダッシュボード、サイト設定。
5. **TechShift・ConShift を追加する。** 2つめのサイトでサイト間の分離を確かめる。
6. **外販の準備をする**（§6.2 の「後でやる」）。

## 7. ドキュメント一覧

| ファイル | 内容 | 状態 |
|---|---|---|
| overview.md | 企画・システム概要（このファイル） | 初版 |
| [data_sources.md](data_sources.md) | データ取得（GA4・GSC・Bing のバッチ） | 初版 |
| [database_design.md](database_design.md) | DB 設計（テーブル、集計のルール、値のそろえ方） | 初版 |
| [api_design.md](api_design.md) | 集計 API（問い合わせ指定、SQL への変換、表示のルール、除外設定） | 初版 |
| [ai_query_design.md](ai_query_design.md) | 生成 AI による問い合わせ（目的、ユースケース、期待値、プロンプト、評価） | 初版 |
| infrastructure_design.md | インフラ構成（ホスティング、バッチの実行環境） | 未作成 |
| technical_design.md | 技術構成（バックエンド・フロントエンドの構成） | 未作成 |
| design_guideline.md | デザインガイドライン（画面の見た目、グラフの描き方） | 未作成 |

## 8. 未決事項

- 外販のターゲットと、その確かめ方（§1.2）
- ホスティング先（DB 容量が数GB規模になりうる点を条件に入れる）
- Gemini のモデルと接続先（どの GCP プロジェクト・認証方式で呼ぶか）
- グラフのライブラリ
- ログイン方式
- 外販するときの製品名。外販の前に、商標（J-PlatPat）も含めて調べて決める。「glance」は同じ分野に同名・似た名前の製品が多い（Glancely、Glancelytics、オープンソースの Glance ダッシュボードなど）

---

## 出典（§1.4）

- [GA4 Analytics Advisor: AI-Powered Analysis in Google Analytics 4（AnalyticaHouse）](https://analyticahouse.com/blogs/ga4-analytics-advisor-ai-powered-analysis-google-analytics-4)
- [Introducing Analytics Advisor in Google Analytics（Cardinal Path）](https://www.cardinalpath.com/blog/introducing-analytics-advisor-in-google-analytics-platform-expertise-at-your-fingertips)
- [Streamline your Search Console analysis with the new AI-powered configuration（Google Search Central Blog、2025-12）](https://developers.google.com/search/blog/2025/12/ai-powered-configuration)
- [Data Studio release notes（Google Cloud）](https://docs.cloud.google.com/data-studio/release-notes)
- [Conversational Analytics in Looker Studio（Google Cloud）](https://cloud.google.com/looker/docs/studio/conversational-analytics-looker-studio)
- [GA4 Chat Analyst を正式リリース（Web担当者Forum / PR TIMES）](https://webtan.impress.co.jp/r/prtimes/items/000000007.000024814)
- [エクスチュア「SEMAIA」発表（2026-06-01）](https://aeo.washinmura.jp/ai/%E3%82%A8%E3%82%AF%E3%82%B9%E3%83%81%E3%83%A5%E3%82%A2%E6%A0%AA%E5%BC%8F%E4%BC%9A%E7%A4%BE/en/news/2026-06-01-%E3%82%A8%E3%82%AF%E3%82%B9%E3%83%81%E3%83%A5%E3%82%A2%E6%A0%AA%E5%BC%8F%E4%BC%9A%E7%A4%BE-ai%E3%81%A7%E8%87%AA%E7%84%B6%E8%A8%80%E8%AA%9E%E5%88%86%E6%9E%90%E3%81%A7%E3%81%8D%E3%82%8B%E3%83%9E%E3%83%8D%E3%83%BC%E3%82%B8%E3%83%89%E3%82%B5%E3%83%BC%E3%83%93%E3%82%B9-semaia)
- [Connect Google Analytics 4 to Gemini Enterprise（Supermetrics）](https://supermetrics.com/connect/ga4-to-gemini-enterprise)
