import os
import threading
import json
import urllib.request
from datetime import timezone, timedelta

from flask import Flask
import discord


# ============================================================
# GOOGLE SHEETS
# ============================================================

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbwvM4ulLEEdt1oI2UWp5tQuGU9Ly6hZpQRkBe1pEreZccshIpiAvUPKUdu_SrwIuze4/exec"


# ============================================================
# RENDER WEB SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animation Update Bot is running!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web, daemon=True).start()


# ============================================================
# DISCORD BOT
# ============================================================

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


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

def send_to_google_sheet(data):

    payload = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        GOOGLE_SHEET_URL,
        data=payload,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:

        result = response.read().decode("utf-8")

        print(f"Google Sheets response: {result}")


# ============================================================
# READ DISCORD MESSAGES
# ============================================================

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


    # --------------------------------------------------------
    # Only process animation update messages
    # --------------------------------------------------------

    if "Shot/Task:" not in text or "Status:" not in text:

        print("Not an animation update. Ignoring.")

        return


    # Remove Discord bold formatting
    text = text.replace("**", "")


    # --------------------------------------------------------
    # GET DATE AND TIME FROM DISCORD
    # --------------------------------------------------------

    malaysia_timezone = timezone(timedelta(hours=8))

    message_time = message.created_at.replace(
        tzinfo=timezone.utc
    ).astimezone(malaysia_timezone)


    date_value = message_time.strftime("%d/%m/%Y")

    time_value = message_time.strftime("%I:%M %p")


    # --------------------------------------------------------
    # CREATE DATA RECORD
    # --------------------------------------------------------

    data = {

        "date": date_value,

        "time": time_value,

        "username": message.author.display_name,

        "task": "",

        "status": "",

        "difficulty": "",

        "progress": "",

        "notes": ""

    }


    # --------------------------------------------------------
    # READ EACH LINE
    # --------------------------------------------------------

    for line in text.splitlines():

        line = line.strip()


        if line.startswith("Shot/Task:"):

            data["task"] = line.replace(
                "Shot/Task:",
                "",
                1
            ).strip()


        elif line.startswith("Status:"):

            data["status"] = line.replace(
                "Status:",
                "",
                1
            ).strip()


        elif line.startswith("Difficulty:"):

            data["difficulty"] = line.replace(
                "Difficulty:",
                "",
                1
            ).strip()


        elif line.startswith("Progress %:"):

            data["progress"] = line.replace(
                "Progress %:",
                "",
                1
            ).strip()


        elif line.startswith("Notes:"):

            data["notes"] = line.replace(
                "Notes:",
                "",
                1
            ).strip()


    # --------------------------------------------------------
    # SHOW DATA IN RENDER LOG
    # --------------------------------------------------------

    print("DATA TO GOOGLE SHEETS:")
    print(data)


    # --------------------------------------------------------
    # SEND TO GOOGLE SHEETS
    # --------------------------------------------------------

    try:

        send_to_google_sheet(data)

        print("SUCCESS: Update sent to Google Sheets!")


    except Exception as error:

        print(
            f"ERROR sending to Google Sheets: {error}"
        )


# ============================================================
# START BOT
# ============================================================

BOT_TOKEN = os.environ.get("DISCORD_TOKEN")


if not BOT_TOKEN:

    raise ValueError(
        "DISCORD_TOKEN is not set!"
    )


bot.run(BOT_TOKEN)
