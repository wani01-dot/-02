# 外部スケジューラーの設定（iPhone）

## 採用案

第一候補は **cron-job.org の無料HTTPジョブ**。1分単位のスケジュールと、カスタムヘッダー・POST・JSON本文をサポートすることを公式リポジトリのソースと文書で確認した。5分ごとなら288回/日。設定管理用REST APIの通常100リクエスト/日という上限は、作成済みHTTPジョブがGitHubへ発行するリクエスト数の上限とは別。ホスト側の実行や無料アカウントの画面はこの環境から未検証。起動の定時性を保証するものではない。[実行エンジン](https://github.com/pschlan/cron-job.org#chronos) · [公式HTTPジョブ仕様](https://github.com/pschlan/cron-job.org/blob/master/docs/source/rest-api.rst) · [サービスFAQ](https://cron-job.org/en/faq/)

Cloudflare Workers Cronは予備候補。公式資料上の無料枠は1アカウント5トリガー、10 ms CPU/回、100,000リクエスト/日。GitHubトークンをWorker Secretに保存できる一方、Workerの作成・更新が必要で、5分の実行間隔を保証する比較実測はない。セットアップの少なさからcron-job.orgを先に試し、アカウント内のカスタムヘッダーにトークンを置く運用が認められない場合はCloudflare Workersを選ぶ。どちらも今回は接続・登録していない。[Cloudflare Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/) · [Workers無料枠](https://developers.cloudflare.com/workers/platform/limits/)

## Safariからの設定

**本番で外部起動を有効にする手順は、この機能が `main` に入ってから行う。** 変更ブランチを検証する場合は、下記の疎通専用本文にそのブランチ名を指定する。本番同期ジョブは `main` に限定され、疎通専用ジョブはLINEの資格情報、チェックアウト、書き込み権限を使わない。

1. GitHubで自分のアカウント設定を開き、**Developer settings → Personal access tokens → Fine-grained tokens → Generate new token** を選ぶ。表示しにくい場合はSafariの「デスクトップ用Webサイトを表示」を使う。
2. 期限を短く設定し、Resource ownerはリポジトリの所有者、Repository accessは **Only select repositories → `wani01-dot/-02` のみ**。Repository permissionsは **Actions: Read and write**。自動付与されるMetadataの読み取り以外の権限は足さない。GitHubのこの権限はリポジトリ単位で、`sync.yml` 1ファイルに限定できない。組織承認が出る場合は承認されるまで設定を止める。[GitHubのトークン設定](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token) · [dispatch APIの必要権限](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
3. cron-job.orgのダッシュボードで新しいジョブを作る。タイトルは任意。URLは `https://api.github.com/repos/wani01-dot/-02/actions/workflows/sync.yml/dispatches`。タイムゾーンは **Asia/Tokyo**、間隔は **Every 5 minutes**。カスタム指定の場合は毎時の分を 00、05、10、15、20、25、30、35、40、45、50、55 に設定する。
4. Advancedのメソッドを **POST** にし、以下のHTTPヘッダーを設定する。トークンはGitHub発行画面から直接貼り付け、URL、JSON本文、リポジトリ、スクリーンショット、チャットには入れない。HTTPレスポンス本文の保存はオフ、失敗通知はオンにする。

   | 名前 | 値 |
   | --- | --- |
   | Authorization | `Bearer <発行したfine-grainedトークン>` |
   | Accept | `application/vnd.github+json` |
   | Content-Type | `application/json` |
   | X-GitHub-Api-Version | `2022-11-28` |

5. 初回は本文に以下を使う。定期実行はまだ無効にし、テスト実行または一回の起動で確認する。GitHub Actionsに **外部スケジューラーの疎通確認** が表示されれば成功。HTTP 2xxだけでは同期の成功を意味しない。401の場合はトークン、403/404の場合は権限・対象リポジトリ・承認、422の場合はrefと入力名を確認する。GitHubが既定ブランチに未登録の入力を拒否した場合は、変更ブランチの外部疎通は未確認のままにする。旧定義を実行する本文に切り替えない。

   ```json
   {"ref":"codex/notification-observability","inputs":{"external_scheduler":true,"scheduler_dry_run":true}}
   ```

6. 本番反映の承認・マージ後に限り、本文を次の形に変更し、ジョブを有効にする。

   ```json
   {"ref":"main","inputs":{"external_scheduler":true}}
   ```

7. Safariで [同期のActions一覧](https://github.com/wani01-dot/-02/actions/workflows/sync.yml) を開く。Summaryの起動元、5分枠、取得タイミング、LINE月間利用量で確認する。トークン失効前に同じ最小権限で更新し、不要になった旧トークンを失効する。漏洩が疑われる場合はGitHubで直ちに失効し、cron-job.orgのジョブを停止する。

## 停止時の補完と重複防止

外部は毎時00・05分など、GitHubは04・09分などに1回起動を試みる。1つの同期枠はUTCの5分バケット。Actionsの実行作成時刻を基準にし、取得できない場合はジョブ冒頭の時刻を使う。最初に枠を取得したランだけが、外部サイトの取得、LINE API利用量の照会、通知に進む。枠の保存には既存通知状態ブランチへのfast-forward保存を使い、競合で保存できないランは取得前に停止する。旧来の排他グループとLINEリトライキーも維持する。重なった試行はActions一覧に現れるが、同じ枠の取得・LINE送信と、その試行からのPages公開はスキップされる。

外部ジョブが停止・失効して次の枠が未処理であれば、その枠のGitHub起動が補完する。GitHubが起動しなかった枠は補完できない。枠を獲得したランが途中で停止した場合、その枠では再取得せず、次の枠へ進む。長い起動遅延や枠の境界では実際の取得間隔が5分と異なり得る。初週は外部のHTTP実行履歴とGitHub Summaryを並べ、5分・10分以内の割合と最長の空白を比較する。

## FANY

FANYチケットのrobots.txtは引き続き403。公式案内・マガジンの本文はこのクラウドの接続制約により確認できず、FANY全体で利用を許可されたAPI・配布は確認できていない。公式劇場サイトのスケジュール、興行主が利用を許可した公開日程は個別の代替候補。劇場データの対象外となるFANY公演まで網羅できる根拠はなく、アクセス制限を回避する方式は採らない。
