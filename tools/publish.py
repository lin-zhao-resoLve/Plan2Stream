#!/usr/bin/env python3
"""Publish the page: create the public GitHub repo, push `main`, enable Pages, upload release assets.

Token: PLAN2STREAM_GH_TOKEN, else ~/.config/plan2stream/gh_token (never printed, never written to
.git/config). The machine-wide GITHUB_TOKEN is ignored, and the token's login must equal the owner.
A fine-grained token needs: Administration (write, only to create the repo), Contents (write), Pages (write).

Each step is idempotent: an existing repo is reused, `main` is pushed without force, an existing Pages
site is left alone, and release assets that already match are skipped.

Usage: python3 tools/publish.py [--dry-run] [--skip-assets]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_release import API, TOKEN_FILE, load_token, request  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OWNER, NAME = "lin-zhao-resoLve", "Plan2Stream"
DESCRIPTION = "Project page: Plan2Stream, real-time long audio-video generation with continuous planning"


def get(url: str, token: str) -> Optional[Any]:
    """GET a GitHub API URL; None on 404."""
    try:
        return request("GET", url, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def git_push(token: str, dry_run: bool) -> None:
    """Push local `main` to the repo over HTTPS; the token reaches git only through GIT_ASKPASS."""
    url = f"https://github.com/{OWNER}/{NAME}.git"
    if dry_run:
        print(f"  would push main -> {url}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        askpass = Path(tmp) / "askpass.sh"
        askpass.write_text('#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) echo "$P2S_TOKEN" ;; esac\n')
        askpass.chmod(0o700)
        env = {**os.environ, "GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0", "P2S_TOKEN": token}
        env.pop("GITHUB_TOKEN", None)
        subprocess.run(["git", "-c", "credential.helper=", "push", url, "main:main"], cwd=ROOT, env=env, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="check the token and print the plan; change nothing")
    ap.add_argument("--skip-assets", action="store_true", help="do not upload release assets")
    args = ap.parse_args()

    token = load_token()
    if not token:
        print(f"no token: set PLAN2STREAM_GH_TOKEN or write it to {TOKEN_FILE}", file=sys.stderr)
        return 2
    login = request("GET", f"{API}/user", token)["login"]
    if login.lower() != OWNER.lower():
        print(f"token belongs to {login!r}, not {OWNER!r}; refusing", file=sys.stderr)
        return 2
    print(f"token ok: {login}")

    repo_api = f"{API}/repos/{OWNER}/{NAME}"
    repo = get(repo_api, token)
    if repo is None:
        print(f"  {'would create' if args.dry_run else 'creating'} public repo {OWNER}/{NAME}")
        if not args.dry_run:
            request("POST", f"{API}/user/repos", token, json.dumps({
                "name": NAME, "description": DESCRIPTION, "private": False,
                "has_issues": True, "has_wiki": False, "has_projects": False,
            }).encode())
    else:
        print(f"  repo exists ({'private' if repo['private'] else 'public'})")
        if repo["private"]:
            print(f"  {'would make' if args.dry_run else 'making'} it public")
            if not args.dry_run:
                request("PATCH", repo_api, token, json.dumps({"private": False}).encode())

    git_push(token, args.dry_run)

    pages = None if args.dry_run and repo is None else get(f"{repo_api}/pages", token)
    if pages is None:
        print(f"  {'would enable' if args.dry_run else 'enabling'} Pages from main:/docs")
        if not args.dry_run:
            request("POST", f"{repo_api}/pages", token, json.dumps({"source": {"branch": "main", "path": "/docs"}}).encode())
            pages = get(f"{repo_api}/pages", token)
    else:
        print(f"  Pages already enabled ({pages['source']['branch']}:{pages['source']['path']})")

    if not args.skip_assets:
        cmd = [sys.executable, str(ROOT / "tools" / "upload_release.py"), "--repo", f"{OWNER}/{NAME}"]
        if args.dry_run:
            if repo is None:
                print("  would create release assets-v1 and upload every file docs/media.json references")
                cmd = []
            else:
                cmd.append("--dry-run")
        if cmd:
            env = {**os.environ, "PLAN2STREAM_GH_TOKEN": token}
            env.pop("GITHUB_TOKEN", None)
            subprocess.run(cmd, env=env, check=True)

    site = (pages or {}).get("html_url") or f"https://{OWNER.lower()}.github.io/{NAME}/"
    print(f"{'plan done' if args.dry_run else 'published'}: https://github.com/{OWNER}/{NAME}  ·  {site}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
