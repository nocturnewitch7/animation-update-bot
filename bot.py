import os
import asyncio
import json
import re
from datetime import timezone, timedelta

import discord

from flask import Flask
from threading import Thread


# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

GOOGLE_SCRIPT_URL = os.getenv("https://script.google.com/macros/s/AKfycbwvM4ulLEEdt1oI2UWp5tQuGU9Ly6hZpQRkBe1pEreZccshIpiAvUPKUdu_SrwIuze4/exec")

# ============================================================
# IMPORTANT:
# This is the ID of the MAIN animation update channel.
# Animator threads underneath this channel are also accepted.
# ============================================================

UPDATE_CHANNEL_ID = 1504673300046151841


# ============================================================
# ANIMATOR NAME MAPPING
# ============================================================
#
# Used by !recover.
#
# The values are Discord DISPLAY NAMES.
#
# Example:
#
# !recover Usop
#
# The bot will look for messages from the display names
# listed under Usop.
#
# ============================================================

ANIMATOR_ALIASES = {

    "UCIOUP": [
        "Usop",
        "Yusof"
    ],

    "Ralph": [
        "Syed"
    ],

    "ilys": [
        "Iliyas"
    ],

    "syahruldayan": [
        "Syahrulul"
    ],

    ".gravillion": [
        "Jenggo"
    ],

    # Zul's Discord display name is simply "zul",
    # so no alias is required.
}


# ============================================================
# RECOVERY CONTROL
# ============================================================

recovery_running = False

stop_recovery = False


# ============================================================
# CHECK ENVIRONMENT VARIABLES
# ============================================================

if not DISCORD_TOKEN:

    print(
        "ERROR: DISCORD_TOKEN is missing."
    )


if not GOOGLE_SCRIPT_URL:

    print(
        "ERROR: GOOGLE_SCRIPT_URL is missing."
    )


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
# CHECK WHETHER CHANNEL IS VALID
# ============================================================
#
# A message is valid if it is:
#
# 1. In the main animation update channel
#
# OR
#
# 2. Inside a thread belonging to that channel
#
# This is the important fix for live animator updates.
#
# ============================================================

def is_valid_update_location(message):

    # --------------------------------------------------------
    # Main channel
    # --------------------------------------------------------

    if message.channel.id == UPDATE_CHANNEL_ID:

        return True


    # --------------------------------------------------------
    # Thread
    # --------------------------------------------------------

    if isinstance(
        message.channel,
        discord.Thread
    ):

        if message.channel.parent_id == UPDATE_CHANNEL_ID:

            return True


    return False


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

async def send_to_google_sheets(data):

    if not GOOGLE_SCRIPT_URL:

        print(
            "ERROR: GOOGLE_SCRIPT_URL is missing."
        )

        return False


    try:

        print(
            "DATA TO GOOGLE SHEETS:"
        )

        print(data)


        payload = json.dumps(
            data
        ).encode("utf-8")


        import urllib.request


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
# CLEAN DISCORD MESSAGE
# ============================================================
#
# Removes common Discord markdown.
#
# Allows:
#
# **Shot/Task:** SH001
#
# to be treated the same as:
#
# Shot/Task: SH001
#
# ============================================================

def clean_discord_text(text):

    if not text:

        return ""


    cleaned = text


    cleaned = cleaned.replace(
        "**",
        ""
    )


    cleaned = cleaned.replace(
        "__",
        ""
    )


    cleaned = cleaned.replace(
        "```",
        ""
    )


    return cleaned


# ============================================================
# CHECK WHETHER MESSAGE IS AN ANIMATION UPDATE
# ============================================================

def is_animation_update(message):

    if message.author.bot:

        return False


    text = clean_discord_text(
        message.content
    )


    # --------------------------------------------------------
    # Shot/Task is required
    # --------------------------------------------------------

    if not re.search(

        r"Shot\s*/\s*Task\s*:",

        text,

        flags=re.IGNORECASE

    ):

        return False


    # --------------------------------------------------------
    # Status is required
    # --------------------------------------------------------

    if not re.search(

        r"Status\s*:",

        text,

        flags=re.IGNORECASE

    ):

        return False


    return True


# ============================================================
# GET FIELD FROM MESSAGE
# ============================================================
#
# Handles fields on separate lines OR the same line.
#
# Example:
#
# Difficulty: - Progress %: 90%
#
# will correctly produce:
#
# Difficulty = -
# Progress = 90%
#
# ============================================================

def get_field(text, field_name):

    clean_text = clean_discord_text(
        text
    )


    pattern = (

        rf"{re.escape(field_name)}"

        rf"\s*:\s*"

        rf"(.*?)"

        rf"(?="

        rf"\s+(?:"

        rf"Shot\s*/\s*Task"

        rf"|Status"

        rf"|Difficulty"

        rf"|Progress\s*%"

        rf"|Notes"

        rf")"

        rf"\s*:"

        rf"|$)"

    )


    match = re.search(

        pattern,

        clean_text,

        flags=re.IGNORECASE | re.DOTALL

    )


    if match:

        return match.group(1).strip()


    return ""


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
    # Check location
    #
    # During recovery this isn't strictly necessary because
    # we already know where the message came from.
    #
    # For live messages it prevents unrelated channels from
    # being processed.
    # --------------------------------------------------------

    if not recovery:

        if not is_valid_update_location(message):

            return False


    # --------------------------------------------------------
    # Check animation update format
    # --------------------------------------------------------

    if not is_animation_update(message):

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
        f"Username: {message.author.name}"
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

    data["task"] = get_field(

        message.content,

        "Shot/Task"

    )


    data["status"] = get_field(

        message.content,

        "Status"

    )


    data["difficulty"] = get_field(

        message.content,

        "Difficulty"

    )


    data["progress"] = get_field(

        message.content,

        "Progress %"

    )


    data["notes"] = get_field(

        message.content,

        "Notes"

    )


    # --------------------------------------------------------
    # Logging extracted data
    # --------------------------------------------------------

    print("EXTRACTED DATA:")

    print(
        data
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
# CHECK WHETHER MESSAGE BELONGS TO REQUESTED ANIMATOR
# ============================================================

def message_matches_animator(
    message,
    animator
):

    requested = (

        animator.strip().lower()

    )


    actual_name = (

        message.author.display_name

        or ""

    ).strip().lower()


    # --------------------------------------------------------
    # Direct display-name match
    # --------------------------------------------------------

    if actual_name == requested:

        return True


    # --------------------------------------------------------
    # Check aliases
    # --------------------------------------------------------

    for real_name, aliases in ANIMATOR_ALIASES.items():

        if real_name.lower() != requested:

            continue


        for alias in aliases:

            if actual_name == alias.lower():

                return True


    return False


# ============================================================
# FULL CHANNEL RECOVERY
# ============================================================

async def check_missed_messages(
    requested_animator=None
):

    global recovery_running

    global stop_recovery


    recovery_running = True

    stop_recovery = False


    print("================================")

    print(
        "STARTING FULL CHANNEL RECOVERY"
    )


    if requested_animator:

        print(
            f"Animator filter: {requested_animator}"
        )

    else:

        print(
            "Animator filter: ALL"
        )


    print("================================")


    found_channel = False

    total_channel_messages = 0

    total_thread_messages = 0

    animation_updates = 0

    successful_updates = 0


    try:

        for guild in bot.guilds:

            if stop_recovery:

                break


            for channel in guild.text_channels:

                if stop_recovery:

                    break


                if channel.id != UPDATE_CHANNEL_ID:

                    continue


                found_channel = True


                print(
                    f"Found update channel: #{channel.name}"
                )


                try:

                    # ====================================================
                    # STEP 1 — READ MAIN CHANNEL
                    # ====================================================

                    print(
                        "Reading main channel history..."
                    )


                    async for message in channel.history(

                        limit=None,

                        oldest_first=True

                    ):

                        if stop_recovery:

                            break


                        total_channel_messages += 1


                        if message.author.bot:

                            continue


                        if requested_animator:

                            if not message_matches_animator(

                                message,

                                requested_animator

                            ):

                                continue


                        if not is_animation_update(message):

                            continue


                        animation_updates += 1


                        print("================================")


                        print(
                            f"RECOVERY UPDATE #{animation_updates}"
                        )


                        print(
                            f"Message ID: {message.id}"
                        )


                        print(
                            "Source: MAIN CHANNEL"
                        )


                        print(
                            f"User: {message.author.display_name}"
                        )


                        print("================================")


                        success = await process_message(

                            message,

                            recovery=True

                        )


                        if success:

                            successful_updates += 1


                        await asyncio.sleep(
                            0.2
                        )


                    # ====================================================
                    # STOP CHECK
                    # ====================================================

                    if stop_recovery:

                        break


                    # ====================================================
                    # STEP 2 — FIND ALL THREADS
                    # ====================================================

                    print("================================")

                    print(
                        "LOOKING FOR THREADS"
                    )

                    print("================================")


                    threads = []


                    # ----------------------------------------------------
                    # Active threads
                    # ----------------------------------------------------

                    active_threads = channel.threads


                    for thread in active_threads:

                        if thread not in threads:

                            threads.append(
                                thread
                            )


                    # ----------------------------------------------------
                    # Threads attached to channel messages
                    # ----------------------------------------------------

                    async for message in channel.history(

                        limit=None,

                        oldest_first=True

                    ):

                        if stop_recovery:

                            break


                        if message.thread:

                            if message.thread not in threads:

                                threads.append(
                                    message.thread
                                )


                    if stop_recovery:

                        break


                    print(
                        f"Found {len(threads)} thread(s)."
                    )


                    # ====================================================
                    # STEP 3 — READ EVERY THREAD
                    # ====================================================

                    for thread in threads:

                        if stop_recovery:

                            break


                        print("================================")


                        print(
                            f"READING THREAD: #{thread.name}"
                        )


                        print(
                            f"Thread ID: {thread.id}"
                        )


                        print("================================")


                        try:

                            async for message in thread.history(

                                limit=None,

                                oldest_first=True

                            ):

                                if stop_recovery:

                                    break


                                total_thread_messages += 1


                                if message.author.bot:

                                    continue


                                if requested_animator:

                                    if not message_matches_animator(

                                        message,

                                        requested_animator

                                    ):

                                        continue


                                if not is_animation_update(message):

                                    continue


                                animation_updates += 1


                                print("================================")


                                print(
                                    f"RECOVERY UPDATE #{animation_updates}"
                                )


                                print(
                                    f"Message ID: {message.id}"
                                )


                                print(
                                    f"Source: THREAD #{thread.name}"
                                )


                                print(
                                    f"User: {message.author.display_name}"
                                )


                                print("================================")


                                success = await process_message(

                                    message,

                                    recovery=True

                                )


                                if success:

                                    successful_updates += 1


                                await asyncio.sleep(
                                    0.2
                                )


                        except discord.Forbidden:

                            print(

                                f"WARNING: Cannot read thread "
                                f"#{thread.name}"

                            )


                        except Exception as error:

                            print(

                                f"ERROR reading thread "
                                f"#{thread.name}: {error}"

                            )


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


    finally:

        recovery_running = False


        print("================================")


        if stop_recovery:

            print(
                "RECOVERY STOPPED"
            )

        else:

            print(
                "FULL CHANNEL RECOVERY COMPLETE"
            )


        print("================================")


        if requested_animator:

            print(
                f"Animator: {requested_animator}"
            )

        else:

            print(
                "Animator: ALL"
            )


        print(
            f"Main channel messages scanned: "
            f"{total_channel_messages}"
        )


        print(
            f"Thread messages scanned: "
            f"{total_thread_messages}"
        )


        print(
            f"Animation updates found: "
            f"{animation_updates}"
        )


        print(
            f"Updates sent successfully: "
            f"{successful_updates}"
        )


        print("================================")


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
        "Commands:"
    )


    print(
        "!recover all"
    )


    print(
        "!recover <animator>"
    )


    print(
        "!stoprecover"
    )


    print("================================")


# ============================================================
# HANDLE DISCORD MESSAGES
# ============================================================

@bot.event
async def on_message(message):

    global stop_recovery


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
    # Check whether this is a valid location.
    #
    # IMPORTANT:
    # This now accepts both the main channel and its threads.
    # --------------------------------------------------------

    if not is_valid_update_location(message):

        print(
            "IGNORED: Message is outside the update channel "
            "and its threads."
        )

        return


    # ========================================================
    # !stoprecover
    # ========================================================

    if message.content.strip().lower() == "!stoprecover":

        if not recovery_running:

            print(
                "STOP REQUEST RECEIVED, "
                "but no recovery is currently running."
            )


            await message.channel.send(

                "There is no recovery currently running."

            )


            return


        print("================================")


        print(
            "STOP RECOVERY COMMAND RECEIVED"
        )


        print(
            f"Requested by: "
            f"{message.author.display_name}"
        )


        print("================================")


        stop_recovery = True


        await message.channel.send(

            "🛑 Recovery stop requested. "
            "The bot will stop after the current message."

        )


        return


    # ========================================================
    # !recover
    # ========================================================

    command = message.content.strip()


    if command.lower().startswith("!recover"):


        # ----------------------------------------------------
        # Prevent two recoveries at the same time
        # ----------------------------------------------------

        if recovery_running:

            await message.channel.send(

                "⚠️ A recovery is already running. "
                "Use `!stoprecover` first if you want to stop it."

            )


            return


        # ----------------------------------------------------
        # Split command
        # ----------------------------------------------------

        parts = command.split(
            maxsplit=1
        )


        # ----------------------------------------------------
        # !recover without a name
        # ----------------------------------------------------

        if len(parts) == 1:

            await message.channel.send(

                "Please specify an animator or use `all`.\n\n"

                "Examples:\n"

                "`!recover all`\n"

                "`!recover Zul`"

            )


            return


        # ----------------------------------------------------
        # Get requested animator
        # ----------------------------------------------------

        requested_animator = parts[1].strip()


        # ----------------------------------------------------
        # !recover all
        # ----------------------------------------------------

        if requested_animator.lower() == "all":

            requested_animator = None


        print("================================")


        print(
            "RECOVERY COMMAND RECEIVED"
        )


        print(
            f"Requested by: "
            f"{message.author.display_name}"
        )


        if requested_animator:

            print(
                f"Animator: {requested_animator}"
            )

        else:

            print(
                "Animator: ALL"
            )


        print("================================")


        # ----------------------------------------------------
        # Start recovery
        # ----------------------------------------------------

        await message.channel.send(

            "🔎 Starting recovery"

            + (

                f" for **{requested_animator}**..."

                if requested_animator

                else " for **everyone**..."

            )

        )


        await check_missed_messages(

            requested_animator

        )


        # ----------------------------------------------------
        # Recovery finished
        # ----------------------------------------------------

        if stop_recovery:

            await message.channel.send(

                "🛑 Recovery stopped."

            )

        else:

            await message.channel.send(

                "✅ Recovery complete."

            )


        return


    # ========================================================
    # PROCESS NORMAL LIVE UPDATE
    # ========================================================

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
