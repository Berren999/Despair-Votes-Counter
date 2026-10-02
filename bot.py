import os
import discord
from discord.ext import commands, tasks
import sqlite3
import re
import datetime
import pytz

# -----------------------------
# MESSAGE SPLITTING HELPER
# -----------------------------
async def send_long_message(ctx, text):
    for i in range(0, len(text), 2000):
        await ctx.send(text[i:i+2000])

# -----------------------------
# INTENTS
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True

# -----------------------------
# CONFIG
# -----------------------------
# TOKEN NOW COMES FROM RENDER ENVIRONMENT VARIABLE
TOKEN = os.environ.get("DISCORD_TOKEN")

VOTE_CHANNEL_ID = 1480276444792754367      # voting-log
RESULTS_CHANNEL_ID = 1501255818274668696   # voting-results

bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# DATABASE SETUP
# -----------------------------
# Render runs your bot from /opt/render/project/src/
# Using a relative path keeps your DB next to bot.py
conn = sqlite3.connect("votes.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS votes (
    user TEXT PRIMARY KEY,
    total INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS last_week_votes (
    user TEXT PRIMARY KEY,
    total INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS monthly_votes (
    user TEXT PRIMARY KEY,
    total INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS last_month_votes (
    user TEXT PRIMARY KEY,
    total INTEGER DEFAULT 0
)
""")

conn.commit()

# -----------------------------
# USERNAME EXTRACTOR
# -----------------------------
def extract_username_from_message(message):
    if message.webhook_id:
        return message.author.name.strip()

    if message.content:
        match = re.match(r"([^ ]+)", message.content)
        if match:
            return match.group(1).strip()

    return None

# -----------------------------
# WEEK CALCULATIONS
# -----------------------------
def get_start_of_week():
    central = pytz.timezone("US/Central")
    now = datetime.datetime.now(central)

    days_since_monday = now.weekday()
    start_of_week = now - datetime.timedelta(days=days_since_monday)
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

    return start_of_week.astimezone(datetime.timezone.utc)

def get_previous_week_range():
    central = pytz.timezone("US/Central")
    now = datetime.datetime.now(central)

    days_since_monday = now.weekday()
    start_this_week = now - datetime.timedelta(days=days_since_monday)
    start_this_week = start_this_week.replace(hour=0, minute=0, second=0, microsecond=0)

    start_prev = start_this_week - datetime.timedelta(days=7)
    end_prev = start_this_week - datetime.timedelta(seconds=1)

    return (
        start_prev.astimezone(datetime.timezone.utc),
        end_prev.astimezone(datetime.timezone.utc)
    )

# -----------------------------
# MONTH CALCULATIONS
# -----------------------------
def get_start_of_month():
    central = pytz.timezone("US/Central")
    now = datetime.datetime.now(central)

    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_month.astimezone(datetime.timezone.utc)

def get_previous_month_range():
    central = pytz.timezone("US/Central")
    now = datetime.datetime.now(central)

    first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    last_month_end = first_this_month - datetime.timedelta(seconds=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return (
        last_month_start.astimezone(datetime.timezone.utc),
        last_month_end.astimezone(datetime.timezone.utc)
    )

# -----------------------------
# REBUILD CURRENT WEEK
# -----------------------------
async def rebuild_votes_from_history():
    channel = bot.get_channel(VOTE_CHANNEL_ID)

    cur.execute("DELETE FROM votes")
    conn.commit()

    start_of_week = get_start_of_week()

    async for msg in channel.history(limit=None, after=start_of_week):
        username = extract_username_from_message(msg)
        if not username:
            continue

        cur.execute("INSERT OR IGNORE INTO votes (user, total) VALUES (?, 0)", (username,))
        cur.execute("UPDATE votes SET total = total + 1 WHERE user = ?", (username,))

    conn.commit()

# -----------------------------
# REBUILD PREVIOUS WEEK
# -----------------------------
async def rebuild_last_week_from_history():
    channel = bot.get_channel(VOTE_CHANNEL_ID)

    cur.execute("DELETE FROM last_week_votes")
    conn.commit()

    start_prev, end_prev = get_previous_week_range()

    async for msg in channel.history(limit=None, after=start_prev, before=end_prev):
        username = extract_username_from_message(msg)
        if not username:
            continue

        cur.execute("INSERT OR IGNORE INTO last_week_votes (user, total) VALUES (?, 0)", (username,))
        cur.execute("UPDATE last_week_votes SET total = total + 1 WHERE user = ?", (username,))

    conn.commit()

# -----------------------------
# REBUILD CURRENT MONTH
# -----------------------------
async def rebuild_month_from_history():
    channel = bot.get_channel(VOTE_CHANNEL_ID)

    cur.execute("DELETE FROM monthly_votes")
    conn.commit()

    start_month = get_start_of_month()

    async for msg in channel.history(limit=None, after=start_month):
        username = extract_username_from_message(msg)
        if not username:
            continue

        cur.execute("INSERT OR IGNORE INTO monthly_votes (user, total) VALUES (?, 0)", (username,))
        cur.execute("UPDATE monthly_votes SET total = total + 1 WHERE user = ?", (username,))

    conn.commit()

# -----------------------------
# REBUILD PREVIOUS MONTH
# -----------------------------
async def rebuild_last_month_from_history():
    channel = bot.get_channel(VOTE_CHANNEL_ID)

    cur.execute("DELETE FROM last_month_votes")
    conn.commit()

    start_prev, end_prev = get_previous_month_range()

    async for msg in channel.history(limit=None, after=start_prev, before=end_prev):
        username = extract_username_from_message(msg)
        if not username:
            continue

        cur.execute("INSERT OR IGNORE INTO last_month_votes (user, total) VALUES (?, 0)", (username,))
        cur.execute("UPDATE last_month_votes SET total = total + 1 WHERE user = ?", (username,))

    conn.commit()

# -----------------------------
# on_message (LIVE COUNTING)
# -----------------------------
@bot.event
async def on_message(message):
    await bot.process_commands(message)

    # Ignore commands
    if message.content.startswith("!"):
        return

    # Only count messages from the voting channel
    if message.channel.id != VOTE_CHANNEL_ID:
        return
    
    if not message.webhook_id:
        return

    username = extract_username_from_message(message)
    if not username:
        return

    cur.execute("INSERT OR IGNORE INTO votes (user, total) VALUES (?, 0)", (username,))
    cur.execute("UPDATE votes SET total = total + 1 WHERE user = ?", (username,))

    cur.execute("INSERT OR IGNORE INTO monthly_votes (user, total) VALUES (?, 0)", (username,))
    cur.execute("UPDATE monthly_votes SET total = total + 1 WHERE user = ?", (username,))

# -----------------------------
# COMMANDS
# -----------------------------
@bot.command()
async def helpbot(ctx):
    msg = (
        "**Voting Bot Commands**\n"
        "`!helpbot` - Show this help message\n"
        "`!votes` - Show current week's vote totals\n"
        "`!lastweek` - Show last week's vote totals\n"
        "`!month` - Show current month's vote totals\n"
        "`!lastmonth` - Show last month's vote totals\n"
        "`!recount` - Rebuild this week's totals\n"
        "`!recountlastweek` - Rebuild last week's totals\n"
        "`!recountmonth` - Rebuild this month's totals\n"
        "`!recountlastmonth` - Rebuild last month's totals\n"
    )
    await ctx.send(msg)

@bot.command()
async def votes(ctx):
    cur.execute("SELECT user, total FROM votes ORDER BY total DESC")
    rows = cur.fetchall()

    if not rows:
        await ctx.send("No votes recorded yet.")
        return

    total_votes = sum(total for _, total in rows)

    msg = "**Current Week Vote Totals:**\n"
    for user, total in rows:
        msg += f"**{user}** — {total}\n"

    msg += f"\n**Total Votes This Week:** {total_votes}"

    await send_long_message(ctx, msg)

@bot.command()
async def lastweek(ctx):
    cur.execute("SELECT user, total FROM last_week_votes ORDER BY total DESC")
    rows = cur.fetchall()

    if not rows:
        await ctx.send("No data stored for last week yet.")
        return

    total_votes = sum(total for _, total in rows)

    msg = "**Last Week's Vote Totals:**\n"
    for user, total in rows:
        msg += f"**{user}** — {total}\n"

    msg += f"\n**Total Votes Last Week:** {total_votes}"

    await send_long_message(ctx, msg)

@bot.command()
async def month(ctx):
    cur.execute("SELECT user, total FROM monthly_votes ORDER BY total DESC")
    rows = cur.fetchall()

    if not rows:
        await ctx.send("No votes recorded this month yet.")
        return

    total_votes = sum(total for _, total in rows)

    msg = "**Current Month Vote Totals:**\n"
    for user, total in rows:
        msg += f"**{user}** — {total}\n"

    msg += f"\n**Total Votes This Month:** {total_votes}"

    await send_long_message(ctx, msg)

@bot.command()
async def lastmonth(ctx):
    cur.execute("SELECT user, total FROM last_month_votes ORDER BY total DESC")
    rows = cur.fetchall()

    if not rows:
        await ctx.send("No data stored for last month yet.")
        return

    total_votes = sum(total for _, total in rows)

    msg = "**Last Month's Vote Totals:**\n"
    for user, total in rows:
        msg += f"**{user}** — {total}\n"

    msg += f"\n**Total Votes Last Month:** {total_votes}"

    await send_long_message(ctx, msg)

@bot.command()
async def recount(ctx):
    await rebuild_votes_from_history()
    await ctx.send("Recount complete for THIS week.")

@bot.command()
async def recountlastweek(ctx):
    await rebuild_last_week_from_history()
    await ctx.send("Recount complete for LAST week.")

@bot.command()
async def recountmonth(ctx):
    await rebuild_month_from_history()
    await ctx.send("Recount complete for THIS month.")

@bot.command()
async def recountlastmonth(ctx):
    await rebuild_last_month_from_history()
    await ctx.send("Recount complete for LAST month.")

# -----------------------------
# WEEKLY TASK
# -----------------------------
@tasks.loop(hours=24)
async def weekly_results():
    now = datetime.datetime.now(pytz.timezone("US/Central"))
    if now.weekday() == 6 and now.hour == 18:
        channel = bot.get_channel(RESULTS_CHANNEL_ID)

        cur.execute("SELECT user, total FROM votes ORDER BY total DESC")
        rows = cur.fetchall()

        if rows:
            total_votes = sum(total for _, total in rows)

            msg = "**Weekly Vote Results:**\n"
            for user, total in rows:
                msg += f"**{user}** — {total}\n"

            msg += f"\n**Total Votes This Week:** {total_votes}"

            await send_long_message(channel, msg)
        else:
            await channel.send("No votes recorded this week.")

        cur.execute("DELETE FROM last_week_votes")
        for user, total in rows:
            cur.execute("INSERT INTO last_week_votes (user, total) VALUES (?, ?)", (user, total))
        conn.commit()

        cur.execute("DELETE FROM votes")
        conn.commit()

# -----------------------------
# MONTHLY TASK
# -----------------------------
@tasks.loop(hours=24)
async def monthly_results():
    now = datetime.datetime.now(pytz.timezone("US/Central"))
    if now.day == 1 and now.hour == 0:
        channel = bot.get_channel(RESULTS_CHANNEL_ID)

        cur.execute("SELECT user, total FROM monthly_votes ORDER BY total DESC")
        rows = cur.fetchall()

        if rows:
            total_votes = sum(total for _, total in rows)

            msg = "**Monthly Vote Results:**\n"
            for user, total in rows:
                msg += f"**{user}** — {total}\n"

            msg += f"\n**Total Votes This Month:** {total_votes}"

            await send_long_message(channel, msg)
        else:
            await channel.send("No votes recorded this month.")

        cur.execute("DELETE FROM last_month_votes")
        for user, total in rows:
            cur.execute("INSERT INTO last_month_votes (user, total) VALUES (?, ?)", (user, total))
        conn.commit()

        cur.execute("DELETE FROM monthly_votes")
        conn.commit()

# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    await rebuild_votes_from_history()
    await rebuild_month_from_history()
    weekly_results.start()
    monthly_results.start()

# -----------------------------
# RUN BOT
# -----------------------------
bot.run(TOKEN)
