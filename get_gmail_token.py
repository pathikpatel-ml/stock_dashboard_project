"""
One-time script to get a Gmail OAuth2 refresh token for the dashboard.
Run this ONCE on your local machine. Copy the printed values into Render env vars.

SETUP (5 minutes):
1. Go to https://console.cloud.google.com  (free, uses your existing Google account)
2. Create a new project (e.g. "stock-dashboard")
3. Search for "Gmail API" → Enable it
4. Go to APIs & Services → Credentials → Create Credentials → OAuth client ID
5. Application type: Desktop app → Create
6. Download the JSON → save as client_secret.json in this folder
7. Run:  python get_gmail_token.py

Then add to Render environment variables:
  GMAIL_CLIENT_ID      = <printed below>
  GMAIL_CLIENT_SECRET  = <printed below>
  GMAIL_REFRESH_TOKEN  = <printed below>
  NOTIFY_EMAIL         = pathikc129@gmail.com   (your Gmail, already set)
"""

import json
import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

SECRET_FILE = "client_secret.json"

if not os.path.exists(SECRET_FILE):
    print(f"ERROR: {SECRET_FILE} not found.")
    print("Download it from Google Cloud Console → APIs & Services → Credentials.")
    sys.exit(1)

with open(SECRET_FILE) as f:
    data = json.load(f)

creds = data.get("installed") or data.get("web")
CLIENT_ID     = creds["client_id"]
CLIENT_SECRET = creds["client_secret"]
REDIRECT_URI  = "http://localhost:8765"
SCOPE         = "https://www.googleapis.com/auth/gmail.send"

auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    + urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
    })
)

auth_code = None

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Done! You can close this tab.</h2>")

    def log_message(self, *args):
        pass  # suppress request logs

print("Opening browser for Google login...")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 8765), _Handler)
server.handle_request()

if not auth_code:
    print("ERROR: Did not receive authorisation code.")
    sys.exit(1)

# Exchange code for tokens
resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code":          auth_code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    },
)
resp.raise_for_status()
tokens = resp.json()

REFRESH_TOKEN = tokens.get("refresh_token")
if not REFRESH_TOKEN:
    print("ERROR: No refresh_token in response. Re-run with a fresh Google login "
          "(revoke app access at myaccount.google.com/permissions first).")
    sys.exit(1)

print("\n" + "=" * 60)
print("Add these to Render -> Environment Variables:")
print("=" * 60)
print(f"GMAIL_CLIENT_ID      = {CLIENT_ID}")
print(f"GMAIL_CLIENT_SECRET  = {CLIENT_SECRET}")
print(f"GMAIL_REFRESH_TOKEN  = {REFRESH_TOKEN}")
print("NOTIFY_EMAIL         = pathikc129@gmail.com")
print("=" * 60)
print("\nDone. You do NOT need to run this script again — the refresh token never expires.")
