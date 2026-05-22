from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

from jira_client import JiraClient
from sweep import collect
from report import render


def resolve_token(flag_token: str | None, config_token: str | None) -> str:
    token = os.environ.get("JIRA_API_TOKEN") or flag_token or config_token
    if not token:
        sys.exit("No API token. Set JIRA_API_TOKEN, pass --token, or put token in config.toml.")
    return token


def load_settings(args) -> dict:
    config: dict = {}
    if getattr(args, "config", None):
        with open(args.config, "rb") as fh:
            config = tomllib.load(fh)
    groups = args.group if getattr(args, "group", None) else config.get("groups", [])
    return {
        "base_url": args.base_url or config.get("base_url"),
        "email": args.email or config.get("email"),
        "config_token": config.get("token"),
        "groups": groups,
        "out_dir": args.out_dir or config.get("out_dir") or "./reports",
    }


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Audit where a Jira Cloud group is referenced.")
    p.add_argument("--config")
    p.add_argument("--base-url", dest="base_url")
    p.add_argument("--email")
    p.add_argument("--token")
    p.add_argument("--group", action="append", help="repeatable")
    p.add_argument("--out-dir", dest="out_dir")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    settings = load_settings(args)
    if not settings["base_url"] or not settings["email"]:
        sys.exit("base_url and email are required (via flags or config.toml).")
    if not settings["groups"]:
        sys.exit("No groups specified (use --group or config.toml groups=[...]).")
    token = resolve_token(getattr(args, "token", None), settings["config_token"])

    client = JiraClient(settings["base_url"], settings["email"], token)
    try:
        me = client.verify_auth()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Auth failed against {settings['base_url']}: {exc}\n"
                 f"Note: this tool uses HTTP Basic (email + token). Bearer tokens return 403 on Cloud.")
    print(f"Authenticated as {me.get('displayName')} on {settings['base_url']}")

    out_dir = Path(settings["out_dir"])
    for group in settings["groups"]:
        print(f"Auditing group: {group} ...")
        audit = collect(client, group)
        pdf_path, json_path = render(audit, out_dir)
        flag = f"  (incomplete: {', '.join(audit.incomplete_dimensions)})" if audit.incomplete_dimensions else ""
        print(f"  -> {pdf_path}\n  -> {json_path}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
