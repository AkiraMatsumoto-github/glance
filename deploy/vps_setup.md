# Glance を VPS に置く手順

作成日: 2026-11-28

LeadHub と同じ VPS に Glance を置き、`glance.crosia.jp` で出すまでの手順。設計は [インフラ設計書](../docs/01_design/infrastructure_design.md)・[技術設計書](../docs/01_design/technical_design.md) §8〜§10、開発計画は [roadmap.md](../docs/01_design/roadmap.md) §3.7。

**コマンドはすべて人が実行する**（Claude は本番のサーバーに触らない）。`<サーバー名>`（SSH の接続名）などの `<…>` は自分の値に置き換える。
パスワード・鍵・トークンは、この手順のとおりに VPS の上で作るか、パスワード管理から貼る。**会話やチャットには貼らない。**

| 節 | 中身 | どこで |
|---|---|---|
| §0 | 前提 | — |
| §1〜3 | ユーザーと置き場所・DB（Glance 用のコンテナ）・環境変数 | 手元・VPS |
| §4 | 手元の DB を写す | 手元・VPS |
| §5 | サービスを入れる | 手元・VPS |
| §6 | 最初のデプロイと、鍵の入れ替え | 手元・VPS |
| §7 | Cloudflare（crosia.jp と Tunnel） | Cloudflare・レジストラ・VPS |
| §8 | Google の設定 | GCP |
| §9 | 毎日の取り込みを始める | VPS |
| §10 | 確かめる | ブラウザ・手元 |
| §11 | ふだんの運用 | 手元・VPS |
| §12 | 戻し方 | VPS |
| §13 | DB のコンテナの運用（止める・版を上げる） | VPS |

---

## 0. 前提

- LeadHub の VPS の開設手順（LeadHub の `deploy/vps_setup.md` §3〜§7）が済み、LeadHub が動いていること。
  **Glance のために新しく入れるソフトは無い。** LeadHub のときに入れたものを、次のように使い回す:
  - **Docker**: Glance 用の PostgreSQL のコンテナ `glance-db` を、LeadHub の DB のコンテナ（`leadhub-db`）とは別に動かす（§2）。
    Docker そのものは共有する。LeadHub の DB の設定にも中身にも触らない
  - **uv**: Glance の Python の環境を作る（Python 3.14 も、最初のデプロイで uv が入れる）
  - **cloudflared**: プログラムは同じものを使い、Glance 用の Tunnel としてもう1つ動かす（Cloudflare のアカウントが LeadHub と別のため。§7）
- **Node.js は VPS では使わない**（画面は手元でビルドして送る）。
- 手元の `.env` に、Glance の本番用ではない値（手元の DB・`http://localhost:3100` など）が入っていること。本番の値は §3 で VPS の上に作る。

| もの | 置き場所 | 持ち主・権限 |
|---|---|---|
| 環境変数（DB のパスワード・鍵・OAuth の秘密・許可リスト） | `/etc/glance/glance.env` | root・600（systemd が root で読んでから渡す） |
| DB のコンテナのパスワード | `/etc/glance/db.env` | root・600 |
| Tunnel のトークン | `/etc/glance/cloudflared.env` | root・600 |
| DB（PostgreSQL 16） | `/srv/glance/db/compose.yml` とボリューム `glance_db_data`。コンテナ `glance-db`、127.0.0.1:5434 | root |
| リリース | `/srv/glance/releases/<日時>-<コミット>/` | glance |
| 動いているリリース | `/srv/glance/current`（リリースへのリンク） | glance |
| サービス | `glance-api`（API と画面。127.0.0.1:8101）・`glance-cloudflared`（Tunnel）・`glance-sync.timer`（毎日の取り込み） | — |

---

## 1. ユーザーと置き場所

```bash
# VPS（ops）
sudo useradd --system --create-home --home-dir /srv/glance --shell /usr/sbin/nologin glance
sudo chmod 750 /srv/glance          # ほかのユーザー（leadhub・gha-runner）から読めないようにする
sudo install -d -m 700 /etc/glance
```

---

## 2. DB（Glance 用の PostgreSQL のコンテナ）

LeadHub の DB のコンテナとは別に、Glance 用のコンテナを動かす（2026-11-28 利用者の決定。LeadHub が乗っ取られても、DB の上では Glance に届かない。
止める・版を上げるのも別々にできる）。設定は `deploy/compose.yml`（手元の `docker-compose.yml` と同じイメージ）。

```bash
# 手元（glance のリポジトリの根）
scp deploy/compose.yml <サーバー名>:/tmp/glance-compose.yml
```

パスワードは英数字だけにする（URL の中で崩れないように）。

```bash
# VPS（ops）
GLANCE_DB_PW=$(openssl rand -hex 24)
echo "POSTGRES_PASSWORD=$GLANCE_DB_PW" | sudo tee /etc/glance/db.env >/dev/null
sudo chmod 600 /etc/glance/db.env
echo "Glance の DB のパスワード: $GLANCE_DB_PW"   # パスワード管理に保存する。§3 でも使うので、まだ unset しない

sudo install -D -m 644 /tmp/glance-compose.yml /srv/glance/db/compose.yml
rm /tmp/glance-compose.yml
sudo docker compose -f /srv/glance/db/compose.yml up -d
sleep 15   # 最初の起動は初期化してから立ち上げ直すので、少し待つ
sudo docker compose -f /srv/glance/db/compose.yml ps
```

> ⚠️ `compose.yml` の先頭の `name: glance` を消さない。LeadHub の compose は名前が「db」（置き場所のフォルダ名）で、Glance も「db」になると、
> 同じサービス名の LeadHub の DB のコンテナを、Glance の設定で作り直してしまう。

確かめる:

```bash
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'leadhub-db|glance-db'   # 2つとも Up（LeadHub の DB はそのまま）
sudo ss -ltnp | grep -E ':5432|:5434'     # どちらも 127.0.0.1 だけで受けている
sudo docker exec glance-db psql -U glance -d glance -Atc "SELECT current_user, version()"
```

---

## 3. 環境変数

暗号化の鍵（Fernet）はここで新しく作る。§4 で写す手元の DB の値は**手元の鍵**で暗号化してあるので、最初は「新しい鍵,手元の鍵」と並べ、
§6 で新しい鍵で暗号化し直してから、手元の鍵を外す（[技術設計書](../docs/01_design/technical_design.md) §5 の鍵の入れ替えと同じ）。

```bash
# VPS（ops）。§2 の GLANCE_DB_PW が入っているシェルで続けて打つ
TOKEN_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
sudo tee /etc/glance/glance.env >/dev/null <<EOF
GLANCE_DATABASE_URL=postgresql+psycopg://glance:$GLANCE_DB_PW@127.0.0.1:5434/glance
GLANCE_TOKEN_KEY=$TOKEN_KEY,<手元の GLANCE_TOKEN_KEY>
GLANCE_PUBLIC_URL=https://glance.crosia.jp
GLANCE_GOOGLE_CLIENT_ID=
GLANCE_GOOGLE_CLIENT_SECRET=
GLANCE_ALLOWED_EMAILS=
EOF
sudo chmod 600 /etc/glance/glance.env
echo "Glance の新しい暗号化の鍵: $TOKEN_KEY"   # パスワード管理に保存する
unset GLANCE_DB_PW TOKEN_KEY
```

残りを手で入れる（`sudoedit` は、root のファイルを自分のエディタで開く）:

```bash
sudoedit /etc/glance/glance.env
```

- `<手元の GLANCE_TOKEN_KEY>`: 手元の `.env` の `GLANCE_TOKEN_KEY` の値に置き換える
- `GLANCE_GOOGLE_CLIENT_ID`・`GLANCE_GOOGLE_CLIENT_SECRET`: 手元と同じ OAuth クライアントの値（パスワード管理か GCP の画面から）
- `GLANCE_ALLOWED_EMAILS`: ログインを許すメールアドレス（カンマ区切り）

各行の意味は `deploy/glance.env.example`。

---

## 4. 手元の DB を写す

手元で貯めた Search Console・Bing の数字（Bing の過去分は取り直せない）を、サイト・連携の設定ごと写す。ログインのセッションは写さない。

```bash
# 手元（glance のリポジトリの根）。手元の DB のコンテナ（glance-db）が動いていること
docker exec glance-db pg_dump -U glance -d glance -Fc --no-owner --no-privileges --exclude-table-data=sessions > /tmp/glance.dump
ls -lh /tmp/glance.dump
scp /tmp/glance.dump <サーバー名>:/tmp/glance.dump
rm /tmp/glance.dump
```

```bash
# VPS（ops）。§2 で作った空のデータベースに入れる（手元のコンテナと同じ名前 glance-db だが、こちらは VPS のもの）
sudo docker exec -i glance-db pg_restore -U glance -d glance --no-owner --no-privileges --exit-on-error < /tmp/glance.dump
rm /tmp/glance.dump
sudo docker exec glance-db psql -U glance -d glance -Atc "SELECT version_num FROM alembic_version" \
  -c "SELECT count(*) FROM sites" -c "SELECT count(*) FROM gsc_site" -c "SELECT count(*) FROM bing_site_daily"
```

マイグレーションの版（`0005` など。手元で `uv run alembic current` と同じ）と、サイト数・数字の件数が手元と同じならよい。

> 写した後は、手元で取り込み（`python -m glance.sync`）を動かさなくてよい（§9 から本番が毎日取る）。手元の DB は、そのまま手元の開発に使う。

---

## 5. サービスを入れる

```bash
# 手元（glance のリポジトリの根）
scp deploy/systemd/glance-api.service deploy/systemd/glance-sync.service deploy/systemd/glance-sync.timer \
    deploy/systemd/glance-cloudflared.service <サーバー名>:/tmp/
```

```bash
# VPS（ops）
command -v cloudflared   # /usr/bin/cloudflared でなければ、glance-cloudflared.service の ExecStart をその場所に直す
sudo install -m 644 /tmp/glance-api.service /tmp/glance-sync.service /tmp/glance-sync.timer \
    /tmp/glance-cloudflared.service /etc/systemd/system/
rm /tmp/glance-api.service /tmp/glance-sync.service /tmp/glance-sync.timer /tmp/glance-cloudflared.service
sudo systemctl daemon-reload
sudo systemctl enable glance-api
```

まだ起動しない（リリースが無い）。最初のデプロイ（§6）が起動する。Tunnel は §7、毎日の取り込みは §9 で始める。

---

## 6. 最初のデプロイと、鍵の入れ替え

### 6.1 デプロイ

手元の `.env` に、VPS に入る SSH の接続名を書く（git には入らない）:

```bash
# 手元の .env に1行足す
GLANCE_PROD_SSH=<サーバー名>
```

```bash
# 手元（glance のリポジトリの根）。出すのは GitHub の main にあるコミット（push してから流す）
scripts/deploy_prod.sh
```

- 手元で画面をビルドした後、`glance` と打ち込むと送る。SSH の鍵のパスフレーズと、VPS の sudo のパスワードを1回ずつ聞かれる
- VPS の上の流れは `deploy/release.sh`（展開 → Python の環境 → マイグレーション → 切り替え → 確かめる）。最初の回は Python 3.14 を入れるので少し長い
- 最後に `/login → 200`・`/api/me → 401` と「完了」が出ればよい

### 6.2 コマンドを本番の環境で動かす

本番の環境変数で Glance のコマンドを動かすときは、次の形を使う（glance ユーザーで、`/etc/glance/glance.env` を読んで動く）。
毎回打つのが手間なら、ops のシェルの関数にしておく:

```bash
# VPS（ops）
glance_run() {
  sudo systemd-run --quiet --wait --pipe --uid=glance --gid=glance \
    -p EnvironmentFile=/etc/glance/glance.env -p WorkingDirectory=/srv/glance/current \
    /srv/glance/current/.venv/bin/python "$@"
}
```

### 6.3 鍵の入れ替え（手元の鍵を外す）

```bash
# VPS（ops）
glance_run -m glance.rekey --check   # 「古い鍵のまま」が、写した更新トークン・Bing のキーの数だけ出る
glance_run -m glance.rekey           # 新しい鍵で暗号化し直す
glance_run -m glance.rekey --check   # 「古い鍵のまま 0件」になればよい
```

0件になったら、`sudoedit /etc/glance/glance.env` で `GLANCE_TOKEN_KEY` の「`,<手元の鍵>`」を消し、`sudo systemctl restart glance-api`。

> 「どの鍵でも復号できない」と出たら、何も書き換わっていない。§3 の `<手元の GLANCE_TOKEN_KEY>` を手元の `.env` と見比べる。

### 6.4 VPS の中で見る（公開する前）

Tunnel をつなぐ前でも、SSH のポート転送で手元のブラウザから見られる。デモ（`/demo`）とログイン画面が出ればよい
（Google ログインは、戻り先が `https://glance.crosia.jp` なので §7・§8 の後でないとできない）。

```bash
# 手元。張っている間だけ http://localhost:18101/demo で見える（Ctrl+C で閉じる）
ssh -N -L 18101:127.0.0.1:8101 <サーバー名>
```

---

## 7. Cloudflare（crosia.jp と Tunnel）

アカウントは LeadHub とは分ける（[インフラ設計書](../docs/01_design/infrastructure_design.md) §4）。入口は絞らない（Cloudflare Access は使わない）。

### 7.1 crosia.jp を Cloudflare に入れる

1. Glance 用の Cloudflare のアカウントで「Add a site」→ `crosia.jp` → Free
2. Cloudflare が読み込んだ DNS のレコードを、**今の DNS（レジストラの画面）と1つずつ見比べる**。特にメールの `MX`・`TXT`（SPF・DKIM・DMARC）と、今使っているサブドメイン。足りないものは足す
3. レジストラで、ネームサーバーを Cloudflare が示す2つに変える
4. Cloudflare の画面で crosia.jp が **Active** になるまで待つ（数分〜数時間）。メールが届くことを確かめる

> ⚠️ ネームサーバーを変えると、crosia.jp のドメイン全体の DNS が Cloudflare に移る。2 で抜けたレコードは、切り替えた時点で引けなくなる。

### 7.2 Tunnel を作る

1. Cloudflare の画面 → **Networking → Tunnels** →「Create a tunnel」→ 種類は **Cloudflared**、名前は `glance`
2. インストールのコマンドの画面に出る `eyJ…` の長い文字列（トークン）を控える。**コマンドは打たない**
   （`cloudflared service install` は、LeadHub の Tunnel のサービス `cloudflared.service` を書き換えてしまう）
3. VPS でトークンを置いて、Glance 用のサービスを起動する:

   ```bash
   # VPS（ops）
   sudo install -m 600 /dev/null /etc/glance/cloudflared.env
   sudoedit /etc/glance/cloudflared.env     # TUNNEL_TOKEN=<トークン> の1行を書く（deploy/cloudflared.env.example）
   sudo systemctl enable --now glance-cloudflared
   systemctl is-active glance-cloudflared cloudflared   # どちらも active（LeadHub の Tunnel も止まっていないこと）
   ```

4. Cloudflare の画面で、Tunnel の状態が **Healthy** になればよい

> トークンを持っていれば誰でもこの Tunnel を動かせる。漏れたら Tunnel の画面で作り直す（Refresh token）。

### 7.3 glance.crosia.jp を向ける

Tunnel の画面 → **Routes** の **Add route** → **Published application** →
**Hostname**：サブドメイン `glance`・ドメイン `crosia.jp`、**Service URL**：`http://127.0.0.1:8101` → **Add route**

SSL/TLS の画面で **Always Use HTTPS** をオンにする（http で来た人を https に移す）。キャッシュの設定は既定のままでよい
（HTML はキャッシュされず、JS・CSS はファイル名に中身のハッシュが入る）。

---

## 8. Google の設定

GCP の、Glance の OAuth クライアントのあるプロジェクトで行う（[インフラ設計書](../docs/01_design/infrastructure_design.md) §5）。

1. **OAuth クライアント**: 承認済みのリダイレクト URI に `https://glance.crosia.jp/api/auth/callback` を足す（手元の `http://localhost:3100/api/auth/callback` は残す）
2. **同意画面**: 公開ステータスを「本番」にする（「テスト」のままだと、更新トークンが7日で切れる）。審査は受けないので「確認されていないアプリ」の警告が出るが、先に進める

---

## 9. 毎日の取り込みを始める

```bash
# VPS（ops）
sudo systemctl enable --now glance-sync.timer
systemctl list-timers glance-sync.timer      # 次に動く時刻（毎日 6:00 ごろ。日本時間）

# すぐ1回動かして確かめる（写したデータの続き、直近の数日分なので数分で終わる）
sudo systemctl start glance-sync
journalctl -u glance-sync -n 50 --no-pager   # 表ごとに「OK」が並べばよい
```

> Search Console の取り込みは、サイト設定で Search Console を紐づけた人の更新トークンで動く。§6.3 で鍵を入れ替えた後なら、写した更新トークンがそのまま使える。
> 「紐づけた利用者がいません」「許可リストにいません」などで失敗したら、本番の画面でログインし直し、サイト設定で紐づけ直す。

---

## 10. 確かめる

1. https://glance.crosia.jp/ を開き、「Google でログイン」→ リアルタイム・SEO・サイト設定が、手元と同じサイト・数字で出る
2. ログインせずに https://glance.crosia.jp/demo（デモ）が出る
3. 許可リストにない Google アカウントでは「このアカウントは使えません」になる
4. クッキーとヘッダー（手元）:

   ```bash
   curl -sI https://glance.crosia.jp/login | grep -iE 'x-frame-options|content-security-policy|x-content-type-options'
   ```

   3つとも出ればよい。ブラウザの開発者ツールで、ログイン後のクッキーが `__Host-glance_session`（Secure）になっていることも見る
5. メモリ: `systemctl status glance-api --no-pager | grep Memory`（約0.15GB の見込み。[roadmap.md](../docs/01_design/roadmap.md) §5）

---

## 11. ふだんの運用

| すること | どうやるか |
|---|---|
| 新しいコードを出す | 手元で `scripts/deploy_prod.sh`（main に push してから） |
| ログインできる人を足す・外す | `sudoedit /etc/glance/glance.env` の `GLANCE_ALLOWED_EMAILS` → `sudo systemctl restart glance-api`（取り込みは毎回読むので再起動は要らない） |
| 取り込みの様子を見る | `journalctl -u glance-sync -n 100 --no-pager`、`systemctl status glance-sync` |
| 取り込みを今すぐ動かす | `sudo systemctl start glance-sync` |
| API のログを見る | `journalctl -u glance-api -n 100 --no-pager` |
| 暗号化の鍵を入れ替える | [技術設計書](../docs/01_design/technical_design.md) §5 の手順。コマンドは §6.2 の `glance_run -m glance.rekey` |

> 本番でログの段階を DEBUG にしない。Google の SDK のログを開く環境変数（`GOOGLE_SDK_PYTHON_LOGGING_SCOPE`）も設定しない（[技術設計書](../docs/01_design/technical_design.md) §9）。

---

## 12. 戻し方

| どこで | すること |
|---|---|
| デプロイの途中（展開・Python の環境・マイグレーション）で失敗 | 何も切り替わっていない。前のリリースが動いたまま |
| 切り替えた後に、新しいリリースが答えない | `deploy/release.sh` が前のリリースに自動で戻す |
| 切り替えた後に問題が出た | 下のコマンドで、前のリリースに戻して再起動する（数秒） |

```bash
# VPS（ops）。リリースは新しい順に並ぶ。戻したいもの（ふつうは2行目）を選ぶ
sudo ls -1t /srv/glance/releases
sudo ln -sfn /srv/glance/releases/<戻したいリリース> /srv/glance/current
sudo systemctl restart glance-api
```

> マイグレーション（DB のテーブル定義）は自動では戻さない。戻したリリースが新しいテーブル定義で動かないときは、Claude に相談する。

---

## 13. DB のコンテナの運用

Glance の DB のコンテナは、LeadHub の DB とは別に止めたり上げたりできる。

| すること | コマンド（VPS・ops） |
|---|---|
| 様子を見る | `sudo docker compose -f /srv/glance/db/compose.yml ps`、`sudo docker stats --no-stream glance-db`（メモリ） |
| 再起動する | `sudo docker compose -f /srv/glance/db/compose.yml restart`（API と取り込みは、つなぎ直すまで少しの間エラーになる） |
| PostgreSQL 16 の中の版を上げる（16.x） | `sudo docker compose -f /srv/glance/db/compose.yml pull`、続けて `sudo docker compose -f /srv/glance/db/compose.yml up -d` |

> PostgreSQL の大きな版（16 → 17 など）を上げるときは、データの移し替えが要る。手元の `docker-compose.yml` と一緒に、Claude に相談する。
> バックアップは取らない決まり（[インフラ設計書](../docs/01_design/infrastructure_design.md) §7）なので、ボリューム `glance_db_data` を消さない（`docker compose down -v` は使わない）。
