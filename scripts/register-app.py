#!/usr/bin/env python3
"""GitHub App Manifest フローで払い出し用の GitHub App を登録する。

GitHub App を作る API は存在しないため、本来はブラウザでフォームを手入力する
必要がある。Manifest フローを使うと、権限や設定を JSON で渡した状態で
登録画面を開けるので、利用者は「Create GitHub App」を押すだけで済み、
権限の付け間違いも起きない。

やること:
  1. ローカルに一時的な HTTP サーバーを立てる（callback 受け取り用）
  2. ブラウザを開き、manifest を添えて GitHub の登録画面へ POST する
  3. GitHub からの callback で一時 code を受け取る
  4. code を App ID と秘密鍵に交換して保存する

  使い方:
    python3 scripts/register-app.py <org> <受付リポジトリ> [--outdir DIR]

  例:
    python3 scripts/register-app.py \\
      comvace-it-solution comvace-it-solution/comvace-training-enroll
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

# Manifest フロー全体を 1 時間以内に終える必要がある（GitHub の制約）。
# ブラウザ操作を待つだけなので、既定はその上限に近い値にしておく。
TIMEOUT_SECONDS = int(os.environ.get("REGISTER_APP_TIMEOUT", "3000"))


def find_free_port() -> int:
    """callback 用の空きポートを取る。

    redirect_url は manifest に埋め込むため、サーバー起動前にポートを
    確定させる必要がある。
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_manifest(org: str, repo: str, port: int) -> dict:
    repo_url = f"https://github.com/{repo}"
    return {
        "name": "comvace-training-provisioner",
        "description": (
            "研修リポジトリの払い出し用。テンプレートから private リポジトリを作成し、"
            "受講者を collaborator として招待する。"
        ),
        "url": repo_url,
        "redirect_url": f"http://127.0.0.1:{port}/callback",
        # Webhook は使わない（Actions から API を呼ぶだけ）が、url は必須項目。
        "hook_attributes": {"url": repo_url, "active": False},
        "public": False,
        "default_events": [],
        # 最小権限。administration(write) がリポジトリ作成と collaborator 追加に必要。
        # contents(read) はテンプレートの読み取りに必要。metadata は自動で付く。
        # instructorTeam / inviteToOrg を使う場合のみ organization members(write) を
        # 後から追加する。
        "default_permissions": {
            "administration": "write",
            "contents": "read",
        },
    }


def exchange_code(code: str) -> dict:
    """一時 code を App の設定（ID・秘密鍵）に交換する。

    認証の有無に左右されないよう gh CLI 経由で叩く。
    """
    result = subprocess.run(
        ["gh", "api", "-X", "POST", f"/app-manifests/{code}/conversions"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"code の交換に失敗しました:\n{result.stderr.strip()}")
    return json.loads(result.stdout)


class Handler(http.server.BaseHTTPRequestHandler):
    manifest: dict = {}
    org: str = ""
    result: dict | None = None
    error: str | None = None
    done = threading.Event()

    def log_message(self, *args):  # アクセスログは出さない
        pass

    def _html(self, status: int, body: str) -> None:
        payload = f"<!doctype html><meta charset=utf-8>{body}".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path)

        if path.path == "/":
            # GitHub の登録画面は POST でしか manifest を受け取らないため、
            # 自動送信するフォームを挟む。
            action = (
                f"https://github.com/organizations/{self.org}/settings/apps/new"
            )
            manifest_json = json.dumps(self.manifest)
            self._html(
                200,
                f"""
                <title>GitHub App を登録</title>
                <body style="font-family:system-ui;padding:3rem;line-height:1.7">
                <p>GitHub の登録画面へ移動します…</p>
                <form id="f" method="post" action="{action}">
                  <input type="hidden" name="manifest"
                         value="{urllib.parse.quote(manifest_json, safe='')}">
                  <noscript><button type="submit">続ける</button></noscript>
                </form>
                <script>
                  const f = document.getElementById("f");
                  // value は URL エンコードして埋めたので、送信前に戻す
                  f.manifest.value = decodeURIComponent(f.manifest.value);
                  f.submit();
                </script>
                </body>
                """,
            )
            return

        if path.path == "/callback":
            params = urllib.parse.parse_qs(path.query)
            code = (params.get("code") or [""])[0]
            if not code:
                Handler.error = "callback に code が含まれていませんでした"
                self._html(400, "<p>code を受け取れませんでした。</p>")
                Handler.done.set()
                return
            try:
                Handler.result = exchange_code(code)
            except Exception as e:  # noqa: BLE001
                Handler.error = str(e)
                self._html(500, f"<p>失敗しました: {e}</p>")
                Handler.done.set()
                return

            name = Handler.result.get("name", "")
            self._html(
                200,
                f"""
                <title>登録できました</title>
                <body style="font-family:system-ui;padding:3rem;line-height:1.7">
                <h2>GitHub App「{name}」を登録しました</h2>
                <p>このタブは閉じて、ターミナルに戻ってください。</p>
                </body>
                """,
            )
            Handler.done.set()
            return

        self._html(404, "<p>not found</p>")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("org", help="App を登録する organization")
    p.add_argument("repo", help="受付リポジトリ（owner/name）")
    p.add_argument(
        "--outdir",
        default=None,
        help="App ID と秘密鍵の保存先（既定: 一時ディレクトリ）",
    )
    args = p.parse_args()

    outdir = Path(args.outdir) if args.outdir else Path("/tmp/gh-app-setup")
    outdir.mkdir(parents=True, exist_ok=True)
    os.chmod(outdir, 0o700)

    port = find_free_port()
    Handler.manifest = build_manifest(args.org, args.repo, port)
    Handler.org = args.org

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{port}/"
    print(f"ブラウザを開きます: {url}")
    print("GitHub の画面で「Create GitHub App」を押してください。")
    print("（開かない場合は上記 URL を手動で開いてください）")
    webbrowser.open(url)

    if not Handler.done.wait(timeout=TIMEOUT_SECONDS):
        print("タイムアウトしました。やり直してください。", file=sys.stderr)
        return 1
    server.shutdown()

    if Handler.error or not Handler.result:
        print(f"失敗: {Handler.error}", file=sys.stderr)
        return 1

    app = Handler.result
    pem_path = outdir / "private-key.pem"
    # 秘密鍵は本人だけが読めるようにしてから書く
    fd = os.open(pem_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(app["pem"])

    # 秘密鍵以外のメタ情報。ログに鍵を出さないよう pem は含めない。
    meta = {k: app.get(k) for k in ("id", "slug", "name", "html_url", "owner")}
    meta["owner"] = (app.get("owner") or {}).get("login")
    (outdir / "app.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    print()
    print(f"App ID   : {app['id']}")
    print(f"slug     : {app['slug']}")
    print(f"秘密鍵   : {pem_path}")
    print(f"設定画面 : {app['html_url']}")
    print()
    print("次にこの App を org にインストールしてください（All repositories）:")
    print(f"  https://github.com/apps/{app['slug']}/installations/new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
