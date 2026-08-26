import os
import threading
from flask import Flask
import discord

# -----------------------------
# Keep the Render web service alive
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Animation Update Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

# -----------------------------
# Discord Bot
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print("================================")
    print(f"BOT ONLINE: {bot.user}")
    print("================================")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    print("----- NEW MESSAGE -----")
    print(f"User: {message.author}")
    print(f"Channel: {message.channel}")
    print(message.content)
    print("-----------------------")

BOT_TOKEN = os.environ.get("DISCORD_TOKEN")

if not BOT_TOKEN:
    raise ValueError("DISCORD_TOKEN is not set!")

bot.run(BOT_TOKEN)
