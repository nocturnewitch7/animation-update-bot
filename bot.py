import os
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands

from flask import Flask
from threading import Thread


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")


if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN is missing.")

if not GOOGLE_SCRIPT_URL:
    print("ERROR: GOOGLE_SCRIPT_URL is missing.")


# ============================================================
# CONFIGURATION
# ============================================================

# Main Discord channel where the animator threads live
UPDATE_CHANNEL_ID = 1504673300046151841

# Malaysia timezone
MALAYSIA_TZ = timezone(timedelta(hours=8))


# ============================================================
# ANIMATOR ALIASES
# ============================================================

ANIMATOR_ALIASES = {
    "UCIOUP": ["Usop", "Yusof"],
    "Ralph": ["Syed"],
    "ilys": ["Iliyas"],
    "ilys2050": ["Iliyas"],
    "syahruldayan": ["Syahrulul"],
    ".gravillion": ["Jenggo"],
    "spiderman4210": ["Zaqwan"],
    "ralph4572": ["Syed"],
    "rory_07": ["Rory"],
}


# ============================================================
# RECOVERY CONTROL
# ============================================================

recovery_running = False
recovery_stop_requested = False


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# FLASK SERVER FOR RENDER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Animation Update Bot is running!"


def run_flask():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )


# ============================================================
# CHECK IF MESSAGE IS IN THE CORRECT LOCATION
# ============================================================

def is_valid_update_location(message):
    """
    Accept messages from:

    1. The main update channel
    2. Threads directly under the main update channel
    """

    # Main channel
    if message.channel.id == UPDATE_CHANNEL_ID:
        return True

    # Thread under main channel
    if isinstance(message.channel, discord.Thread):

        if message.channel.parent_id == UPDATE_CHANNEL_ID:
            return True

    return False


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

async def send_to_google_sheets(data):

    if not GOOGLE_SCRIPT_URL:
        print("FAILED: GOOGLE_SCRIPT_URL is missing.")
        return False

    try:

        import urllib.request

        payload = json.dumps(data).encode("utf-8")

        request = urllib.request.Request(
            GOOGLE_SCRIPT_URL,
            data=payload,
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=30) as response:

            result = response.read().decode("utf-8")

            print("Google Sheets response:", result)

            if "SUCCESS" in result.upper():
                print("SUCCESS: Update sent to Google Sheets!")
                return True

            print("WARNING: Google Sheets returned:", result)

            return False

    except Exception as e:

        print("ERROR sending to Google Sheets:")
        print(e)

        return False


# ============================================================
# CLEAN DISCORD MESSAGE
# ============================================================

def clean_discord_text(text):

    if not text:
        return ""

    # Remove Discord bold / underline formatting
    text = text.replace("**", "")
    text = text.replace("__", "")

    # Remove code blocks
    text = text.replace("```", "")

    # Remove inline code formatting
    text = text.replace("`", "")

    return text.strip()


# ============================================================
# CHECK IF MESSAGE LOOKS LIKE AN ANIMATION UPDATE
# ============================================================

def is_animation_update(content):

    if not content:
        return False

    text = clean_discord_text(content)

    has_shot_task = re.search(
        r"\bShot\s*/?\s*Task\s*:",
        text,
        re.IGNORECASE
    )

    has_status = re.search(
        r"\bStatus\s*:",
        text,
        re.IGNORECASE
    )

    return bool(has_shot_task and has_status)


# ============================================================
# EXTRACT A FIELD FROM THE MESSAGE
# ============================================================

def get_field(text, field_name, next_fields=None):

    if not text:
        return ""

    text = clean_discord_text(text)

    if next_fields is None:
        next_fields = [
            "Date",
            "Time",
            "Username",
            "Shot/Task",
            "Status",
            "Difficulty",
            "Progress %",
            "Notes"
        ]

    # Escape field names for regex
    escaped_next_fields = [
        re.escape(field)
        for field in next_fields
        if field.lower() != field_name.lower()
    ]

    if escaped_next_fields:

        next_pattern = "|".join(escaped_next_fields)

        pattern = (
            r"\b"
            + re.escape(field_name)
            + r"\s*:\s*"
            r"(.*?)"
            r"(?=\s+(?:"
            + next_pattern
            + r")\s*:|$)"
        )

    else:

        pattern = (
            r"\b"
            + re.escape(field_name)
            + r"\s*:\s*(.*)$"
        )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE | re.DOTALL
    )

    if not match:
        return ""

    value = match.group(1).strip()

    # Remove leading "-" if the user wrote:
    # Difficulty: - Progress %: 90%
    if value == "-":
        return ""

    return value


# ============================================================
# PARSE DATE FROM COMMAND
# ============================================================

def parse_recovery_date(date_text):

    if not date_text:
        return None

    date_text = date_text.strip()

    formats = [

        # 26/08/2026
        "%d/%m/%Y",

        # 26/8/26
        "%d/%m/%y",

        # 26-08-2026
        "%d-%m-%Y",

        # 26-8-26
        "%d-%m-%y",

        # 2026-08-26
        "%Y-%m-%d",

        # 26 August 2026
        "%d %B %Y",

        # 26 Aug 2026
        "%d %b %Y",
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                date_text,
                fmt
            ).date()

        except ValueError:
            pass

    return None


# ============================================================
# CONVERT DISCORD TIME TO MALAYSIA TIME
# ============================================================

def malaysia_datetime(dt):

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(MALAYSIA_TZ)


# ============================================================
# CHECK WHETHER MESSAGE MATCHES REQUESTED ANIMATOR
# ============================================================

def message_matches_animator(message, requested_animator):

    if not requested_animator:
        return True

    requested = requested_animator.strip().lower()

    author_display = (
        getattr(message.author, "display_name", "")
        or ""
    ).lower()

    author_username = (
        getattr(message.author, "name", "")
        or ""
    ).lower()

    author_global = (
        getattr(message.author, "global_name", "")
        or ""
    ).lower()

    # Direct match
    if requested in [
        author_display,
        author_username,
        author_global
    ]:
        return True

    # Alias match
    for key, aliases in ANIMATOR_ALIASES.items():

        names = [key] + aliases

        names_lower = [
            name.lower()
            for name in names
        ]

        if requested in names_lower:

            for name in names_lower:

                if name in [
                    author_display,
                    author_username,
                    author_global
                ]:
                    return True

    return False


# ============================================================
# CHECK WHETHER MESSAGE MATCHES REQUESTED DATE
# ============================================================

def message_matches_date(message, requested_date):

    if not requested_date:
        return True

    message_time = malaysia_datetime(
        message.created_at
    )

    message_date = message_time.date()

    return message_date == requested_date


# ============================================================
# PROCESS ONE MESSAGE
# ============================================================

async def process_message(message, source="LIVE"):

    if message.author.bot:
        return False

    if not is_animation_update(message.content):
        return False

    print()
    print("=" * 60)
    print("ANIMATION UPDATE FOUND")
    print("=" * 60)

    print("Source:", source)

    print(
        "Author display name:",
        getattr(
            message.author,
            "display_name",
            ""
        )
    )

    print(
        "Author username:",
        getattr(
            message.author,
            "name",
            ""
        )
    )

    print(
        "Channel:",
        getattr(
            message.channel,
            "name",
            ""
        )
    )

    print(
        "Message ID:",
        message.id
    )

    # --------------------------------------------------------
    # MESSAGE TIME
    # --------------------------------------------------------

    message_time = malaysia_datetime(
        message.created_at
    )

    date_string = message_time.strftime(
        "%d/%m/%Y"
    )

    time_string = message_time.strftime(
        "%H:%M"
    )

    # --------------------------------------------------------
    # EXTRACT FIELDS
    # --------------------------------------------------------

    shot_task = get_field(
        message.content,
        "Shot/Task"
    )

    status = get_field(
        message.content,
        "Status"
    )

    difficulty = get_field(
        message.content,
        "Difficulty"
    )

    progress = get_field(
        message.content,
        "Progress %"
    )

    notes = get_field(
        message.content,
        "Notes"
    )

    # --------------------------------------------------------
    # CLEAN PROGRESS
    # --------------------------------------------------------

    if progress:

        progress = progress.strip()

        # Keep just the number if possible
        progress_match = re.search(
            r"(\d+(?:\.\d+)?)",
            progress
        )

        if progress_match:
            progress = progress_match.group(1)

    # --------------------------------------------------------
    # USERNAME
    # --------------------------------------------------------

    username = getattr(
        message.author,
        "display_name",
        ""
    )

    if not username:

        username = getattr(
            message.author,
            "name",
            ""
        )

    # --------------------------------------------------------
    # DATA TO GOOGLE SHEETS
    # --------------------------------------------------------

    data = {

        "date": date_string,

        "time": time_string,

        "username": username,

        "task": shot_task,

        "status": status,

        "difficulty": difficulty,

        "progress": progress,

        "notes": notes,

        # Useful later for duplicate protection
        "message_id": str(message.id),

        # Discord channel/thread name
        "channel": getattr(
            message.channel,
            "name",
            ""
        ),
    }

    # --------------------------------------------------------
    # DEBUG OUTPUT
    # --------------------------------------------------------

    print()
    print("EXTRACTED DATA")
    print("-" * 40)

    print("Date:", data["date"])
    print("Time:", data["time"])
    print("Username:", data["username"])
    print("Shot/Task:", data["task"])
    print("Status:", data["status"])
    print("Difficulty:", data["difficulty"])
    print("Progress:", data["progress"])
    print("Notes:", data["notes"])
    print("Message ID:", data["message_id"])
    print("Channel:", data["channel"])

    print("-" * 40)

    # --------------------------------------------------------
    # SEND TO GOOGLE SHEETS
    # --------------------------------------------------------

    success = await send_to_google_sheets(
        data
    )

    if success:
        print("SUCCESS: Update processed.")
    else:
        print("FAILED: Update was NOT sent to Google Sheets.")

    return success


# ============================================================
# RECOVERY FUNCTION
# ============================================================

async def check_missed_messages(
    requested_animator=None,
    requested_date=None
):

    global recovery_running
    global recovery_stop_requested

    if recovery_running:

        print(
            "A recovery is already running."
        )

        return

    recovery_running = True
    recovery_stop_requested = False

    try:

        print()
        print("=" * 70)
        print("STARTING RECOVERY")
        print("=" * 70)

        if requested_animator:
            print(
                "Animator:",
                requested_animator
            )
        else:
            print(
                "Animator: ALL"
            )

        if requested_date:
            print(
                "Date:",
                requested_date.strftime(
                    "%d/%m/%Y"
                )
            )
        else:
            print(
                "Date: ALL"
            )

        print("=" * 70)

        # ----------------------------------------------------
        # GET MAIN UPDATE CHANNEL
        # ----------------------------------------------------

        channel = bot.get_channel(
            UPDATE_CHANNEL_ID
        )

        if not channel:

            print(
                "Could not find update channel."
            )

            return

        print(
            "Found update channel:",
            channel.name
        )

        # ----------------------------------------------------
        # COUNTERS
        # ----------------------------------------------------

        main_messages_scanned = 0
        thread_messages_scanned = 0

        updates_found = 0
        updates_sent = 0

        # ----------------------------------------------------
        # MAIN CHANNEL
        # ----------------------------------------------------

        print()
        print(
            "Reading MAIN CHANNEL history..."
        )

        async for message in channel.history(
            limit=None,
            oldest_first=True
        ):

            if recovery_stop_requested:

                print(
                    "RECOVERY STOP REQUESTED."
                )

                return

            main_messages_scanned += 1

            # Don't process bots
            if message.author.bot:
                continue

            # Date filter
            if not message_matches_date(
                message,
                requested_date
            ):
                continue

            # Animator filter
            if not message_matches_animator(
                message,
                requested_animator
            ):
                continue

            if not is_animation_update(
                message.content
            ):
                continue

            updates_found += 1

            success = await process_message(
                message,
                source="RECOVERY - MAIN CHANNEL"
            )

            if success:
                updates_sent += 1

            # Give Discord a tiny break
            await asyncio.sleep(0.05)

        print()
        print(
            "Main channel messages scanned:",
            main_messages_scanned
        )

        # ----------------------------------------------------
        # FIND THREADS
        # ----------------------------------------------------

        print()
        print(
            "Finding threads..."
        )

        threads = {}

        # Active threads
        try:

            for thread in channel.threads:

                threads[thread.id] = thread

        except Exception as e:

            print(
                "Error getting active threads:",
                e
            )

        # Archived threads
        try:

            async for thread in channel.archived_threads(
                limit=None
            ):

                threads[thread.id] = thread

        except Exception as e:

            print(
                "Error getting archived threads:",
                e
            )

        print(
            "Total threads found:",
            len(threads)
        )

        # ----------------------------------------------------
        # READ THREADS
        # ----------------------------------------------------

        for thread in threads.values():

            if recovery_stop_requested:

                print(
                    "RECOVERY STOP REQUESTED."
                )

                return

            print()
            print(
                "-" * 60
            )

            print(
                "Reading thread:",
                thread.name
            )

            print(
                "Thread ID:",
                thread.id
            )

            thread_count = 0

            try:

                async for message in thread.history(
                    limit=None,
                    oldest_first=True
                ):

                    if recovery_stop_requested:

                        print(
                            "RECOVERY STOP REQUESTED."
                        )

                        return

                    thread_messages_scanned += 1
                    thread_count += 1

                    # Don't process bots
                    if message.author.bot:
                        continue

                    # Date filter
                    if not message_matches_date(
                        message,
                        requested_date
                    ):
                        continue

                    # Animator filter
                    if not message_matches_animator(
                        message,
                        requested_animator
                    ):
                        continue

                    # Animation update check
                    if not is_animation_update(
                        message.content
                    ):
                        continue

                    updates_found += 1

                    success = await process_message(
                        message,
                        source=(
                            "RECOVERY - THREAD: "
                            + thread.name
                        )
                    )

                    if success:
                        updates_sent += 1

                    await asyncio.sleep(0.05)

            except Exception as e:

                print(
                    "ERROR reading thread:",
                    thread.name
                )

                print(e)

            print(
                "Messages scanned in thread:",
                thread_count
            )

        # ----------------------------------------------------
        # FINAL SUMMARY
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("RECOVERY COMPLETE")
        print("=" * 70)

        print(
            "Animator:",
            requested_animator
            if requested_animator
            else "ALL"
        )

        print(
            "Date:",
            requested_date.strftime(
                "%d/%m/%Y"
            )
            if requested_date
            else "ALL"
        )

        print(
            "Main channel messages scanned:",
            main_messages_scanned
        )

        print(
            "Thread messages scanned:",
            thread_messages_scanned
        )

        print(
            "Animation updates found:",
            updates_found
        )

        print(
            "Updates sent successfully:",
            updates_sent
        )

        print("=" * 70)

    except Exception as e:

        print()
        print(
            "RECOVERY ERROR:"
        )

        print(e)

    finally:

        recovery_running = False
        recovery_stop_requested = False


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print()
    print("=" * 60)
    print("BOT IS READY")
    print("=" * 60)

    print(
        "Logged in as:",
        bot.user
    )

    print(
        "Bot ID:",
        bot.user.id
    )

    print(
        "Connected to",
        len(bot.guilds),
        "server(s)"
    )

    print(
        "Update Channel ID:",
        UPDATE_CHANNEL_ID
    )

    channel = bot.get_channel(
        UPDATE_CHANNEL_ID
    )

    if channel:

        print(
            "Update channel found:",
            channel.name
        )

    else:

        print(
            "WARNING: Update channel NOT found."
        )

    print()
    print(
        "Commands:"
    )

    print(
        "!recover all"
    )

    print(
        "!recover Zul"
    )

    print(
        "!recover all 26/08/2026"
    )

    print(
        "!recover Zul 26/08/2026"
    )

    print(
        "!stoprecover"
    )

    print("=" * 60)


# ============================================================
# LIVE MESSAGE EVENT
# ============================================================

@bot.event
async def on_message(message):

    print()
    print(
        "LIVE MESSAGE EVENT RECEIVED"
    )

    print(
        "Author:",
        getattr(
            message.author,
            "display_name",
            ""
        )
    )

    print(
        "Channel ID:",
        message.channel.id
    )

    print(
        "Channel Name:",
        getattr(
            message.channel,
            "name",
            ""
        )
    )

    # --------------------------------------------------------
    # Ignore bots
    # --------------------------------------------------------

    if message.author.bot:

        print(
            "Ignored: message is from a bot."
        )

        await bot.process_commands(
            message
        )

        return

    # --------------------------------------------------------
    # Allow commands from anywhere
    # --------------------------------------------------------

    await bot.process_commands(
        message
    )

    # --------------------------------------------------------
    # Check channel / thread
    # --------------------------------------------------------

    if not is_valid_update_location(
        message
    ):

        print(
            "Ignored: not in update channel/thread."
        )

        return

    # --------------------------------------------------------
    # Check whether it looks like an update
    # --------------------------------------------------------

    if not is_animation_update(
        message.content
    ):

        print(
            "Ignored: not an animation update."
        )

        return

    # --------------------------------------------------------
    # Process update
    # --------------------------------------------------------

    await process_message(
        message,
        source="LIVE"
    )


# ============================================================
# !RECOVER COMMAND
# ============================================================

@bot.command(name="recover")
async def recover_command(
    ctx,
    *args
):

    """
    Examples:

    !recover all

    !recover Zul

    !recover all 26/08/2026

    !recover Zul 26/08/2026

    !recover 26/08/2026
    """

    global recovery_running

    if recovery_running:

        await ctx.send(
            "⚠️ A recovery is already running. "
            "Use `!stoprecover` first if you want to stop it."
        )

        return

    if not args:

        await ctx.send(
            "Please specify an animator or `all`.\n\n"
            "Examples:\n"
            "`!recover all`\n"
            "`!recover Zul`\n"
            "`!recover all 26/08/2026`\n"
            "`!recover Zul 26/08/2026`"
        )

        return

    requested_animator = None
    requested_date = None

    # --------------------------------------------------------
    # FIRST ARGUMENT
    # --------------------------------------------------------

    first_arg = args[0].strip()

    # If first argument is a date,
    # assume user wants ALL animators
    possible_date = parse_recovery_date(
        first_arg
    )

    if possible_date:

        requested_animator = None
        requested_date = possible_date

    else:

        if first_arg.lower() == "all":

            requested_animator = None

        else:

            requested_animator = first_arg

        # ----------------------------------------------------
        # SECOND ARGUMENT = DATE
        # ----------------------------------------------------

        if len(args) >= 2:

            date_text = " ".join(
                args[1:]
            )

            requested_date = parse_recovery_date(
                date_text
            )

            if not requested_date:

                await ctx.send(
                    "❌ I couldn't understand that date.\n\n"
                    "Try one of these:\n"
                    "`26/08/2026`\n"
                    "`26/8/26`\n"
                    "`2026-08-26`\n"
                    "`26 August 2026`"
                )

                return

    # --------------------------------------------------------
    # START RECOVERY
    # --------------------------------------------------------

    if requested_animator:

        animator_text = requested_animator

    else:

        animator_text = "ALL ANIMATORS"

    if requested_date:

        date_text = requested_date.strftime(
            "%d/%m/%Y"
        )

        await ctx.send(
            "🔎 Starting recovery...\n"
            f"👤 Animator: **{animator_text}**\n"
            f"📅 Date: **{date_text}**\n\n"
            "This may take a while."
        )

    else:

        await ctx.send(
            "🔎 Starting recovery...\n"
            f"👤 Animator: **{animator_text}**\n"
            "📅 Date: **ALL DATES**\n\n"
            "This may take a while."
        )

    await check_missed_messages(
        requested_animator=requested_animator,
        requested_date=requested_date
    )

    await ctx.send(
        "✅ Recovery finished.\n"
        "Check the Render logs for the detailed summary."
    )


# ============================================================
# !STOPRECOVER COMMAND
# ============================================================

@bot.command(name="stoprecover")
async def stop_recover_command(ctx):

    global recovery_stop_requested

    if not recovery_running:

        await ctx.send(
            "ℹ️ There is no recovery running right now."
        )

        return

    recovery_stop_requested = True

    await ctx.send(
        "🛑 Stop request received. "
        "The recovery will stop shortly."
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

print()
print("Starting Animation Update Bot...")

bot.run(
    DISCORD_TOKEN
)
