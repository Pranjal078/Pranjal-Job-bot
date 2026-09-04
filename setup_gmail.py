"""
setup_gmail.py — One-time OAuth2 setup for Gmail API access.

Run this script ONCE locally to authenticate with your Google account
and generate a token.json file. This token is then used by the bot to
read your Gmail (specifically LinkedIn job-alert emails) without a password.

The token is a refresh token — it stays valid until you revoke access
in your Google account security settings.

Steps:
  1. Go to https://console.cloud.google.com/
  2. Create a project (or use existing)
  3. Enable "Gmail API"
  4. Create OAuth2 credentials (Desktop app type)
  5. Download credentials.json to this project folder
  6. Run: python setup_gmail.py
  7. Authorize in browser → token.json is created
  8. For GitHub Actions: store token.json content as a repository secret
     named GMAIL_TOKEN_JSON (see README.md for details)
"""

import json
import os
import sys
from pathlib import Path


def setup_gmail_auth(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
):
    """Run the OAuth2 flow and save the resulting token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("ERROR: Missing dependencies. Run: pip install -r requirements.txt")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    creds = None

    # Check for existing valid token
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds and creds.valid:
            print(f"✅ Existing token at '{token_path}' is still valid. Nothing to do.")
            return
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Token expired — refreshing...")
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            print(f"✅ Token refreshed and saved to '{token_path}'.")
            return

    # Need fresh auth
    if not Path(credentials_path).exists():
        print(f"""
ERROR: credentials.json not found at '{credentials_path}'.

To get it:
  1. Go to https://console.cloud.google.com/
  2. Select your project (or create one)
  3. Go to APIs & Services → Enable APIs → search "Gmail API" → Enable
  4. Go to APIs & Services → Credentials
  5. Click "Create Credentials" → "OAuth client ID"
  6. Application type: "Desktop app" → Create
  7. Download the JSON file and save it as: {credentials_path}
  8. Re-run this script.
""")
        sys.exit(1)

    print("🌐 Opening browser for Google OAuth2 authorization...")
    print("   You will be asked to sign in and grant Gmail read-only access.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"""
✅ Authorization successful! Token saved to '{token_path}'.

Next steps:
  • For local use: the bot will use this token automatically.
  • For GitHub Actions:
      1. Copy the contents of token.json
      2. In your GitHub repo → Settings → Secrets → Actions
      3. Add secret: GMAIL_TOKEN_JSON = <paste token.json contents>
      4. The workflow will write it to disk before running the bot.
      See README.md for the full GitHub Actions setup guide.

⚠️  Keep token.json private — it grants read access to your Gmail.
    It is already listed in .gitignore.
""")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Set up Gmail API OAuth2 token.")
    parser.add_argument("--credentials", default="credentials.json", help="Path to OAuth2 credentials JSON")
    parser.add_argument("--token", default="token.json", help="Where to save the token")
    args = parser.parse_args()

    setup_gmail_auth(args.credentials, args.token)
