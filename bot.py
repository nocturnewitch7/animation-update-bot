import os
import threading
import json
import urllib.request
import re

# -----------------------------
# Google Sheets Web App URL
# -----------------------------
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbwvM4ulLEEdt1oI2UWp5tQuGU9Ly6hZpQRkBe1pEreZccshIpiAvUPKUdu_SrwIuze4/exec"

# -----------------------------
# Keep Render Web Service alive
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Animation Update Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# -----------------------------
# Discord Bot
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

print("BOT SCRIPT STARTED")


@bot.event
async def on_ready():
    print("================================")
    print(f"Logged in as {bot.user}")
    print(f"Connected to {len(bot.guilds)} server(s)")
    print("================================")


def send_to_google_sheet(data):
    payload = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        GOOGLE_SHEET_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        result = response.read().decode("utf-8")
        print(f"Google Sheets response: {result}")


@bot.event
async def on_message(message):
    # Ignore messages sent by bots
    if message.author.bot:
        return

    print("================================")
    print("NEW DISCORD MESSAGE")
    print(f"User: {message.author}")
    print(f"Channel: {message.channel}")
    print(f"Message: {message.content}")
    print("================================")

    text = message.content

    # Only process messages containing our update fields
    if "Shot/Task:" not in text or "Status:" not in text:
        print("Not an animation update. Ignoring.")
        return

    # Remove Discord's ** bold formatting
    text = text.replace("**", "")

    data = {
        "date": "",
        "username": str(message.author),
        "task": "",
        "status": "",
        "difficulty": "",
        "progress": "",
        "notes": ""
    }

    # Read each field
 for line in text.splitlines():
    line = line.strip()

    if line.startswith("Date:"):
        data["date"] = line.replace("Date:", "", 1).strip()

    elif re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}$", line):
        data["date"] = line

        elif line.startswith("Shot/Task:"):
            data["task"] = line.replace("Shot/Task:", "", 1).strip()

        elif line.startswith("Status:"):
            data["status"] = line.replace("Status:", "", 1).strip()

        elif line.startswith("Difficulty:"):
            data["difficulty"] = line.replace("Difficulty:", "", 1).strip()

        elif line.startswith("Progress %:"):
            data["progress"] = line.replace("Progress %:", "", 1).strip()

        elif line.startswith("Notes:"):
            data["notes"] = line.replace("Notes:", "", 1).strip()

    print("DATA TO GOOGLE SHEETS:")
    print(data)

    try:
        send_to_google_sheet(data)
        print("SUCCESS: Update sent to Google Sheets!")
    except Exception as error:
        print(f"ERROR sending to Google Sheets: {error}")


# -----------------------------
# Start Discord Bot
# -----------------------------
BOT_TOKEN = os.environ.get("DISCORD_TOKEN")

if not BOT_TOKEN:
    raise ValueError("DISCORD_TOKEN is not set!")

bot.run(BOT_TOKEN)
