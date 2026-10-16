#!/usr/bin/env python3
"""Puts SecurePrint's risk weights back to the shipped values in
config/weights.json, turns masking back on for CONFIDENTIAL, and adds any
label words from config/patterns.json that the built-in detection rules are
missing (words an admin added are kept). Runs through the running server's
API, signed in as an administrator.

    python3 scripts/restore-default-scoring.py [--server http://localhost:8000]

It asks for the admin username and password itself; nothing is stored.
"""
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"
WEIGHTS_FILE = CONFIG / "weights.json"
PATTERNS_FILE = CONFIG / "patterns.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://localhost:8000")
    args = parser.parse_args()
    api = args.server.rstrip("/") + "/api/v1"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(api + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=15) as resp:
            return json.loads(resp.read() or b"null")

    username = input("Admin username: ").strip() or "admin"
    password = getpass.getpass("Admin password (not shown): ")
    try:
        user = call("POST", "/auth/login", {"username": username, "password": password})
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Sign-in failed ({exc.code}). Check the username and password.")
    if user.get("role") != "ADMIN":
        raise SystemExit(f"'{username}' is not an administrator.")

    shipped = json.loads(WEIGHTS_FILE.read_text())
    for row in call("GET", "/rules/weights/all"):
        want = shipped.get(row["category"], {}).get("weight")
        if want is None or row["weight"] == want:
            print(f"  {row['label']:<26} {row['weight']:>3}  (unchanged)")
            continue
        call("PATCH", f"/rules/weights/{row['id']}", {"weight": want})
        print(f"  {row['label']:<26} {row['weight']:>3} -> {want}")

    for policy in call("GET", "/policies"):
        if policy["classification"] == "CONFIDENTIAL" and not policy["require_masking"]:
            call("PATCH", f"/policies/{policy['id']}", {"require_masking": True})
            print("  CONFIDENTIAL: Require Masking turned on")

    shipped_rules = json.loads(PATTERNS_FILE.read_text())
    for rule in call("GET", "/rules"):
        cfg = shipped_rules.get(rule["name"])
        if not cfg or not cfg.get("context_keywords"):
            continue
        current = [w.strip() for w in rule["context_keywords"].split(",") if w.strip()]
        missing = [w for w in cfg["context_keywords"] if w not in current]
        if missing:
            call("PATCH", f"/rules/{rule['id']}", {"context_keywords": ",".join(current + missing)})
            print(f"  Rule {rule['name']}: added {len(missing)} label words")

    call("POST", "/auth/logout")
    print("Done. New print jobs use the restored weights.")


if __name__ == "__main__":
    main()
