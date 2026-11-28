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
│   FastAPI（127.0.0.1:8101）                    │  ← API と、画面（Next.js で書き出した静的ファイル）。DB に繋ぐのはここだけ
│   PostgreSQL（Glance 用のコンテナ。LeadHub の   │
│              DB のコンテナとは別。Docker は共有）  │
│   日次バッチ（2番目の段階から）                   │
└──┬──────────────────────────────────────────┘
   │ 外向きの呼び出し
   ▼
GA4 Data API（日次・リアルタイム）、Search Console API、Bing Webmaster API、Gemini（Vertex AI）
```

- 常駐するのは FastAPI だけ。画面は静的ファイルにして FastAPI から出す（[technical_design.md](technical_design.md) §1）。ポートは LeadHub（3000・8001）と重ならない 8101 にし、127.0.0.1 だけで受けて、外には Tunnel を通してだけ出す。
- 動かし方（Linux ユーザー、置き場所、systemd、反映の手順）は [technical_design.md](technical_design.md) §8・§10。
- 段階ごとに置くもの:
  - 1番目（リアルタイム画面）: 画面、API、DB（顧客・利用者・セッション・サイト・接続設定だけ）
  - 2番目から: 日次バッチと、貯めた分析データ（[overview.md](overview.md) §6.3）

## 2. VPS に同居させる理由

Glance の DB は数GB 規模になる（[database_design.md](database_design.md) §8）。日次バッチと初回の取り込み（GA4 の全期間、GSC の16ヶ月分）は時間がかかる。VPS ならどちらも、追加の費用なしで置ける。

**見送った案**

| 案 | 見送った理由 |
|---|---|
| Vercel（画面・API） | 使用量の上限は、管理画面だけなら問題になりにくい（LeadHub が上限を超えた原因は、公開ページの ISR の書き込みと検索エンジンの巡回）。ただし Vercel には DB がない。外部の DB を使うと、数GB では無料枠（Supabase は 500MB）を超える。関数には実行時間の上限があるので、バッチは別の場所に要る。Hobby（無料）は商用利用不可で、外販するなら Pro（月 $20）が要る |
| 画面だけ Vercel、API・DB・バッチは VPS | 画面は静的ファイルにして FastAPI から出すので、分けても VPS で浮くものがない。分けると、API を別のオリジンに出すための設定（CORS・クッキー）が増える |

## 3. 資源

| 項目 | 見込み |
|---|---|
| メモリ | VPS は 4GB ＋ スワップ 2GB。LeadHub が普段 0.7GB 前後、同じ VPS の GitHub Actions のランナーが上限 2.5GB（LeadHub のインフラ設計書・VPS への移行計画）。Glance で常駐するのは API（約0.15GB。LeadHub の API の実測 117MB に、Google のライブラリの分を足した）と DB のコンテナ（約0.2GB の見込み）で、合計は約3.6GB |
| メモリを抑える工夫 | 画面は静的ファイルにし、Node.js を常駐させない。画面のビルドは手元で行う（VPS でビルドしない）。DB はもともと LeadHub の PostgreSQL のコンテナに入れてコンテナを増やさない案だったが、LeadHub と DB の上で分けるため、Glance 用のコンテナを別に立てる（2026-11-28 利用者の決定。§6） |
| 足りなくなったら | 8GB のプラン（月3,784円）に上げる |
| ディスク | 50GB のうち LeadHub が使うのは 10GB 前後。Glance の DB は GSC を中心に数GB 規模 |

## 4. ドメインと Cloudflare

作業は利用者が行う。

- `crosia.jp` を Cloudflare に追加する。アカウントは LeadHub とは分ける。
- ネームサーバーを Cloudflare に切り替えると、crosia.jp のドメイン全体の DNS が Cloudflare に移る。切り替える前に、今使っている DNS レコード（メールの MX など）が Cloudflare 側にそろっているか確かめる。
- Glance 用の Tunnel を作り、`glance.crosia.jp` を VPS の Glance の画面へ向ける。Tunnel は Cloudflare のアカウントごとに作るので、LeadHub の Tunnel とは別に、VPS で cloudflared をもう1つ動かす。
- 入口は絞らない（Cloudflare Access などは使わない。2026-11-28 利用者の決定）。誰でもログイン画面とデモを開ける。中に入れるのは許可リストの人だけ（§5）。分かっている影響は次の2つで、承知のうえで絞らない。
  - 知らない人が Google の同意画面を進めると、Glance が断っても、審査前のアプリの「利用者100人」の枠を使う可能性が高い。
  - デモ（ダミーの数字）は誰でも何度でも呼べる。長い期間でサーバーを止める穴は塞いである（[technical_design.md](technical_design.md) §6.3 の期間の上限）。

## 5. ログイン（Google アカウント）

- **ログイン**: Google アカウントでログインする（OAuth）。ログインできるのは、許可したメールアドレスだけ。許可するアドレスは `/etc/glance/` の env に書き、git には書かない。データはアカウントごとに分かれ、ほかの人のサイト・数字は見えない（2026-11-28 利用者の決定。[technical_design.md](technical_design.md) §4）。
- **許可の範囲**: ログインのときに、GA4 と Search Console の読み取りの許可（`analytics.readonly`・`webmasters.readonly`）ももらう。Search Console を使うのは2番目の段階からだが、そのときに許可を取り直さずに済むよう、最初から両方もらう。
- **トークン**: もらった更新トークンは暗号化して利用者（`users`）に入れ、接続設定（`connections`）からその利用者を指す。日次バッチとリアルタイムは、このトークンで API を呼ぶ。サービスアカウントは使わない。
- **サイトへの紐づけ**
  - GA4: GA4 Admin API の `accountSummaries.list` で、ログインしたアカウントが見られるプロパティの一覧を取る。画面で選んでサイトに紐づける。
  - Search Console: 見られるサイトの一覧から選んで紐づける。
  - 5サイトの GA4 プロパティは、ログインする1つのアカウントからすべて見える（2026-11-26、利用者に確認）。
- **OAuth 同意画面**
  - 公開ステータスは「本番」にする。「テスト」のままだと、Gmail アカウントの更新トークンが7日で切れ、毎週ログインし直すことになる。
  - Google の審査は外販の前まで受けない。それまでは「確認されていないアプリ」という警告が出るが、自分で使う分には先に進める。審査前は利用者100人まで。
- **GCP プロジェクト**: OAuth クライアントは、LogiShift とは別の GCP プロジェクトに作った（2026-11-26 利用者が設定済み。最初は LogiShift のプロジェクトの予定だったが変えた）。プロジェクトの ID は git に書かない。
  - 同意画面は、手元で試す間は「テスト」で、自分をテストユーザーに入れている。VPS に出すときに「本番」に切り替え、本番のリダイレクト URI を足す。
  - 外販の前に、Google の審査をこのプロジェクトで受ける。
  - 使う API（Google Analytics Data API・Google Analytics Admin API）を有効にした。Search Console API は2番目の段階で有効にする。
- 実装の手順（ログインの流れ、セッション、トークンの暗号化）は [technical_design.md](technical_design.md) §4・§5。

## 6. 秘密の置き場所

**懸念**: Glance は、5サイトの GA4・Search Console を読める更新トークンを持つ。公開サイトの LeadHub と同じサーバーなので、LeadHub が破られるとトークンに届きうる。

**守り方**

- Glance は、LeadHub と別の Linux ユーザーで動かす。
- DB は Glance 用の PostgreSQL のコンテナを別に立てる（2026-11-28 利用者の決定）。LeadHub の API は、LeadHub の DB のコンテナの管理者の DB ユーザーでつなぐので、同じ DB のサーバーに入れると、LeadHub が乗っ取られたときに Glance のデータも読み書きされる。コンテナを分ければ、DB の上では届かない。止める・版を上げるのも別々にできる。Docker そのものは共有する（Docker を操作できるのは root だけで、分けても守りは強くならない）。
- 次のものは `/etc/glance/glance.env`（root・600）に置き、git には書かない。手元の保管はパスワード管理。一覧は [technical_design.md](technical_design.md) §9。
  - トークンを暗号化する鍵
  - OAuth クライアントの秘密
  - 許可するメールアドレス
- Google の更新トークンと Bing の API キーは、暗号化して DB に入れる。暗号化の鍵は DB と別の場所（上の env）に置く（[overview.md](overview.md) §5）。

自分だけで使う間はこれで足りる。LeadHub のサーバーの root まで取られる場合は、コンテナを分けていても届く。外販で顧客のトークンを預かる前に、サーバーを分けるかを決め直す（[overview.md](overview.md) §6.2）。

## 7. バックアップ

**取らない（2026-11-28 利用者の決定）。**

- DB が消えたときに取り直せないのは、Bing の日次・ページ別のデータ（API が返すのは日次が約98日・ページ別が13週）と、16ヶ月を過ぎた GSC のデータ。それ以外（サイト・連携の設定、直近の数字）は、設定し直して取り込み直せば戻る。
- 失うのはこの古い分だけと承知のうえで、バックアップの仕組みは作らない。

## 8. 未決事項

- なし（バックアップは取らないことにした（§7）。日次バッチは systemd のタイマーで動かす（[technical_design.md](technical_design.md) §8））
