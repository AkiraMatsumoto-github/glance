# glance インフラ設計

作成日: 2026-11-26
状態: 初版（実装前）。

ホスティング、ドメイン、ログイン、秘密の置き場所、バックアップの設計。全体像は [overview.md](overview.md)、データの取り方は [data_sources.md](data_sources.md)。

---

## 1. 構成

**LeadHub と同じ XServer VPS（クラウド 4GB・50GB）に同居させ、前に Cloudflare を置く。** URL は `glance.crosia.jp`。

```
利用者（ブラウザ）
   │ HTTPS（glance.crosia.jp）
┌──▼──────────────────────────────────────────┐
│  Cloudflare（crosia.jp。LeadHub とは別のアカウント） │
└──┬──────────────────────────────────────────┘
   │ Cloudflare Tunnel（Glance 用。LeadHub の Tunnel とは別）
┌──▼──────────────────────────────────────────┐
│  XServer VPS（LeadHub と同じサーバー）           │
│   cloudflared（Glance 用）                     │
│   Next.js（管理コンソール・127.0.0.1）           │
│   FastAPI（API サーバー・127.0.0.1）             │  ← DB に繋ぐのはここだけ
│   PostgreSQL（LeadHub の Docker のコンテナに、    │
│              別のデータベースとして入れる）        │
│   日次バッチ（2番目の段階から）                   │
└──┬──────────────────────────────────────────┘
   │ 外向きの呼び出し
   ▼
GA4 Data API（日次・リアルタイム）、Search Console API、Bing Webmaster API、Gemini（Vertex AI）
```

- 画面・API のポートは LeadHub と重ならないものにする。どちらも 127.0.0.1 だけで受け、外には Tunnel を通してだけ出す。
- 段階ごとに置くもの:
  - 1番目（リアルタイム画面）: 画面、API、DB（サイト・接続設定だけ）
  - 2番目から: 日次バッチと、貯めた分析データ（[overview.md](overview.md) §6.3）

## 2. VPS に同居させる理由

Glance の DB は数GB 規模になる（[database_design.md](database_design.md) §8）。日次バッチと初回の取り込み（GA4 の全期間、GSC の16ヶ月分）は時間がかかる。VPS ならどちらも、追加の費用なしで置ける。

**見送った案**

| 案 | 見送った理由 |
|---|---|
| Vercel（画面・API） | 使用量の上限は、管理画面だけなら問題になりにくい（LeadHub が上限を超えた原因は、公開ページの ISR の書き込みと検索エンジンの巡回）。ただし Vercel には DB がない。外部の DB を使うと、数GB では無料枠（Supabase は 500MB）を超える。関数には実行時間の上限があるので、バッチは別の場所に要る。Hobby（無料）は商用利用不可で、外販するなら Pro（月 $20）が要る |
| 画面だけ Vercel、API・DB・バッチは VPS | 浮くのは画面のメモリ（約0.15GB）だけで、API を外部に公開するための認証が増える |

## 3. 資源

| 項目 | 見込み |
|---|---|
| メモリ | VPS は 4GB ＋ スワップ 2GB。LeadHub が普段 0.7GB 前後、同じ VPS の GitHub Actions のランナーが上限 2.5GB（LeadHub のインフラ設計書・VPS への移行計画）。Glance の画面と API が LeadHub と同じくらい（LeadHub の実測は API 117MB・画面 144MB）なら約0.3GB 増え、合計は約3.5GB。ビルドが重なるとスワップを使う程度 |
| メモリを抑える工夫 | DB は LeadHub の PostgreSQL のコンテナに別のデータベースとして入れ、コンテナを増やさない |
| 足りなくなったら | 8GB のプラン（月3,784円）に上げる |
| ディスク | 50GB のうち LeadHub が使うのは 10GB 前後。Glance の DB は GSC を中心に数GB 規模 |

## 4. ドメインと Cloudflare

作業は利用者が行う。

- `crosia.jp` を Cloudflare に追加する。アカウントは LeadHub とは分ける。
- ネームサーバーを Cloudflare に切り替えると、crosia.jp のドメイン全体の DNS が Cloudflare に移る。切り替える前に、今使っている DNS レコード（メールの MX など）が Cloudflare 側にそろっているか確かめる。
- Glance 用の Tunnel を作り、`glance.crosia.jp` を VPS の Glance の画面へ向ける。Tunnel は Cloudflare のアカウントごとに作るので、LeadHub の Tunnel とは別に、VPS で cloudflared をもう1つ動かす。

## 5. ログイン（Google アカウント）

- **ログイン**: Google アカウントでログインする（OAuth）。ログインできるのは、許可したメールアドレスだけ。許可するアドレスは `/etc/glance/` の env に書き、git には書かない。
- **許可の範囲**: ログインのときに、GA4 と Search Console の読み取りの許可（`analytics.readonly`・`webmasters.readonly`）ももらう。Search Console を使うのは2番目の段階からだが、そのときに許可を取り直さずに済むよう、最初から両方もらう。
- **トークン**: もらった更新トークンは暗号化して接続設定（`connections`）に入れる。日次バッチとリアルタイムは、このトークンで API を呼ぶ。サービスアカウントは使わない。
- **サイトへの紐づけ**
  - GA4: GA4 Admin API の `accountSummaries.list` で、ログインしたアカウントが見られるプロパティの一覧を取る。画面で選んでサイトに紐づける。
  - Search Console: 見られるサイトの一覧から選んで紐づける。
  - 5サイトの GA4 プロパティは、ログインする1つのアカウントからすべて見える（2026-11-26、利用者に確認）。
- **OAuth 同意画面**
  - 公開ステータスは「本番」にする。「テスト」のままだと、Gmail アカウントの更新トークンが7日で切れ、毎週ログインし直すことになる。
  - Google の審査は外販の前まで受けない。それまでは「確認されていないアプリ」という警告が出るが、自分で使う分には先に進める。審査前は利用者100人まで。
- OAuth クライアントを置く GCP プロジェクトは未決（§8）。

## 6. 秘密の置き場所

**懸念**: Glance は、5サイトの GA4・Search Console を読める更新トークンを持つ。公開サイトの LeadHub と同じサーバーなので、LeadHub が破られるとトークンに届きうる。

**守り方**

- Glance は、LeadHub と別の Linux ユーザーで動かす。
- DB は別のデータベース・別の DB ユーザーにし、互いの DB に入れないようにする。
- 次のものは `/etc/glance/*.env`（root・600）に置き、git には書かない。手元の保管はパスワード管理。
  - トークンを暗号化する鍵
  - OAuth クライアントの秘密
  - 許可するメールアドレス
  - Bing の API キー
- 暗号化の鍵は DB と別の場所に置く（[overview.md](overview.md) §5）。

自分だけで使う間はこれで足りる。外販で顧客のトークンを預かる前に、サーバーを分けるかを決め直す（[overview.md](overview.md) §6.2）。

## 7. バックアップ

- **1番目の段階（リアルタイム画面）**: 分析データを貯めないので、DB にはサイトと接続設定しかない。消えても、設定し直してログインし直せば戻る。
- **2番目の段階（Bing・GSC のバッチ）から**: DB が、取り直せないデータの唯一の置き場所になる。取り直せないのは、Bing の日次・ページ別のデータと、16ヶ月を過ぎた GSC のデータ。ここから、1日1回 Glance のデータベースを `pg_dump` して VPS の外に置く。
- LeadHub の本番 DB は手元から送った写しで、バックアップに頼っていない。同じコンテナに入れても、Glance のバックアップは Glance のデータベースだけを対象に、LeadHub とは別に取る。

## 8. 未決事項

- バックアップの置き場所（2番目の段階までに決める）
- OAuth クライアントを置く GCP プロジェクト（Gemini の接続先と合わせて決める。[overview.md](overview.md) §8）
- 反映（デプロイ）の手順、日次バッチの動かし方（技術構成のファイルで決める）
