#!/usr/bin/env bash
#
# 払い出しワークフローが動くための org / リポジトリ側の前提条件を点検する。
#
# 読み取りと「安全な作成」（ラベル）だけを行い、
# org 全体に影響する設定変更は実行せずコマンドを提示するだけに留める。
#
#   使い方: ./scripts/setup-org.sh [受付リポジトリ]
#   例:     ./scripts/setup-org.sh comvace-it-solution/comvace-training-enroll

set -euo pipefail

ENROLL_REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
ORG="${ENROLL_REPO%%/*}"

ok()   { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
warn() { printf '  \033[33mTODO\033[0m  %s\n' "$1"; }
info() { printf '\n\033[1m%s\033[0m\n' "$1"; }
todo=0

info "1. 受付リポジトリ: $ENROLL_REPO"

visibility="$(gh api "repos/$ENROLL_REPO" --jq .visibility)"
if [ "$visibility" = "public" ]; then
  ok "public（受講者が org 未参加でもフォームを送信できます）"
else
  warn "visibility が $visibility です。org 未参加の受講者はフォームを開けません。"
  warn "  gh api -X PATCH repos/$ENROLL_REPO -f visibility=public"
  todo=$((todo + 1))
fi

# フォームが付与するラベルと、ワークフローが結果に応じて付けるラベルを用意する
for pair in "enroll:0E8A16:払い出しフォームからの申請" \
            "provisioned:1D76DB:払い出し済み" \
            "provision-failed:B60205:担当者の確認が必要な申請"; do
  name="${pair%%:*}"
  rest="${pair#*:}"
  color="${rest%%:*}"
  desc="${rest#*:}"
  if gh api "repos/$ENROLL_REPO/labels/$name" --silent 2>/dev/null; then
    ok "ラベル '$name' は既に存在します"
  else
    gh api -X POST "repos/$ENROLL_REPO/labels" \
      -f name="$name" -f color="$color" -f description="$desc" --silent
    ok "ラベル '$name' を作成しました"
  fi
done

info "2. Organization の既定権限: $ORG"

base="$(gh api "orgs/$ORG" --jq .default_repository_permission)"
if [ "$base" = "none" ]; then
  ok "Base permissions = none（受講者同士が互いの提出物を見られません）"
else
  warn "Base permissions = $base です。この状態では org メンバー全員が"
  warn "他の受講者のリポジトリを閲覧できてしまいます。"
  warn "  gh api -X PATCH orgs/$ORG -f default_repository_permission=none"
  warn "  ※ org 内の既存リポジトリ全体に影響します。必ず内容を確認してから実行してください。"
  todo=$((todo + 1))
fi

info "3. コース定義（courses.json）"

# コース名だけを読み、各値は個別に引く。
# TSV + IFS=$'\t' ではタブが空白文字として連続分を潰すため、
# 省略されたキー（instructorTeam など）があるとフィールドがずれる。
while IFS= read -r course; do
  printf '  [%s]\n' "$course"

  template="$(jq -r --arg c "$course" '.[$c].template' courses.json)"
  team="$(jq -r --arg c "$course" '.[$c].instructorTeam // ""' courses.json)"
  invite="$(jq -r --arg c "$course" '(.[$c].inviteToOrg // false) | tostring' courses.json)"

  if ! gh api "repos/$ORG/$template" --silent 2>/dev/null; then
    warn "  テンプレート $ORG/$template が見つかりません"
    todo=$((todo + 1))
    continue
  fi

  if [ "$(gh api "repos/$ORG/$template" --jq .is_template)" = "true" ]; then
    # 全角文字が直後に続くので ${} で変数名の終わりを明示する
    ok "  テンプレート ${template}（Template repository 有効）"
  else
    warn "  $template の Template repository フラグが無効です"
    warn "    gh api -X PATCH repos/$ORG/$template -F is_template=true"
    todo=$((todo + 1))
  fi

  if [ -n "$team" ] && [ "$team" != "null" ]; then
    if gh api "orgs/$ORG/teams/$team" --silent 2>/dev/null; then
      ok "  講師チーム '$team'"
    else
      warn "  講師チーム '$team' が存在しません"
      warn "    gh api -X POST orgs/$ORG/teams -f name=$team -f privacy=closed"
      todo=$((todo + 1))
    fi
  fi

  if [ "$invite" = "true" ]; then
    warn "  inviteToOrg = true です。招待リンクを知った第三者が org メンバーに"
    warn "  なれてしまうため、意図した設定か確認してください。"
  fi
done < <(jq -r 'keys[]' courses.json)

info "4. 受付のスイッチと上限"

enroll_open="$(gh variable get ENROLL_OPEN --repo "$ENROLL_REPO" 2>/dev/null || echo "")"
case "$enroll_open" in
  "")      ok "ENROLL_OPEN 未設定 → 受付中（既定）" ;;
  "true")  ok "ENROLL_OPEN=true → 受付中" ;;
  *)       ok "ENROLL_OPEN=$enroll_open → 受付停止中（申請は自動で却下されます）" ;;
esac

max_per_day="$(gh variable get ENROLL_MAX_PER_DAY --repo "$ENROLL_REPO" 2>/dev/null || echo "")"
if [ -z "$max_per_day" ]; then
  ok "ENROLL_MAX_PER_DAY 未設定 → 24 時間あたり 10 件まで（既定）"
else
  ok "ENROLL_MAX_PER_DAY=$max_per_day → 24 時間あたり $max_per_day 件まで"
fi

info "5. Actions のシークレット・変数"

if gh variable list --repo "$ENROLL_REPO" --json name --jq '.[].name' 2>/dev/null \
    | grep -qx PROVISIONER_APP_ID; then
  ok "変数 PROVISIONER_APP_ID"
else
  warn "変数 PROVISIONER_APP_ID が未設定です（SETUP.md 参照）"
  todo=$((todo + 1))
fi

if gh secret list --repo "$ENROLL_REPO" --json name --jq '.[].name' 2>/dev/null \
    | grep -qx PROVISIONER_APP_PRIVATE_KEY; then
  ok "シークレット PROVISIONER_APP_PRIVATE_KEY"
else
  warn "シークレット PROVISIONER_APP_PRIVATE_KEY が未設定です（SETUP.md 参照）"
  todo=$((todo + 1))
fi

info "6. 通知"

watching="$(gh api "repos/$ENROLL_REPO/subscription" --jq '.subscribed // false' 2>/dev/null || echo false)"
if [ "$watching" = "true" ]; then
  ok "あなたはこのリポジトリを Watch 中です（申請時に通知が届きます）"
else
  warn "このリポジトリを Watch していません。"
  warn "払い出しに気づけるよう、研修担当者は Watch → All Activity を推奨します。"
  warn "  gh api -X PUT repos/$ENROLL_REPO/subscription -F subscribed=true"
fi

if [ "$todo" -eq 0 ]; then
  printf '\n\033[32m前提条件はすべて満たされています。\033[0m\n'
else
  printf '\n\033[33m未対応の項目が %d 件あります。上記 TODO を確認してください。\033[0m\n' "$todo"
  exit 1
fi
