#!/usr/bin/env python3
"""Create the OAuth token secret used for JEAC personal Google Drive uploads.

Run this once locally, never on GitHub Actions:
    python scripts/authorize_google_drive_oauth.py --client-json path/to/client.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authorize personal Google Drive uploads for JEAC."
    )
    parser.add_argument(
        "--client-json",
        required=True,
        type=Path,
        help="Desktop OAuth client JSON downloaded from Google Cloud",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("google_drive_oauth_token.json"),
        help="Where to write the token JSON (default: ./google_drive_oauth_token.json)",
    )
    args = parser.parse_args()

    if not args.client_json.is_file():
        raise SystemExit(f"OAuth client JSON does not exist: {args.client_json}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_json), scopes=[DRIVE_SCOPE]
    )
    credentials = flow.run_local_server(port=0, prompt="consent")

    if not credentials.refresh_token:
        raise SystemExit(
            "No refresh token was returned. Revoke the app's Google Account access "
            "then run this command again."
        )

    args.output.write_text(credentials.to_json(), encoding="utf-8")
    print(f"OAuth token saved to: {args.output}")
    print("Copy the entire JSON into GitHub Secret GOOGLE_DRIVE_OAUTH_TOKEN_JSON.")
    print("Do not commit this file or share it in chat.")


if __name__ == "__main__":
    main()
