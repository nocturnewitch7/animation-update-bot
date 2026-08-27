import os
import re
import asyncio
import threading
from datetime import datetime, timezone, timedelta

import discord
from flask import Flask


# ============================================================
# SETTINGS
# ============================================================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

GOOGLE_SCRIPT_URL = os.environ.get("GOOGLE_SCRIPT_URL")

UPDATE_CHANNEL_NAME = "🗓️waunimators_daily_log"
UPDATE_CHANNEL_ID = 1504673300046151841

# How far back the recovery system looks.
# 24 hours = 24
RECOVERY_HOURS = 24


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.default()

intents.message_content = True

bot = discord.Client(
    intents=intents
)


# ============================================================
# FLASK SERVER
# Keeps Render service alive
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():

    return "Animation Update Bot is running."


def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )


# ============================================================
# TIMEZONE
# Malaysia = UTC+8
# ============================================================

MALAYSIA_TIMEZONE = timezone(
    timedelta(hours=8)
)


# ============================================================
# DUPLICATE PROTECTION
# ============================================================

processed_message_ids = set()


# ============================================================
# PARSE FIELD
# ============================================================

def get_field(text, field_name):

    pattern = rf"^{re.escape(field_name)}\s*:\s*(.*)$"

    match = re.search(
        pattern,
        text,
        re.MULTILINE | re.IGNORECASE
    )

    if match:

        return match.group(1).strip()

    return ""


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

async def send_to_google_sheets(data):

    if not GOOGLE_SCRIPT_URL:

        print("ERROR: GOOGLE_SCRIPT_URL is missing.")

        return False


    import urllib.request
    import urllib.parse
    import json


    try:

        payload = json.dumps(data).encode("utf-8")


        request = urllib.request.Request(

            GOOGLE_SCRIPT_URL,

            data=payload,

            headers={
                "Content-Type": "application/json"
            },

            method="POST"
        )


        loop = asyncio.get_running_loop()


        def send_request():

            with urllib.request.urlopen(
                request,
                timeout=30
            ) as response:

                return response.read().decode("utf-8")


        result = await loop.run_in_executor(
            None,
            send_request
        )


        print(
            f"Google Sheets response: {result}"
        )


        return True


    except Exception as error:

        print(
            f"ERROR sending to Google Sheets: {error}"
        )

        return False


# ============================================================
# PROCESS A DISCORD MESSAGE
# ============================================================

async def process_message(message, recovery=False):

    # --------------------------------------------------------
    # Ignore bots
    # --------------------------------------------------------

    if message.author.bot:

        return


    # --------------------------------------------------------
    # Duplicate protection
    # --------------------------------------------------------

    message_id = str(message.id)


    if message_id in processed_message_ids:

        print(
            f"SKIPPING DUPLICATE MESSAGE: {message_id}"
        )

        return


    # --------------------------------------------------------
    # Get message text
    # --------------------------------------------------------

    text = message.content


    # --------------------------------------------------------
    # Ignore messages that are not animation updates
    # --------------------------------------------------------

    if "Shot/Task:" not in text:

        return


    if "Status:" not in text:

        return


    # --------------------------------------------------------
    # Mark as processed
    # --------------------------------------------------------

    processed_message_ids.add(message_id)


    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    print("================================")

    if recovery:

        print("RECOVERED DISCORD MESSAGE")

    else:

        print("NEW DISCORD MESSAGE")


    print(
        f"Message ID: {message.id}"
    )

    print(
        f"User: {message.author.display_name}"
    )

    print(
        f"Channel: {message.channel.name}"
    )

    print(
        f"Message: {message.content}"
    )

    print("================================")


    # --------------------------------------------------------
    # Convert Discord time to Malaysia time
    # --------------------------------------------------------

    message_time = (
        message.created_at
        .replace(tzinfo=timezone.utc)
        .astimezone(MALAYSIA_TIMEZONE)
    )


    date_value = message_time.strftime(
        "%d/%m/%Y"
    )


    time_value = message_time.strftime(
        "%I:%M %p"
    )


    # --------------------------------------------------------
    # Extract fields
    # --------------------------------------------------------

    task = get_field(
        text,
        "Shot/Task"
    )


    status = get_field(
        text,
        "Status"
    )


    difficulty = get_field(
        text,
        "Difficulty"
    )


    progress = get_field(
        text,
        "Progress %"
    )


    notes = get_field(
        text,
        "Notes"
    )


    # --------------------------------------------------------
    # Create data
    # --------------------------------------------------------

    data = {

        "date": date_value,

        "time": time_value,

        "username": message.author.display_name,

        "task": task,

        "status": status,

        "difficulty": difficulty,

        "progress": progress,

        "notes": notes,

        "message_id": message_id
    }


    # --------------------------------------------------------
    # Show data
    # --------------------------------------------------------

    print("DATA TO GOOGLE SHEETS:")

    print(data)

    print("================================")


    # --------------------------------------------------------
    # Send to Google Sheets
    # --------------------------------------------------------

    success = await send_to_google_sheets(
        data
    )


    if success:

        print(
            "SUCCESS: Update sent to Google Sheets!"
        )

    else:

        print(
            "FAILED: Update was NOT sent to Google Sheets."
        )


    print("================================")


# ============================================================
# RECOVER MISSED MESSAGES
# ============================================================

async def check_missed_messages():

    print("================================")

    print("CHECKING FOR MISSED MESSAGES")

    print(
        f"Recovery window: LAST {RECOVERY_HOURS} HOURS"
    )

    print("================================")


    found_channel = False


    # --------------------------------------------------------
    # Calculate recovery cutoff
    # --------------------------------------------------------

    now_utc = datetime.now(
        timezone.utc
    )


    cutoff_time = (
        now_utc -
        timedelta(hours=RECOVERY_HOURS)
    )


    # --------------------------------------------------------
    # Search every server
    # --------------------------------------------------------

    for guild in bot.guilds:

        for channel in guild.text_channels:

            if channel.name != UPDATE_CHANNEL_NAME:

                continue


            found_channel = True


            print(
                f"Found update channel: #{channel.name}"
            )


            print(
                f"Looking for messages after: "
                f"{cutoff_time}"
            )


            try:

                messages = []


                # ------------------------------------------------
                # Read recent history
                # ------------------------------------------------

                async for message in channel.history(
                    limit=200
                ):

                    # Discord gives newest first.
                    # Once we reach a message older
                    # than our recovery window,
                    # we can stop.

                    if message.created_at < cutoff_time:

                        break


                    messages.append(
                        message
                    )


                # ------------------------------------------------
                # Oldest first
                # ------------------------------------------------

                messages.reverse()


                print(
                    f"Found {len(messages)} messages "
                    f"within recovery window."
                )


                # ------------------------------------------------
                # Process messages
                # ------------------------------------------------

                for message in messages:

                    await process_message(
                        message,
                        recovery=True
                    )


            except discord.Forbidden:

                print(
                    "ERROR: Bot does not have permission "
                    "to read message history."
                )


            except Exception as error:

                print(
                    f"ERROR reading channel history: {error}"
                )


    if not found_channel:

        print(
            f"WARNING: Could not find "
            f"#{UPDATE_CHANNEL_NAME}"
        )


    print("================================")

    print("MISSED MESSAGE CHECK COMPLETE")

    print("================================")


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print("================================")

    print(
        f"Logged in as {bot.user}"
    )

    print(
        f"Connected to {len(bot.guilds)} server(s)"
    )

    print("================================")


    # --------------------------------------------------------
    # Recover messages
    # --------------------------------------------------------

    await check_missed_messages()


# ============================================================
# LIVE DISCORD MESSAGES
# ============================================================

@bot.event
async def on_message(message):

    print("LIVE MESSAGE EVENT RECEIVED")
    
    print(f"CHANNEL ID: {message.channel.id}")
    print(f"CHANNEL NAME: {message.channel.name}")

    if message.channel.id != UPDATE_CHANNEL_ID:
        return

    await process_message(
        message,
        recovery=False
    )
# ============================================================
# START BOT
# ============================================================

print("================================")

print("BOT SCRIPT STARTED")

print("================================")


# ------------------------------------------------------------
# Start Flask in background
# ------------------------------------------------------------

flask_thread = threading.Thread(
    target=run_flask,
    daemon=True
)

flask_thread.start()


# ------------------------------------------------------------
# Start Discord bot
# ------------------------------------------------------------

if not DISCORD_TOKEN:

    print(
        "ERROR: DISCORD_TOKEN environment variable is missing."
    )

else:

    bot.run(
        DISCORD_TOKEN
    )
