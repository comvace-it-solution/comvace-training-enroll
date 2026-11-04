# セットアップ手順

研修担当者（org Owner）が一度だけ行う作業です。所要 15 分程度。

以下では org を `comvace-it-solution`、受付リポジトリを
`comvace-it-solution/comvace-training-enroll` として記載します。

---

## 1. 受付リポジトリを作る

この一式を **public** リポジトリとして push します。

```sh
gh repo create comvace-it-solution/comvace-training-enroll \
  --public \
  --description "研修リポジトリの払い出し受付" \
  --source . --push
```

public にするのは、まだ org に参加していない受講者でもフォームを送信できるようにするためです。
払い出される研修リポジトリは常に private なので、課題の中身が公開されることはありません。

> 公開される情報は「どの GitHub アカウントがいつ申請したか」と
> 「払い出されたリポジトリ名」です。これも隠したい場合は後述の
> 「受付リポジトリを private にしたい場合」を参照してください。

## 2. GitHub App を作る

Classroom の代わりに org へリポジトリを作る主体です。
PAT ではなく App を使います。権限を絞れて、退職時の失効管理も不要になるためです。

GitHub App を作成する API は存在しないため、ブラウザでの操作が 1 回必要です。
ただし **App Manifest フロー**を使えば、権限が設定済みの登録画面を開けるので、
フォームを手入力する必要はありません（権限の付け間違いも起きません）。

```sh
python3 scripts/register-app.py \
  comvace-it-solution comvace-it-solution/comvace-training-enroll
```

ブラウザが開くので **「Create GitHub App for comvace-it-solution」** を押すだけです。
App ID と秘密鍵が `/tmp/gh-app-setup/` に保存されます。

> App 名は GitHub 全体で一意です。既に使われている場合は登録画面の名前欄で変更してください。

このスクリプトが設定する権限は以下です（手で作る場合の参照用）。

**Repository permissions**

| 権限           | レベル         | 用途                                             |
| -------------- | -------------- | ------------------------------------------------ |
| Administration | Read and write | 研修リポジトリの作成、受講者の collaborator 追加 |
| Contents       | Read-only      | テンプレートリポジトリの読み取り                 |
| Metadata       | Read-only      | （自動で付与されます）                           |

**Organization permissions**

現在の `courses.json`（`instructorTeam` なし・`inviteToOrg` なし）では **不要** です。
最小権限に保つため、付与しないでください。

| 権限    | レベル         | 必要になる条件                                             |
| ------- | -------------- | ---------------------------------------------------------- |
| Members | Read and write | `instructorTeam` または `inviteToOrg` を有効にしたときのみ |

**Where can this GitHub App be installed?** → `Only on this account`

### App を org にインストールする

作成しただけでは使えません。インストールもブラウザ操作が必要です（API なし）。

```sh
open https://github.com/apps/comvace-training-provisioner/installations/new
```

`comvace-it-solution` を選び、**All repositories** を選んで Install します。

> ここは必ず `All repositories` にしてください。払い出すリポジトリは**まだ存在しない**ため、
> `Only select repositories` では新規リポジトリにトークンが効きません。

インストールされたか確認します。

```sh
gh api orgs/comvace-it-solution/installations \
  --jq '.installations[] | {app_slug, repository_selection, permissions}'
```

`repository_selection` が `all` になっていれば正しい状態です。

## 3. 認証情報を受付リポジトリに登録する

```sh
REPO=comvace-it-solution/comvace-training-enroll

# App ID は秘密情報ではないので variable で十分
gh variable set PROVISIONER_APP_ID --repo "$REPO" --body '123456'

# 秘密鍵は secret として登録し、ローカルのファイルは消す
gh secret set PROVISIONER_APP_PRIVATE_KEY --repo "$REPO" \
  < ~/Downloads/comvace-training-provisioner.private-key.pem

rm ~/Downloads/comvace-training-provisioner.private-key.pem
```

## 4. org 側の前提を整える

### Base permissions を `No permission` にする → **対応済み**

**ここが「受講者本人と担当者だけが見える」の要** です。
既定値（`Read`）だと org メンバー全員が他の受講者の提出物を読めてしまいます。

`comvace-it-solution` は確認時点で既に `none` でした。変更は不要です。

```sh
# 確認用
gh api orgs/comvace-it-solution --jq .default_repository_permission   # → none
```

org Owner は Base permissions に関係なく全リポジトリを見られるので、担当者の閲覧性は保たれます。

### テンプレートリポジトリのフラグを立てる → **要対応**

`comvace-inc-frontend-basic-training` は確認時点で `is_template: false` でした。
このフラグが立っていないと払い出し API が失敗します。

```sh
gh api -X PATCH repos/comvace-it-solution/comvace-inc-frontend-basic-training -F is_template=true
```

### 講師チーム（任意）

現在 org にチームは作られていないため、`courses.json` では `instructorTeam` を省略しています。
この状態でも **org Owner は全リポジトリを閲覧できる**ので、担当者が Owner だけなら設定不要です。

Owner 以外のメンターにも見せたい場合はチームを作り、`courses.json` に追記してください。

```sh
gh api -X POST orgs/comvace-it-solution/teams -f name=instructors -f privacy=closed
```

```json
{
  "frontend-basic": {
    "template": "comvace-inc-frontend-basic-training",
    "repoPrefix": "comvace-frontend-training",
    "instructorTeam": "instructors"
  }
}
```

## 5. 受付の上限を決める（任意）

招待 URL は「知っている人なら誰でも使える」ため、万一リンクが外部に漏れたときの
被害を抑える上限を設けています。既定は **24 時間あたり 10 件** です。

同時期に 10 名以上が着手する研修なら、先に上げておいてください。

```sh
REPO=comvace-it-solution/comvace-training-enroll
gh variable set ENROLL_MAX_PER_DAY --repo "$REPO" --body 30
```

研修期間外に受付を閉じる場合は `ENROLL_OPEN` を `false` にします（未設定なら受付中）。

```sh
gh variable set ENROLL_OPEN --repo "$REPO" --body false
```

## 6. 通知を受け取る

払い出しに気づけるよう、研修担当者は受付リポジトリを Watch してください。

```sh
gh api -X PUT repos/comvace-it-solution/comvace-training-enroll/subscription -F subscribed=true
```

## 7. 点検する

```sh
./scripts/setup-org.sh comvace-it-solution/comvace-training-enroll
```

ラベル（`enroll` / `provisioned` / `provision-failed`）が無ければ作成し、
残りの前提条件は OK / TODO の一覧で表示します。TODO が残っていれば終了コード 1 になります。

> `enroll` ラベルの作成は飛ばさないでください。ワークフローはこのラベルが付いた Issue だけを
> 処理します。ラベルがリポジトリに存在しないとフォームからの付与が無視され、
> **申請しても何も起こらない**という分かりにくい症状になります。

## 8. 動作確認する

招待 URL を開いて、自分で実際に申請してみてください。事前登録は不要です。

<https://github.com/comvace-it-solution/comvace-training-enroll/issues/new?template=enroll.yml>

確認できたら、作られたリポジトリを削除します。

```sh
gh repo delete comvace-it-solution/comvace-frontend-training-ComvaceDeveloper-Yazawa --yes
```

---

## つまずきやすいところ

### リポジトリ作成が 403 で失敗する

App の権限不足か、インストール範囲が `All repositories` になっていないことがほとんどです。
必要な権限はレスポンスヘッダで確認できます。

```sh
gh api repos/comvace-it-solution/comvace-inc-frontend-basic-training/generate \
  -X POST --include 2>&1 | grep -i x-accepted-github-permissions
```

App の権限を後から変更した場合、org Owner が新しい権限を**承認**するまで
インストールは旧権限のまま動きます。
<https://github.com/organizations/comvace-it-solution/settings/installations> で保留中の承認を確認してください。

### 受講者が「リポジトリが見つからない」と言う

招待が未承認です。GitHub からの招待通知を承認するまでリポジトリは開けません。
これは GitHub の仕様で回避できません（Classroom でも同じでした）。

承認は org への参加ではなく、そのリポジトリへの外部コラボレーター招待に対するものです。
現在の受講者 31 名と同じ扱いになります。

### 申請しても何も起こらない

ワークフローは `enroll` ラベルが付いた Issue だけを処理します。
ラベルがリポジトリに存在しないとフォームからの付与が無視されるため、
`./scripts/setup-org.sh` を実行してラベルを作成してください。

次に Actions が無効化されていないかを確認します。

```sh
gh api repos/comvace-it-solution/comvace-training-enroll/actions/permissions
```

### 身に覚えのない払い出しがあった

招待 URL を知っている人は誰でも払い出せます（Classroom と同じ設計です）。
リポジトリを削除すれば元に戻ります。

```sh
gh repo delete comvace-it-solution/comvace-frontend-training-<アカウント名> --yes
```

受付を止めるには `ENROLL_OPEN` を `false` にします。

```sh
gh variable set ENROLL_OPEN --repo comvace-it-solution/comvace-training-enroll --body false
```

### 受付リポジトリを private にしたい場合

申請者のアカウント名を公開したくない場合は、受付リポジトリを private にできます。
ただし受講者が Issue を立てられるようにするため、**先に org へ招待しておく**必要があります。
「URL を踏むだけ」の手軽さは下がるので、通常は public のままを推奨します。
