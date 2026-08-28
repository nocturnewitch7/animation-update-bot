import os
import asyncio
import json
from datetime import timezone, timedelta

import discord

from flask import Flask
from threading import Thread


# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")

# Actual update channel ID
UPDATE_CHANNEL_ID = 1504740541148172339


# ============================================================
# CHECK ENVIRONMENT VARIABLES
# ============================================================

if not DISCORD_TOKEN:

    print("ERROR: DISCORD_TOKEN is missing.")


if not GOOGLE_SCRIPT_URL:

    print("ERROR: GOOGLE_SCRIPT_URL is missing.")


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.default()

intents.message_content = True


# ============================================================
# CREATE BOT
# ============================================================

bot = discord.Client(
    intents=intents
)


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():

    return "Animation Update Bot is running."


def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        )
    )


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

async def send_to_google_sheets(data):

    if not GOOGLE_SCRIPT_URL:

        print(
            "ERROR: GOOGLE_SCRIPT_URL is missing."
        )

        return False


    import urllib.request
    import json


    try:

        print(
            "DATA TO GOOGLE SHEETS:"
        )

        print(data)


        payload = json.dumps(
            data
        ).encode("utf-8")


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

                return response.read().decode(
                    "utf-8"
                )


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
# PROCESS ONE DISCORD MESSAGE
# ============================================================

async def process_message(
    message,
    recovery=False
):

    # --------------------------------------------------------
    # Ignore bots
    # --------------------------------------------------------

    if message.author.bot:

        return False


    # --------------------------------------------------------
    # Ignore messages that aren't animation updates
    # --------------------------------------------------------

    text = message.content


    if "Shot/Task:" not in text:

        return False


    if "Status:" not in text:

        return False


    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    print("================================")


    if recovery:

        print(
            "PROCESSING RECOVERED MESSAGE"
        )

    else:

        print(
            "PROCESSING LIVE ANIMATION UPDATE"
        )


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
    # Malaysia time
    # --------------------------------------------------------

    malaysia_timezone = timezone(
        timedelta(hours=8)
    )


    message_time = (

        message.created_at

        .replace(
            tzinfo=timezone.utc
        )

        .astimezone(
            malaysia_timezone
        )

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
    # Read fields
    # --------------------------------------------------------

    for line in text.splitlines():

        line = line.strip()


        if line.startswith("Shot/Task:"):

            data["task"] = (

                line.split(
                    "Shot/Task:",
                    1
                )[1].strip()

            )


        elif line.startswith("Status:"):

            data["status"] = (

                line.split(
                    "Status:",
                    1
                )[1].strip()

            )


        elif line.startswith("Difficulty:"):

            data["difficulty"] = (

                line.split(
                    "Difficulty:",
                    1
                )[1].strip()

            )


        elif line.startswith("Progress %:"):

            data["progress"] = (

                line.split(
                    "Progress %:",
                    1
                )[1].strip()

            )


        elif line.startswith("Notes:"):

            data["notes"] = (

                line.split(
                    "Notes:",
                    1
                )[1].strip()

            )


    # --------------------------------------------------------
    # Send to Google Sheets
    # --------------------------------------------------------

    success = await send_to_google_sheets(
        data
    )


    if success:

        if recovery:

            print(
                "RECOVERY: Update sent to Google Sheets."
            )

        else:

            print(
                "LIVE UPDATE: Update sent to Google Sheets."
            )


        return True


    print(
        "FAILED: Update was NOT sent to Google Sheets."
    )


    return False


# ============================================================
# FULL CHANNEL RECOVERY
# ============================================================

async def check_missed_messages():

    print("================================")

    print(
        "STARTING FULL CHANNEL RECOVERY"
    )

    print("================================")


    found_channel = False

    total_messages = 0

    animation_updates = 0

    successful_updates = 0


    # --------------------------------------------------------
    # Find correct channel
    # --------------------------------------------------------

    for guild in bot.guilds:

        for channel in guild.text_channels:


            if channel.id != UPDATE_CHANNEL_ID:

                continue


            found_channel = True


            print(
                f"Found update channel: #{channel.name}"
            )


            try:

                print(
                    "Reading ENTIRE channel history..."
                )


                # ------------------------------------------------
                # Read every message from oldest to newest
                # ------------------------------------------------

                async for message in channel.history(

                    limit=None,

                    oldest_first=True

                ):

                    total_messages += 1


                    # --------------------------------------------
                    # Ignore bots
                    # --------------------------------------------

                    if message.author.bot:

                        continue


                    # --------------------------------------------
                    # Ignore normal chat
                    # --------------------------------------------

                    if "Shot/Task:" not in message.content:

                        continue


                    if "Status:" not in message.content:

                        continue


                    animation_updates += 1


                    print("================================")

                    print(
                        f"RECOVERY UPDATE #{animation_updates}"
                    )

                    print(
                        f"Message ID: {message.id}"
                    )

                    print("================================")


                    success = await process_message(

                        message,

                        recovery=True

                    )


                    if success:

                        successful_updates += 1


                    # Give the API a small breather

                    await asyncio.sleep(
                        0.2
                    )


                print("================================")

                print(
                    f"Total messages scanned: "
                    f"{total_messages}"
                )

                print(
                    f"Animation updates found: "
                    f"{animation_updates}"
                )

                print(
                    f"Updates sent successfully: "
                    f"{successful_updates}"
                )

                print(
                    "FULL CHANNEL RECOVERY COMPLETE"
                )

                print("================================")


            except discord.Forbidden:

                print(
                    "ERROR: Bot does not have permission "
                    "to read message history."
                )


            except Exception as error:

                print(
                    f"ERROR reading channel history: "
                    f"{error}"
                )


    if not found_channel:

        print(
            "WARNING: Could not find the update channel."
        )


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

    print(
        "Bot is ready."
    )

    print(
        "Use !recover in the update channel "
        "to scan the entire channel history."
    )

    print("================================")


# ============================================================
# HANDLE DISCORD MESSAGES
# ============================================================

@bot.event
async def on_message(message):

    # --------------------------------------------------------
    # Ignore bot messages
    # --------------------------------------------------------

    if message.author.bot:

        return


    # --------------------------------------------------------
    # Show that a live message was received
    # --------------------------------------------------------

    print(
        "LIVE MESSAGE EVENT RECEIVED"
    )


    print(
        f"CHANNEL ID: {message.channel.id}"
    )


    print(
        f"CHANNEL NAME: {message.channel.name}"
    )


    # --------------------------------------------------------
    # !recover command
    # --------------------------------------------------------

    if message.content.strip().lower() == "!recover":


        if message.channel.id != UPDATE_CHANNEL_ID:

            return


        print("================================")

        print(
            "RECOVERY COMMAND RECEIVED"
        )

        print(
            f"Requested by: "
            f"{message.author.display_name}"
        )

        print("================================")


        await check_missed_messages()


        return


    # --------------------------------------------------------
    # Ignore other channels
    # --------------------------------------------------------

    if message.channel.id != UPDATE_CHANNEL_ID:

        return


    # --------------------------------------------------------
    # Process normal live update
    # --------------------------------------------------------

    await process_message(

        message,

        recovery=False

    )


# ============================================================
# START FLASK SERVER
# ============================================================

flask_thread = Thread(

    target=run_flask,

    daemon=True

)

flask_thread.start()


# ============================================================
# START DISCORD BOT
# ============================================================

print("================================")

print(
    "BOT SCRIPT STARTED"
)

print("================================")


if not DISCORD_TOKEN:

    print(
        "ERROR: Cannot start bot because "
        "DISCORD_TOKEN is missing."
    )

else:

    bot.run(
        DISCORD_TOKEN
    )
