import discord
from discord.ext import commands
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

# --- Google Sheets setup using Environment Variables ---

# Get the credentials from an environment variable
# We will set this variable in Render later
creds_json_str = os.environ.get("GOOGLE_CREDS_JSON")
if not creds_json_str:
    raise ValueError("GOOGLE_CREDS_JSON environment variable not set.")

# Convert the JSON string from the environment variable into a Python dictionary
creds_dict = json.loads(creds_json_str)

# Authorize with the credentials dictionary
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Daily Logs").sheet1  # your sheet name

# --- Discord setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="#", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is ready. Logged in as {bot.user}")

def log_to_sheet(name, action, task_title="", desc=""):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    # Make sure all values are strings to avoid API errors
    row_to_append = [str(val) for val in [date_str, name, action, time_str, task_title, desc]]
    sheet.append_row(row_to_append)

@bot.command()
async def Start(ctx):
    log_to_sheet(ctx.author.display_name, "Start")
    await ctx.send(f"🟢 Start logged for {ctx.author.display_name}")

@bot.command()
async def End(ctx):
    log_to_sheet(ctx.author.display_name, "End")
    await ctx.send(f"🔴 End logged for {ctx.author.display_name}")

@bot.command(name="work_done")
async def work_done(ctx, task_title: str, *, desc: str = ""):
    log_to_sheet(ctx.author.display_name, "Task", task_title, desc)
    await ctx.send(f"✅ Task logged: {task_title} — {desc}")

# --- Run the bot using the token from Environment Variables ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable not set.")

bot.run(DISCORD_TOKEN)
