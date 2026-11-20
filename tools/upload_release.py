#!/usr/bin/env python3
"""Upload media/ files as GitHub Release assets (stdlib only).

Token: PLAN2STREAM_GH_TOKEN, else ~/.config/plan2stream/gh_token (never printed). The machine-wide
GITHUB_TOKEN is deliberately ignored, and the token's login must equal the repo owner.
Creates the release if it is missing, then uploads every file in media/ that is
not already an asset with the same name and size.  A same-name/different-size
asset is deleted first, then re-uploaded.

Usage: python3 tools/upload_release.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
MIME = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".m4a": "audio/mp4", ".json": "application/json"}


def request(method: str, url: str, token: str, body: Optional[bytes] = None,
            content_type: str = "application/json") -> Any:
    """Perform an authenticated GitHub API request and return decoded JSON (or None)."""
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "plan2stream-upload")
    if body is not None:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = resp.read()
    return json.loads(data) if data else None


def get_release(repo: str, tag: str, token: str) -> Optional[dict[str, Any]]:
    """Return the release for `tag`, or None if it does not exist."""
    try:
        return request("GET", f"{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}", token)  # type: ignore[no-any-return]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def list_assets(repo: str, release_id: int, token: str) -> dict[str, dict[str, Any]]:
    """Map asset name -> asset dict for all assets of a release (paginated)."""
    assets: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        batch = request("GET", f"{API}/repos/{repo}/releases/{release_id}/assets?per_page=100&page={page}", token)
        if not batch:
            break
        for a in batch:
            assets[a["name"]] = a
        page += 1
    return assets


TOKEN_FILE = Path.home() / ".config" / "plan2stream" / "gh_token"


def load_token() -> str:
    """Token for the page's GitHub account (not the machine-wide GITHUB_TOKEN)."""
    tok = os.environ.get("PLAN2STREAM_GH_TOKEN", "").strip()
    if not tok and TOKEN_FILE.is_file():
        tok = TOKEN_FILE.read_text().strip()
    return tok


def referenced_files(manifest: Path) -> set[str]:
    """Every media file name the page loads, read from docs/media.json."""
    m = json.loads(manifest.read_text())
    names: set[str] = set()
    for entry in m.get("items", []) + m.get("wall", []) + m.get("hour", []):
        for key in ("src", "poster", "plan", "input_image", "input_audio"):
            if entry.get(key):
                names.add(str(entry[key]))
        if isinstance(entry.get("sprite"), dict) and entry["sprite"].get("src"):
            names.add(str(entry["sprite"]["src"]))
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default="lin-zhao-resoLve/Plan2Stream")
    ap.add_argument("--tag", default="assets-v1")
    ap.add_argument("--media-dir", type=Path, default=ROOT / "media")
    ap.add_argument("--dry-run", action="store_true", help="print the plan only; change nothing")
    ap.add_argument("--manifest", type=Path, default=ROOT / "docs" / "media.json", help="upload only files this manifest references")
    ap.add_argument("--all", action="store_true", help="upload every file in --media-dir")
    args = ap.parse_args()

    token = load_token()
    if not token:
        print(f"no token: set PLAN2STREAM_GH_TOKEN or write it to {TOKEN_FILE}", file=sys.stderr)
        return 2
    login = request("GET", f"{API}/user", token)["login"]
    owner = args.repo.split("/", 1)[0]
    if login.lower() != owner.lower():
        print(f"token belongs to {login!r}, not the repo owner {owner!r}; refusing", file=sys.stderr)
        return 2

    files = sorted(p for p in args.media_dir.iterdir() if p.is_file() and ".part" not in p.name)
    if not args.all:  # only what the page references; media/ may keep unused encodes as a cache
        used = referenced_files(args.manifest)
        files = [p for p in files if p.name in used]
    release = get_release(args.repo, args.tag, token)
    if release is None:
        print(f"release {args.tag!r} missing in {args.repo}: would create" if args.dry_run
              else f"creating release {args.tag!r}")
        if args.dry_run:
            for p in files:
                print(f"  upload  {p.name} ({p.stat().st_size} bytes)")
            print(f"plan: create release + upload {len(files)} files")
            return 0
        release = request("POST", f"{API}/repos/{args.repo}/releases", token, json.dumps({
            "tag_name": args.tag, "name": "Media assets v1",
            "body": "Encoded media for the Plan2Stream project page.", "draft": False, "prerelease": False,
        }).encode())
    assert release is not None
    existing = list_assets(args.repo, release["id"], token)
    upload_base = release["upload_url"].split("{", 1)[0]

    n_up = n_skip = n_replace = 0
    for p in files:
        size = p.stat().st_size
        old = existing.get(p.name)
        if old is not None and old["size"] == size:
            n_skip += 1
            print(f"  skip    {p.name}")
            continue
        action = "replace" if old is not None else "upload "
        print(f"  {action} {p.name} ({size} bytes)")
        if args.dry_run:
            n_replace += old is not None
            n_up += old is None
            continue
        if old is not None:
            request("DELETE", f"{API}/repos/{args.repo}/releases/assets/{old['id']}", token)
            n_replace += 1
        else:
            n_up += 1
        ctype = MIME.get(p.suffix, mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        request("POST", f"{upload_base}?name={urllib.parse.quote(p.name)}", token, p.read_bytes(), ctype)
    print(f"{'plan' if args.dry_run else 'done'}: {n_up} new, {n_replace} replaced, {n_skip} unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
