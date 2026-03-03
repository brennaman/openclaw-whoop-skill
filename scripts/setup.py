#!/usr/bin/env python3
"""Retrieve WHOOP OAuth tokens from the relay and save locally."""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

RELAY_BASE = "https://www.paulbrennaman.me/api/whoop/token"
CREDS_PATH = os.path.expanduser(
    "~/.openclaw/workspace/knowledge/resources/whoop-credentials.json"
)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch WHOOP tokens from the OAuth relay"
    )
    parser.add_argument(
        "--code", required=True, help="Retrieval code from the connect flow"
    )
    args = parser.parse_args()

    url = f"{RELAY_BASE}/{args.code}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(
                "Error: Code is invalid or expired (codes last 10 minutes, single-use)."
            )
        else:
            print(f"Error: HTTP {e.code} — {e.read().decode()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    os.makedirs(os.path.dirname(CREDS_PATH), exist_ok=True)
    with open(CREDS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"Tokens saved to {CREDS_PATH}")
    print("Verify with: python3 fetch.py /user/profile/basic")


if __name__ == "__main__":
    main()
