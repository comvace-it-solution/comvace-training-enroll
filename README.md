# 研修リポジトリ払い出し受付

GitHub Classroom（2026-08-28 廃止）の「招待 URL を踏むと org 内に自分専用の
プライベートリポジトリができる」フローを、GitHub の標準機能だけで再現したものです。

受講者が増えても担当者側の作業はありません。招待 URL は使い回せます。

## 受講者の方へ

下のリンクを開いて、表示されるフォームを送信してください。

**→ [研修リポジトリを払い出す](https://github.com/comvace-it-solution/comvace-training-enroll/issues/new?template=enroll.yml)**

1 分ほどで、あなた専用のプライベートリポジトリが作成され、
その URL がフォーム（Issue）にコメントされます。

作成後、GitHub から届く**招待の通知を承認**してください。
承認するまでリポジトリは開けません。

---

## 仕組み

```
受講者がリンクを開く
  → Issue Form を送信（enroll ラベルが付く）
      → provision ワークフローが起動
          1. 受付中かどうか（ENROLL_OPEN）を確認
          2. 直近 24 時間の払い出し数が上限内かを確認
          3. GitHub App トークンでテンプレートから private リポジトリを生成
          4. 受講者本人を外部コラボレーター（Write）として招待
          5. リポジトリ URL をコメントして Issue をクローズ
```

受講者を特定するのに Issue 本文の入力は使わず、**Issue 作成者**
（`github.event.issue.user.login`）を使います。ここは偽装できないため、
他人のアカウント名で払い出すことはできません。

「本人と担当者だけが見える」状態は、以下の組み合わせで実現しています。

- org の Base permissions が `No permission` → 他の受講者からは見えない
- 受講者本人を direct collaborator（Write）で追加 → 本人は読み書きできる
- org Owner は Base permissions に関係なく全リポジトリを見られる → 担当者は見える

## アクセス制御の考え方

**招待 URL を知っている人は誰でも払い出せます。** これは Classroom と同じ設計です。
GitHub も Classroom の招待リンクについて
[「リンクを持つ人は誰でも受け入れられる。これは意図的な仕様」](https://bounty.github.com/targets/github-education.html)
と明記していました（教員が自分の経路でリンクを配るため、GitHub 側では受け取り手を判定できないという理由）。

名簿による事前許可はしません。受講者が増えるたびに担当者が作業する運用になり、
Classroom より手間が増えてしまうためです。

代わりに、**悪用されたときの影響を小さく保つ**方向で守っています。

| 仕掛け                        | 効果                                                                              |
| ----------------------------- | --------------------------------------------------------------------------------- |
| org への自動招待をしない      | 第三者が org メンバーになれない。現在の受講者と同じ外部コラボレーター扱いに留まる |
| 24 時間あたりの払い出し上限   | リンクが外部に漏れても大量に作られない。上限到達時は自動停止して担当者に通知      |
| 受付スイッチ（`ENROLL_OPEN`） | 研修開始時期だけ開けておける。受講者ごとではなく期間単位の管理                    |
| 受付リポジトリの Watch        | 申請があるたびに通知が届く。不審な払い出しに気づける                              |
| リポジトリは常に private      | 払い出されても、その人専用のコピー 1 個しか見えない                               |

想定外の払い出しがあった場合は、リポジトリを削除すれば元に戻ります。

```sh
gh repo delete comvace-it-solution/comvace-frontend-training-<アカウント名> --yes
```

## 運用

### 受講者が増えたとき

**何もしません。** 同じ招待 URL を渡すだけです。

### 研修期間外に受付を閉じたいとき

```sh
REPO=comvace-it-solution/comvace-training-enroll

# 受付停止（申請が来ても自動で却下コメントが付きます）
gh variable set ENROLL_OPEN --repo "$REPO" --body false

# 受付再開
gh variable set ENROLL_OPEN --repo "$REPO" --body true
```

変数が未設定の場合は「受付中」として扱います。

### 一度に大人数を受け入れるとき

既定では 24 時間あたり 10 件が上限です。同時期に 10 名以上が着手する場合は上限を上げてください。

```sh
gh variable set ENROLL_MAX_PER_DAY --repo "$REPO" --body 30
```

上限に達した申請は却下コメントが付き、`provision-failed` ラベルで **open のまま**残ります。
上限を上げたあと、受講者がもう一度フォームを送信すれば払い出されます。

### コースを追加したいとき

`courses.json` にエントリを足します。

```json
{
  "frontend-basic": {
    "template": "comvace-inc-frontend-basic-training",
    "repoPrefix": "comvace-frontend-training"
  },
  "react-basic": {
    "template": "comvace-inc-react-basic-training",
    "repoPrefix": "comvace-react-training"
  }
}
```

あわせて `.github/ISSUE_TEMPLATE/enroll.yml` の `options` にもコース名を追加してください。
この 2 箇所の値は一致させる必要があります。

| キー             | 既定    | 意味                                                                            |
| ---------------- | ------- | ------------------------------------------------------------------------------- |
| `template`       | 必須    | 複製元のテンプレートリポジトリ名（org 内）                                      |
| `repoPrefix`     | 必須    | 払い出すリポジトリ名の接頭辞。`<prefix>-<アカウント名>` になります              |
| `instructorTeam` | なし    | Admin を付与する org チーム。省略すると付与しません                             |
| `inviteToOrg`    | `false` | `true` にすると org にも招待します。**第三者が org メンバーになれるため非推奨** |

### 払い出しが失敗したとき

担当者の判断が必要な場合、Issue は `provision-failed` ラベルが付いた **open のまま**残ります。

**→ [対応が必要な申請を見る](https://github.com/comvace-it-solution/comvace-training-enroll/issues?q=is%3Aopen+label%3Aprovision-failed)**

Issue にコメントされた実行ログのリンクから原因を確認してください。
原因を直したあと、同じ受講者がもう一度フォームを送信すれば再実行されます。
ワークフローは既存リポジトリがあれば作成をスキップするので、二重に作られることはありません。

### 払い出し済みリポジトリの一覧

```sh
gh repo list comvace-it-solution --limit 200 \
  --json name,createdAt,visibility \
  --jq '.[] | select(.name | startswith("comvace-frontend-training-")) | [.createdAt, .visibility, .name] | @tsv' \
  | sort
```

誰に払い出したかは、受付リポジトリの
[`provisioned` ラベル付き Issue](https://github.com/comvace-it-solution/comvace-training-enroll/issues?q=label%3Aprovisioned)
からも追えます（氏名の申告を含む）。

## ファイル構成

| パス                                | 役割                                          |
| ----------------------------------- | --------------------------------------------- |
| `.github/ISSUE_TEMPLATE/enroll.yml` | 受講者が入力するフォーム（= 招待 URL の中身） |
| `.github/workflows/provision.yml`   | 払い出し本体                                  |
| `courses.json`                      | コース定義（テンプレート・命名規則・権限）    |
| `scripts/setup-org.sh`              | org / リポジトリ側の前提条件の点検            |
| `SETUP.md`                          | 初回セットアップ手順                          |

## セットアップ

初回のみ GitHub App の作成と org 設定が必要です。[SETUP.md](./SETUP.md) を参照してください。
