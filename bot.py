import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import Flask, request, jsonify, abort

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import nacl.signing
import nacl.exceptions

# ---------- Config & Logging ----------
logging.basicConfig(level=logging.INFO)
TZ = os.getenv("TIMEZONE", "Asia/Kolkata")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Daily Logs")

DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")            # Bot token
DISCORD_APP_ID = os.environ.get("DISCORD_APP_ID")          # Application ID
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")      # Guild (server) ID for instant commands

if not DISCORD_PUBLIC_KEY:
    raise ValueError("DISCORD_PUBLIC_KEY env var is required")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN env var is required")
if not DISCORD_APP_ID:
    raise ValueError("DISCORD_APP_ID env var is required")
if not DISCORD_GUILD_ID:
    logging.warning("DISCORD_GUILD_ID not set — commands will register globally and may take up to 1 hour.")

# ---------- Google Sheets ----------
creds_json_str = os.environ.get("GOOGLE_CREDS_JSON")
if not creds_json_str:
    raise ValueError("GOOGLE_CREDS_JSON environment variable not set.")

creds_dict = json.loads(creds_json_str)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gclient = gspread.authorize(creds)
sheet = gclient.open(SHEET_NAME).sheet1  # first worksheet

def now_ist():
    return datetime.now(ZoneInfo(TZ))

def log_to_sheet(name, action, task_title="", desc=""):
    dt = now_ist()
    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M:%S")
    row = [date_str, str(name), str(action), time_str, str(task_title), str(desc)]
    sheet.append_row(row)

# ---------- Discord (slash commands) ----------
COMMANDS = [
    {
        "name": "start",
        "description": "Log start of work"
    },
    {
        "name": "end",
        "description": "Log end of work"
    },
    {
        "name": "work_done",
        "description": "Log a completed task",
        "options": [
            {
                "name": "task_title",
                "description": "Title of the task",
                "type": 3,  # STRING
                "required": True
            },
            {
                "name": "desc",
                "description": "Description (optional)",
                "type": 3,  # STRING
                "required": False
            }
        ]
    }
]

def register_commands():
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }
    if DISCORD_GUILD_ID:
        url = f"https://discord.com/api/v10/applications/{DISCORD_APP_ID}/guilds/{DISCORD_GUILD_ID}/commands"
    else:
        url = f"https://discord.com/api/v10/applications/{DISCORD_APP_ID}/commands"

    # Bulk overwrite for idempotency
    resp = requests.put(url, headers=headers, json=COMMANDS)
    if resp.status_code in (200, 201):
        logging.info("Slash commands registered successfully.")
    else:
        logging.error(f"Failed to register commands: {resp.status_code} {resp.text}")

def verify_discord_request(req):
    try:
        signature = req.headers["X-Signature-Ed25519"]
        timestamp = req.headers["X-Signature-Timestamp"]
        body = req.data.decode("utf-8")
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
        return True
    except Exception as e:
        logging.warning(f"Signature verification failed: {e}")
        return False

def extract_user_display(data: dict) -> str:
    member = data.get("member") or {}
    user = member.get("user") or data.get("user") or {}
    # Prefer server nickname, then global_name, then username
    return member.get("nick") or user.get("global_name") or user.get("username") or "Unknown"

def option_value(options, name, default=""):
    if not options:
        return default
    for o in options:
        if o.get("name") == name:
            return o.get("value", default)
    return default

# ---------- Flask app ----------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "✅ Bot server is running!", 200

@app.route("/interactions", methods=["POST"])
def interactions():
    if not verify_discord_request(request):
        abort(401, "Invalid request signature")

    data = request.json or {}
    # 1 = PING
    if data.get("type") == 1:
        return jsonify({"type": 1})

    # 2 = APPLICATION_COMMAND
    if data.get("type") == 2:
        cmd = data.get("data", {}).get("name")
        user_display = extract_user_display(data)

        try:
            if cmd == "start":
                log_to_sheet(user_display, "Start")
                return jsonify({"type": 4, "data": {"content": f"🟢 Start logged for **{user_display}**"}})

            if cmd == "end":
                log_to_sheet(user_display, "End")
                return jsonify({"type": 4, "data": {"content": f"🔴 End logged for **{user_display}**"}})

            if cmd == "work_done":
                options = data.get("data", {}).get("options", [])
                task_title = option_value(options, "task_title", "")
                desc = option_value(options, "desc", "")
                log_to_sheet(user_display, "Task", task_title, desc)
                return jsonify({"type": 4, "data": {"content": f"✅ Task logged: **{task_title}** — {desc}"}})

            return jsonify({"type": 4, "data": {"content": "⚠ Unknown command"}})
        except Exception as e:
            logging.exception("Error handling command")
            return jsonify({"type": 4, "data": {"content": f"❌ Error: {e}"}})

    # Fallback
    return jsonify({"type": 4, "data": {"content": "Unsupported interaction type"}})

if __name__ == "__main__":
    register_commands()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
