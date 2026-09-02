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

# Main Discord update channel
UPDATE_CHANNEL_ID = 1504673300046151841

# Malaysia timezone (UTC+8)
MALAYSIA_TZ = timezone(timedelta(hours=8))


# ============================================================
# ANIMATOR ALIASES
# ============================================================

ANIMATOR_ALIASES = {
    "UCIOUP": ["Usop", "Yusof"],
    "Ralph": ["Syed"],
    "ilys": ["Iliyas"],
    "syahruldayan": ["Syahrulul"],
    ".gravillion": ["Jenggo"],
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
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        )
    )


# ============================================================
# CHECK MESSAGE LOCATION
# ============================================================

def is_valid_update_location(message):

    # Main update channel
    if message.channel.id == UPDATE_CHANNEL_ID:
        return True

    # Thread belonging to main update channel
    if isinstance(
        message.channel,
        discord.Thread
    ):

        if (
            message.channel.parent_id
            == UPDATE_CHANNEL_ID
        ):
            return True

    return False


# ============================================================
# SEND DATA TO GOOGLE SHEETS
# ============================================================

async def send_to_google_sheets(data):

    if not GOOGLE_SCRIPT_URL:

        print(
            "FAILED: GOOGLE_SCRIPT_URL is missing."
        )

        return "ERROR"

    try:

        import urllib.request

        payload = json.dumps(
            data
        ).encode("utf-8")

        request = urllib.request.Request(

            GOOGLE_SCRIPT_URL,

            data=payload,

            headers={
                "Content-Type":
                    "application/json"
            },

            method="POST"
        )

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            result = (
                response
                .read()
                .decode("utf-8")
                .strip()
            )

            print(
                "Google Sheets response:",
                result
            )

            # ------------------------------------------------
            # NEW UPDATE
            # ------------------------------------------------

            if result.upper() == "SUCCESS":

                print(
                    "SUCCESS: Update sent to Google Sheets!"
                )

                return "SUCCESS"

            # ------------------------------------------------
            # DUPLICATE
            # ------------------------------------------------

            if result.upper() == "DUPLICATE":

                print(
                    "DUPLICATE: Update already exists. Skipping."
                )

                return "DUPLICATE"

            # ------------------------------------------------
            # OTHER RESPONSE
            # ------------------------------------------------

            print(
                "WARNING: Unexpected Google Sheets response:",
                result
            )

            return "ERROR"

    except Exception as e:

        print(
            "ERROR sending to Google Sheets:"
        )

        print(e)

        return "ERROR"


# ============================================================
# CLEAN DISCORD TEXT
# ============================================================

def clean_discord_text(text):

    if not text:
        return ""

    # Remove bold
    text = text.replace(
        "**",
        ""
    )

    # Remove underline
    text = text.replace(
        "__",
        ""
    )

    # Remove code blocks
    text = text.replace(
        "```",
        ""
    )

    # Remove inline code
    text = text.replace(
        "`",
        ""
    )

    return text.strip()


# ============================================================
# CHECK IF MESSAGE IS AN ANIMATION UPDATE
# ============================================================

def is_animation_update(content):

    if not content:
        return False

    text = clean_discord_text(
        content
    )

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

    return bool(
        has_shot_task
        and has_status
    )


# ============================================================
# EXTRACT FIELD
# ============================================================

def get_field(
    text,
    field_name,
    next_fields=None
):

    if not text:
        return ""

    text = clean_discord_text(
        text
    )

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

    escaped_fields = []

    for field in next_fields:

        if (
            field.lower()
            != field_name.lower()
        ):

            escaped_fields.append(
                re.escape(field)
            )

    if escaped_fields:

        next_pattern = "|".join(
            escaped_fields
        )

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

        re.IGNORECASE |
        re.DOTALL
    )

    if not match:
        return ""

    value = match.group(1).strip()

    if value == "-":
        return ""

    return value


# ============================================================
# PARSE RECOVERY DATE
# ============================================================

def parse_recovery_date(date_text):

    if not date_text:
        return None

    date_text = date_text.strip()

    formats = [

        "%d/%m/%Y",
        "%d/%m/%y",

        "%d-%m-%Y",
        "%d-%m-%y",

        "%Y-%m-%d",

        "%d %B %Y",
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
# CONVERT TO MALAYSIA TIME
# ============================================================

def malaysia_datetime(dt):

    if dt.tzinfo is None:

        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        MALAYSIA_TZ
    )


# ============================================================
# CHECK ANIMATOR
# ============================================================

def message_matches_animator(
    message,
    requested_animator
):

    if not requested_animator:
        return True

    requested = (
        requested_animator
        .strip()
        .lower()
    )

    author_display = (

        getattr(
            message.author,
            "display_name",
            ""
        )
        or ""

    ).lower()

    author_username = (

        getattr(
            message.author,
            "name",
            ""
        )
        or ""

    ).lower()

    author_global = (

        getattr(
            message.author,
            "global_name",
            ""
        )
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

        names = [
            key
        ] + aliases

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
# CHECK MESSAGE DATE
# ============================================================

def message_matches_date(
    message,
    requested_date
):

    if not requested_date:
        return True

    message_time = malaysia_datetime(
        message.created_at
    )

    return (
        message_time.date()
        == requested_date
    )


# ============================================================
# PROCESS ONE MESSAGE
# ============================================================

async def process_message(
    message,
    source="LIVE"
):

    # Ignore bot messages
    if message.author.bot:
        return "IGNORED"

    # Check animation update
    if not is_animation_update(
        message.content
    ):

        return "IGNORED"

    print()
    print(
        "=" * 60
    )

    print(
        "ANIMATION UPDATE FOUND"
    )

    print(
        "=" * 60
    )

    print(
        "Source:",
        source
    )

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
    # TIME
    # --------------------------------------------------------

    message_time = malaysia_datetime(
        message.created_at
    )

    date_string = (
        message_time
        .strftime("%d/%m/%Y")
    )

    time_string = (
        message_time
        .strftime("%H:%M")
    )

    # --------------------------------------------------------
    # FIELDS
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

        progress_match = re.search(

            r"(\d+(?:\.\d+)?)",

            progress
        )

        if progress_match:

            progress = (
                progress_match
                .group(1)
            )

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
    # DATA
    # --------------------------------------------------------

    data = {

        "date":
            date_string,

        "time":
            time_string,

        "username":
            username,

        "task":
            shot_task,

        "status":
            status,

        "difficulty":
            difficulty,

        "progress":
            progress,

        "notes":
            notes,

        "message_id":
            str(message.id),

        "channel":
            getattr(
                message.channel,
                "name",
                ""
            )

    }

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    print()
    print(
        "EXTRACTED DATA"
    )

    print(
        "-" * 40
    )

    print(
        "Date:",
        data["date"]
    )

    print(
        "Time:",
        data["time"]
    )

    print(
        "Username:",
        data["username"]
    )

    print(
        "Shot/Task:",
        data["task"]
    )

    print(
        "Status:",
        data["status"]
    )

    print(
        "Difficulty:",
        data["difficulty"]
    )

    print(
        "Progress:",
        data["progress"]
    )

    print(
        "Notes:",
        data["notes"]
    )

    print(
        "Message ID:",
        data["message_id"]
    )

    print(
        "Channel:",
        data["channel"]
    )

    print(
        "-" * 40
    )

    # --------------------------------------------------------
    # SEND TO GOOGLE SHEETS
    # --------------------------------------------------------

    result = await send_to_google_sheets(
        data
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if result == "SUCCESS":

        print(
            "✅ NEW UPDATE ADDED"
        )

    elif result == "DUPLICATE":

        print(
            "🔄 DUPLICATE SKIPPED"
        )

    else:

        print(
            "❌ UPDATE FAILED"
        )

    return result


# ============================================================
# RECOVERY
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
        print(
            "=" * 70
        )

        print(
            "STARTING RECOVERY"
        )

        print(
            "=" * 70
        )

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
            "=" * 70
        )

        # ----------------------------------------------------
        # GET CHANNEL
        # ----------------------------------------------------

        channel = bot.get_channel(
            UPDATE_CHANNEL_ID
        )

        if not channel:

            print(
                "ERROR: Could not find update channel."
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
        duplicates_skipped = 0
        errors = 0

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
                    "🛑 RECOVERY STOP REQUESTED."
                )

                return

            main_messages_scanned += 1

            if message.author.bot:
                continue

            if not message_matches_date(
                message,
                requested_date
            ):
                continue

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

            result = await process_message(
                message,
                source="RECOVERY - MAIN CHANNEL"
            )

            if result == "SUCCESS":

                updates_sent += 1

            elif result == "DUPLICATE":

                duplicates_skipped += 1

            elif result == "ERROR":

                errors += 1

            await asyncio.sleep(
                0.05
            )

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

                threads[
                    thread.id
                ] = thread

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

                threads[
                    thread.id
                ] = thread

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
                    "🛑 RECOVERY STOP REQUESTED."
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
                            "🛑 RECOVERY STOP REQUESTED."
                        )

                        return

                    thread_messages_scanned += 1
                    thread_count += 1

                    if message.author.bot:
                        continue

                    if not message_matches_date(
                        message,
                        requested_date
                    ):
                        continue

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

                    result = await process_message(
                        message,
                        source=(
                            "RECOVERY - THREAD: "
                            + thread.name
                        )
                    )

                    if result == "SUCCESS":

                        updates_sent += 1

                    elif result == "DUPLICATE":

                        duplicates_skipped += 1

                    elif result == "ERROR":

                        errors += 1

                    await asyncio.sleep(
                        0.05
                    )

            except Exception as e:

                print(
                    "ERROR reading thread:",
                    thread.name
                )

                print(e)

                errors += 1

            print(
                "Messages scanned in thread:",
                thread_count
            )

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        print()
        print(
            "=" * 70
        )

        print(
            "RECOVERY COMPLETE"
        )

        print(
            "=" * 70
        )

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
            "New updates sent:",
            updates_sent
        )

        print(
            "Duplicates skipped:",
            duplicates_skipped
        )

        print(
            "Errors:",
            errors
        )

        print(
            "=" * 70
        )

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
    print(
        "=" * 60
    )

    print(
        "BOT IS READY"
    )

    print(
        "=" * 60
    )

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
        "Available commands:"
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
        "!recover 26/08/2026"
    )

    print(
        "!stoprecover"
    )

    print(
        "=" * 60
    )


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
    # IGNORE BOT
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
    # PROCESS COMMANDS
    # --------------------------------------------------------

    await bot.process_commands(
        message
    )

    # --------------------------------------------------------
    # CHECK LOCATION
    # --------------------------------------------------------

    if not is_valid_update_location(
        message
    ):

        print(
            "Ignored: not in update channel/thread."
        )

        return

    # --------------------------------------------------------
    # CHECK UPDATE
    # --------------------------------------------------------

    if not is_animation_update(
        message.content
    ):

        print(
            "Ignored: not an animation update."
        )

        return

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    await process_message(
        message,
        source="LIVE"
    )


# ============================================================
# !RECOVER
# ============================================================

@bot.command(
    name="recover"
)
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

            "⚠️ A recovery is already running.\n"
            "Use `!stoprecover` if you want to stop it."

        )

        return

    if not args:

        await ctx.send(

            "Please specify an animator or `all`.\n\n"

            "Examples:\n"

            "`!recover all`\n"

            "`!recover Zul`\n"

            "`!recover all 26/08/2026`\n"

            "`!recover Zul 26/08/2026`\n"

            "`!recover 26/08/2026`"

        )

        return

    requested_animator = None
    requested_date = None

    # --------------------------------------------------------
    # FIRST ARGUMENT
    # --------------------------------------------------------

    first_arg = args[0].strip()

    possible_date = parse_recovery_date(
        first_arg
    )

    # !recover 26/08/2026
    if possible_date:

        requested_animator = None
        requested_date = possible_date

    else:

        # !recover all
        if first_arg.lower() == "all":

            requested_animator = None

        # !recover Zul
        else:

            requested_animator = first_arg

        # ----------------------------------------------------
        # DATE ARGUMENT
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

                    "Try:\n"
                    "`26/08/2026`\n"
                    "`26/8/26`\n"
                    "`2026-08-26`\n"
                    "`26 August 2026`"

                )

                return

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    animator_text = (

        requested_animator
        if requested_animator
        else "ALL ANIMATORS"

    )

    date_text = (

        requested_date.strftime(
            "%d/%m/%Y"
        )

        if requested_date

        else "ALL DATES"

    )

    await ctx.send(

        "🔎 **Starting recovery...**\n\n"

        f"👤 Animator: **{animator_text}**\n"

        f"📅 Date: **{date_text}**\n\n"

        "The bot will skip messages that are "
        "already in Google Sheets. 👍"

    )

    # --------------------------------------------------------
    # RUN RECOVERY
    # --------------------------------------------------------

    await check_missed_messages(

        requested_animator=
            requested_animator,

        requested_date=
            requested_date

    )

    await ctx.send(

        "✅ **Recovery finished!**\n\n"

        "New messages were added, while "
        "existing message IDs were skipped."

    )


# ============================================================
# !STOPRECOVER
# ============================================================

@bot.command(
    name="stoprecover"
)
async def stop_recover_command(ctx):

    global recovery_stop_requested

    if not recovery_running:

        await ctx.send(

            "ℹ️ There is no recovery running right now."

        )

        return

    recovery_stop_requested = True

    await ctx.send(

        "🛑 Stop request received.\n"
        "The recovery will stop shortly."

    )


# ============================================================
# START FLASK
# ============================================================

flask_thread = Thread(
    target=run_flask,
    daemon=True
)

flask_thread.start()


# ============================================================
# START BOT
# ============================================================

print()
print(
    "Starting Animation Update Bot..."
)

bot.run(
    DISCORD_TOKEN
)
