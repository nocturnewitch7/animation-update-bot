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
# DISCORD CHANNEL
# ============================================================

UPDATE_CHANNEL_NAME = "🗓️waunimators_daily_log"


# ============================================================
# HOW MANY RECENT MESSAGES TO CHECK
# ============================================================

MESSAGES_TO_CHECK = 300


# ============================================================
# RENDER WEB SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animation Update Bot is running!"


def run_web():

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


threading.Thread(
    target=run_web,
    daemon=True
).start()


# ============================================================
# DISCORD BOT
# ============================================================

intents = discord.Intents.default()

intents.message_content = True

intents.guilds = True

intents.messages = True


bot = discord.Client(
    intents=intents
)


print("BOT SCRIPT STARTED")


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


    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        result = response.read().decode("utf-8")

        print(
            f"Google Sheets response: {result}"
        )

        return result


# ============================================================
# PROCESS A DISCORD MESSAGE
# ============================================================

async def process_message(message):

    # --------------------------------------------------------
    # Ignore bots
    # --------------------------------------------------------

    if message.author.bot:

        return


    # --------------------------------------------------------
    # Ignore messages that are not animation updates
    # --------------------------------------------------------

    text = message.content


    if "Shot/Task:" not in text:

        return


    if "Status:" not in text:

        return


    print("================================")

    print("PROCESSING ANIMATION UPDATE")

    print(
        f"Message ID: {message.id}"
    )

    print(
        f"User: {message.author.display_name}"
    )

    print(
        f"Message: {message.content}"
    )

    print("================================")


    # --------------------------------------------------------
    # Convert Discord time to Malaysia time
    # --------------------------------------------------------

    malaysia_timezone = timezone(
        timedelta(hours=8)
    )


    message_time = (
        message.created_at
        .replace(tzinfo=timezone.utc)
        .astimezone(malaysia_timezone)
    )


    date_value = message_time.strftime(
        "%d/%m/%Y"
    )


    time_value = message_time.strftime(
        "%I:%M %p"
    )


    # --------------------------------------------------------
    # Create data
    # --------------------------------------------------------

    data = {

        "date": date_value,

        "time": time_value,

        "username": message.author.display_name,

        "task": "",

        "status": "",

        "difficulty": "",

        "progress": "",

        "notes": "",

        "message_id": str(message.id)

    }


    # --------------------------------------------------------
    # Remove Discord bold formatting
    # --------------------------------------------------------

    text = text.replace(
        "**",
        ""
    )


    # --------------------------------------------------------
    # Read each line
    # --------------------------------------------------------

    for line in text.splitlines():

        line = line.strip()


        if line.startswith(
            "Shot/Task:"
        ):

            data["task"] = line.replace(
                "Shot/Task:",
                "",
                1
            ).strip()


        elif line.startswith(
            "Status:"
        ):

            data["status"] = line.replace(
                "Status:",
                "",
                1
            ).strip()


        elif line.startswith(
            "Difficulty:"
        ):

            data["difficulty"] = line.replace(
                "Difficulty:",
                "",
                1
            ).strip()


        elif line.startswith(
            "Progress %:"
        ):

            data["progress"] = line.replace(
                "Progress %:",
                "",
                1
            ).strip()


        elif line.startswith(
            "Notes:"
        ):

            data["notes"] = line.replace(
                "Notes:",
                "",
                1
            ).strip()


    # --------------------------------------------------------
    # Send to Google Sheets
    # --------------------------------------------------------

    try:

        result = send_to_google_sheet(
            data
        )


        if result == "DUPLICATE":

            print(
                "SKIPPED: Message already exists in Google Sheets."
            )


        else:

            print(
                "SUCCESS: Update sent to Google Sheets!"
            )


    except Exception as error:

        print(
            f"ERROR sending to Google Sheets: {error}"
        )


# ============================================================
# CHECK MISSED MESSAGES
# ============================================================

async def check_missed_messages():

    print("================================")

    print("CHECKING FOR MISSED MESSAGES")

    print("================================")


    found_channel = False


    for guild in bot.guilds:

        for channel in guild.text_channels:

            if channel.name != UPDATE_CHANNEL_NAME:

                continue


            found_channel = True


            print(
                f"Found update channel: #{channel.name}"
            )


            try:

                messages = []


                async for message in channel.history(
                    limit=MESSAGES_TO_CHECK
                ):

                    messages.append(
                        message
                    )


                # Discord gives newest first.
                # Reverse so we process oldest first.

                messages.reverse()


                print(
                    f"Checking {len(messages)} recent messages..."
                )


                for message in messages:

                    await process_message(
                        message
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
            f"WARNING: Could not find #{UPDATE_CHANNEL_NAME}"
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


    # Check recent messages

    await check_missed_messages()


# ============================================================
# LIVE MESSAGE LISTENER
# ============================================================

@bot.event
async def on_message(message):

    # Ignore bots

    if message.author.bot:

        return


    # Only monitor the specified channel

    if not hasattr(
        message.channel,
        "name"
    ):

        return


    if message.channel.name != UPDATE_CHANNEL_NAME:

        return


    # Process the new message

    await process_message(
        message
    )


# ============================================================
# START BOT
# ============================================================

BOT_TOKEN = os.environ.get(
    "DISCORD_TOKEN"
)


if not BOT_TOKEN:

    raise ValueError(
        "DISCORD_TOKEN is not set!"
    )


bot.run(
    BOT_TOKEN
)
