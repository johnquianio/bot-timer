import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import pytz
import re
from typing import Dict, List, Optional, Tuple
import aiosqlite
import os
from tabulate import tabulate

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# Boss data
BOSS_DATA = [
    {"name": "Venatus", "fixed_time": "10 hrs", "armor": "TBD",
        "level": 60, "location": "Corrupted Basin"},
    {"name": "Viorent", "fixed_time": "10 hrs", "armor": "TBD",
        "level": 65, "location": "Crescent Lake"},
    {"name": "Ego", "fixed_time": "21 hrs", "armor": "TBD",
        "level": 70, "location": "Ulan Canyon"},
    {"name": "Clementis", "fixed_time": "Mon 11:30 / Thu 19:00",
        "armor": "TBD", "level": 70, "location": "Corrupted Basin"},
    {"name": "Livera", "fixed_time": "24 hrs", "armor": "TBD",
        "level": 75, "location": "Protector's Ruins"},
    {"name": "Araneo", "fixed_time": "24 hrs", "armor": "TBD",
        "level": 75, "location": "Lower Tomb of Tyriosa 1F"},
    {"name": "Undomiel", "fixed_time": "24 hrs", "armor": "TBD",
        "level": 80, "location": "Secret Laboratory"},
    {"name": "Saphirus", "fixed_time": "Sun 17:00 / Tue 11:30",
        "armor": "TBD", "level": 80, "location": "Crescent Lake"},
    {"name": "Neutro", "fixed_time": "Tue 19:00 / Thu 11:30",
        "armor": "TBD", "level": 80, "location": "Desert of the Screaming"},
    {"name": "Lady Dalia", "fixed_time": "18 hrs",
        "armor": "TBD", "level": 85, "location": "Twilight Hill"},
    {"name": "Aquleus", "fixed_time": "29 hrs", "armor": "TBD",
        "level": 85, "location": "Lower Tomb of Tyriosa 2F"},
    {"name": "Thymele", "fixed_time": "Mon 19:00 / Wed 11:30",
        "armor": "TBD", "level": 85, "location": "Twilight Hill"},
    {"name": "Amentis", "fixed_time": "29 hrs", "armor": "TBD",
        "level": 88, "location": "Land of Glory"},
    {"name": "Baron", "fixed_time": "32 hrs", "armor": "TBD",
        "level": 88, "location": "Battlefield of Templar"},
    {"name": "Milavy", "fixed_time": "Sat 15:00", "armor": "TBD",
        "level": 90, "location": "Lower Tomb of Tyriosa 3F"},
    {"name": "Wannitas", "fixed_time": "48 hrs", "armor": "TBD",
        "level": 93, "location": "Plateau of Revolution"},
    {"name": "Metus", "fixed_time": "48 hrs", "armor": "TBD",
        "level": 93, "location": "Plateau of Revolution"},
    {"name": "Duplican", "fixed_time": "48 hrs", "armor": "TBD",
        "level": 93, "location": "Plateau of Revolution"},
    {"name": "Shuliar", "fixed_time": "35 hrs", "armor": "TBD",
        "level": 95, "location": "Ruins of the War"},
    {"name": "Ringor", "fixed_time": "Sat 17:00", "armor": "TBD",
        "level": 95, "location": "Battlefield of Templar"},
    {"name": "Roderick", "fixed_time": "Fri 19:00", "armor": "TBD",
        "level": 95, "location": "Garbana Underground Waterway 1F"},
    {"name": "Gareth", "fixed_time": "32 hrs", "armor": "TBD",
        "level": 98, "location": "Deadman's Land District 1"},
    {"name": "Titore", "fixed_time": "37 hrs", "armor": "TBD",
        "level": 98, "location": "Deadman's Land District 2"},
    {"name": "Larba", "fixed_time": "34 hrs", "armor": "TBD",
        "level": 98, "location": "Ruins of the War"},
    {"name": "Catena", "fixed_time": "34 hrs", "armor": "TBD",
        "level": 100, "location": "Deadman's Land District 3"},
    {"name": "Auraq", "fixed_time": "Sun 21:00 / Wed 21:00", "armor": "TBD",
        "level": 100, "location": "Garbana Underground Waterway 2F"},
]

# Database setup


async def init_db():
    async with aiosqlite.connect('boss_timer.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS boss_kills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                boss_name TEXT NOT NULL,
                kill_time DATETIME NOT NULL,
                next_spawn DATETIME
            )
        ''')
        await db.commit()


class BossTimer:
    def __init__(self):
        self.bosses = {boss["name"]: boss for boss in BOSS_DATA}
        self.day_map = {
            "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
            "Fri": 4, "Sat": 5, "Sun": 6
        }
        self.live_messages = {}
        self.timezone = pytz.timezone('Asia/Manila')

        # Create a case-insensitive mapping of boss names
        self.boss_name_mapping = {}
        for boss_name in self.bosses.keys():
            # Create simplified versions for matching
            simplified = boss_name.lower().replace(" ", "")
            self.boss_name_mapping[simplified] = boss_name

            # Also add common short names
            if "lady" in boss_name.lower():
                self.boss_name_mapping["dalia"] = boss_name
                self.boss_name_mapping["lady"] = boss_name

    def find_boss_name(self, input_name):
        """Find the correct boss name from various input formats"""
        input_name = input_name.lower().replace(" ", "").replace("'", "")

        # Direct match
        if input_name in self.boss_name_mapping:
            return self.boss_name_mapping[input_name]

        # Partial match
        for simplified_name, real_name in self.boss_name_mapping.items():
            if input_name in simplified_name or simplified_name in input_name:
                return real_name

        return None

    def parse_fixed_time(self, fixed_time: str) -> Tuple[Optional[int], Optional[List[Tuple[int, int]]]]:
        """Parse fixed time string into hours or weekly schedule"""
        match = re.match(r'(\d+)\s*hrs', fixed_time)
        if match:
            return int(match.group(1)), None

        if '/' in fixed_time:
            schedules = fixed_time.split('/')
            result = []
            for schedule in schedules:
                schedule = schedule.strip()
                day_time = schedule.split()
                if len(day_time) == 2:
                    day, time_str = day_time
                    if day in self.day_map and ':' in time_str:
                        hour, minute = map(int, time_str.split(':'))
                        result.append((self.day_map[day], hour, minute))
            return None, result if result else None

        day_time = fixed_time.split()
        if len(day_time) == 2:
            day, time_str = day_time[0], day_time[1]
            if day in self.day_map and ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
                return None, [(self.day_map[day], hour, minute)]

        return None, None

    def calculate_next_spawn(self, boss_name: str, kill_time: datetime) -> datetime:
        """Calculate next spawn time based on boss fixed time"""
        boss = self.bosses[boss_name]
        hours, weekly_schedule = self.parse_fixed_time(boss["fixed_time"])

        if hours:
            return kill_time + timedelta(hours=hours)

        if weekly_schedule:
            next_times = []
            for day, hour, minute in weekly_schedule:
                days_ahead = (day - kill_time.weekday()) % 7
                if days_ahead == 0 and (kill_time.hour > hour or
                                        (kill_time.hour == hour and kill_time.minute >= minute)):
                    days_ahead = 7

                next_time = kill_time + timedelta(days=days_ahead)
                next_time = next_time.replace(
                    hour=hour, minute=minute, second=0, microsecond=0)
                next_times.append(next_time)

            return min(next_times)

        return kill_time + timedelta(hours=24)

    def format_time_left(self, next_spawn: datetime) -> str:
        """Format time left until next spawn"""
        now = datetime.now(self.timezone)
        if now >= next_spawn:
            return "NOW!"

        delta = next_spawn - now
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if delta.days > 0:
            return f"{delta.days}d {hours:02d}:{minutes:02d}"
        else:
            return f"{hours:02d}:{minutes:02d}"

    def format_fixed_time_for_table(self, fixed_time: str) -> str:
        """Format fixed time for display in the table"""
        if 'hrs' in fixed_time:
            return fixed_time

        if '/' in fixed_time:
            parts = fixed_time.split('/')
            compact_parts = []
            for part in parts:
                part = part.strip()
                if ' ' in part:
                    day, time = part.split()
                    compact_parts.append(f"{day}{time}")
                else:
                    compact_parts.append(part)
            return "/".join(compact_parts)

        if ' ' in fixed_time:
            day, time = fixed_time.split()
            return f"{day}{time}"

        return fixed_time

    def shorten_location(self, location: str) -> str:
        """Shorten long location names to save space"""
        short_names = {
            "Corrupted Basin": "CrptBasin",
            "Crescent Lake": "CrescentLk",
            "Ulan Canyon": "UlanCany",
            "Protector's Ruins": "ProtRuins",
            "Lower Tomb of Tyriosa 1F": "Tyriosa1F",
            "Secret Laboratory": "SecretLab",
            "Desert of the Screaming": "ScreamDst",
            "Twilight Hill": "TwilightHl",
            "Lower Tomb of Tyriosa 2F": "Tyriosa2F",
            "Land of Glory": "GloryLand",
            "Battlefield of Templar": "TemplarBF",
            "Lower Tomb of Tyriosa 3F": "Tyriosa3F",
            "Plateau of Revolution": "RevolPlat",
            "Ruins of the War": "WarRuins",
            "Garbana Underground Waterway 1F": "Garbana1F",
            "Deadman's Land District 1": "Deadman1",
            "Deadman's Land District 2": "Deadman2",
            "Deadman's Land District 3": "Deadman3",
            "Garbana Underground Waterway 2F": "Garbana2F"
        }
        return short_names.get(location, location[:10])

    def shorten_boss_name(self, name: str) -> str:
        """Shorten long boss names to save space"""
        short_names = {
            "Venatus": "Venatus",
            "Viorent": "Viorent",
            "Ego": "Ego",
            "Clementis": "Clemnts",
            "Livera": "Livera",
            "Araneo": "Araneo",
            "Undomiel": "Undomiel",
            "Saphirus": "Saphirus",
            "Neutro": "Neutro",
            "Lady Dalia": "LadyDalia",
            "Aquleus": "Aquleus",
            "Thymele": "Thymele",
            "Amentis": "Amentis",
            "Baron": "Baron",
            "Milavy": "Milavy",
            "Wannitas": "Wannitas",
            "Metus": "Metus",
            "Duplican": "Duplican",
            "Shuliar": "Shuliar",
            "Ringor": "Ringor",
            "Roderick": "Roderick",
            "Gareth": "Gareth",
            "Titore": "Titore",
            "Larba": "Larba",
            "Catena": "Catena",
            "Auraq": "Auraq"
        }
        return short_names.get(name, name[:8])

    async def generate_boss_table(self) -> str:
        """Generate a formatted table of all bosses with timers first"""
        async with aiosqlite.connect('boss_timer.db') as db:
            cursor = await db.execute(
                "SELECT boss_name, next_spawn FROM boss_kills WHERE id IN (SELECT MAX(id) FROM boss_kills GROUP BY boss_name)"
            )
            results = await cursor.fetchall()

        boss_times = {row[0]: datetime.fromisoformat(row[1]).astimezone(
            self.timezone) if row[1] else None for row in results}

        # Separate bosses with timers and without
        bosses_with_timers = []
        bosses_without_timers = []

        for boss_name, boss_data in self.bosses.items():
            next_spawn = boss_times.get(boss_name)
            if next_spawn:
                time_left = self.format_time_left(next_spawn)
            else:
                time_left = "TBD"

            short_boss_name = self.shorten_boss_name(boss_name)
            boss_with_level = f"{short_boss_name}({boss_data['level']})"
            short_location = self.shorten_location(boss_data["location"])
            formatted_fixed_time = self.format_fixed_time_for_table(
                boss_data["fixed_time"])

            row = [
                boss_with_level,
                time_left,
                formatted_fixed_time,
                short_location
            ]

            if time_left != "TBD":
                # Add the actual datetime for sorting
                bosses_with_timers.append((next_spawn, row))
            else:
                bosses_without_timers.append(row)

        # Sort bosses with timers by next spawn time (soonest first)
        bosses_with_timers.sort(key=lambda x: x[0])

        # Extract just the rows without the datetime
        sorted_bosses_with_timers = [
            row for (next_spawn, row) in bosses_with_timers]

        # Combine lists (timers first, then TBD bosses)
        table_data = sorted_bosses_with_timers + bosses_without_timers

        # Create table with headers
        headers = ["Boss(Lvl)", "Time Left", "Fixed Time", "Location"]
        table = tabulate(table_data, headers, tablefmt="simple")

        # Add timestamp
        timestamp = datetime.now(self.timezone).strftime(
            "%Y-%m-%d %H:%M:%S %Z")

        return f"```\n{table}\n\nLast updated: {timestamp}\n```"


# Initialize boss timer
boss_timer = BossTimer()


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await init_db()
    update_boss_timers.start()


@tasks.loop(seconds=5)
async def update_boss_timers():
    """Update all live boss timer messages"""
    for channel_id, message_id in boss_timer.live_messages.items():
        try:
            channel = bot.get_channel(channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                table_text = await boss_timer.generate_boss_table()
                await message.edit(content=table_text)
        except discord.NotFound:
            if channel_id in boss_timer.live_messages:
                del boss_timer.live_messages[channel_id]
        except Exception as e:
            print(f"Error updating message: {e}")


@bot.command(name='boss')
async def boss_info(ctx, *, boss_name: str):
    """Get information about a specific boss"""
    # Use our flexible boss name finder
    actual_boss_name = boss_timer.find_boss_name(boss_name)
    if not actual_boss_name:
        await ctx.send(f"Boss '{boss_name}' not found.")
        return

    boss = boss_timer.bosses[actual_boss_name]

    async with aiosqlite.connect('boss_timer.db') as db:
        cursor = await db.execute(
            "SELECT kill_time, next_spawn FROM boss_kills WHERE boss_name = ? ORDER BY kill_time DESC LIMIT 1",
            (actual_boss_name,)
        )
        result = await cursor.fetchone()

    if result:
        kill_time, next_spawn_str = result
        next_spawn = datetime.fromisoformat(
            next_spawn_str).astimezone(boss_timer.timezone)
        time_left = boss_timer.format_time_left(next_spawn)
        kill_time_display = datetime.fromisoformat(
            kill_time).astimezone(boss_timer.timezone).strftime('%H:%M')
    else:
        time_left = "TBD"
        kill_time_display = "N/A"

    embed = discord.Embed(title=f"Boss: {actual_boss_name}", color=0x00ff00)
    embed.add_field(name="Time Left", value=time_left, inline=True)
    embed.add_field(name="Fixed Time", value=boss["fixed_time"], inline=True)
    embed.add_field(name="Armor", value=boss["armor"], inline=True)
    embed.add_field(name="Level", value=boss["level"], inline=True)
    embed.add_field(name="Location", value=boss["location"], inline=True)
    embed.add_field(name="Last Kill Time",
                    value=kill_time_display, inline=True)

    await ctx.send(embed=embed)


@bot.command(name='bosslist')
async def boss_list(ctx):
    """Display the current boss timer table"""
    try:
        table_text = await boss_timer.generate_boss_table()
        await ctx.send(table_text)
    except Exception as e:
        await ctx.send(f"Error generating boss list: {e}")


@bot.command(name='livebosses')
async def live_bosses(ctx):
    """Start live updating boss timer table in this channel"""
    try:
        table_text = await boss_timer.generate_boss_table()
        message = await ctx.send(table_text)

        boss_timer.live_messages[ctx.channel.id] = message.id
        await ctx.send("Live boss timer started! This message will update every 5 seconds.")
    except Exception as e:
        await ctx.send(f"Error starting live boss timer: {e}")


@bot.command(name='stoplive')
async def stop_live(ctx):
    """Stop live updating boss timer table in this channel"""
    if ctx.channel.id in boss_timer.live_messages:
        del boss_timer.live_messages[ctx.channel.id]
        await ctx.send("Live boss timer stopped.")
    else:
        await ctx.send("No live timer is running in this channel.")


@bot.command(name='dead')
async def boss_dead(ctx, *, boss_name: str):
    """Mark a boss as dead (uses current time)"""
    # Use our flexible boss name finder
    actual_boss_name = boss_timer.find_boss_name(boss_name)
    if not actual_boss_name:
        await ctx.send(f"Boss '{boss_name}' not found.")
        return

    kill_time = datetime.now(boss_timer.timezone)
    next_spawn = boss_timer.calculate_next_spawn(actual_boss_name, kill_time)

    async with aiosqlite.connect('boss_timer.db') as db:
        await db.execute(
            "INSERT INTO boss_kills (boss_name, kill_time, next_spawn) VALUES (?, ?, ?)",
            (actual_boss_name, kill_time.isoformat(), next_spawn.isoformat())
        )
        await db.commit()

    time_left = boss_timer.format_time_left(next_spawn)
    await ctx.send(f"{actual_boss_name} has been marked as dead at {kill_time.strftime('%H:%M')}. Next spawn in {time_left}.")


@bot.command(name='diedat')
async def boss_died_at(ctx, boss_name: str, death_time: str):
    """Mark a boss as dead at a specific time"""
    # Use our flexible boss name finder
    actual_boss_name = boss_timer.find_boss_name(boss_name)
    if not actual_boss_name:
        await ctx.send(f"Boss '{boss_name}' not found.")
        return

    try:
        hour, minute = map(int, death_time.split(':'))
        now = datetime.now(boss_timer.timezone)
        kill_time = now.replace(hour=hour, minute=minute,
                                second=0, microsecond=0)

        if kill_time > now:
            kill_time = kill_time - timedelta(days=1)

    except ValueError:
        await ctx.send("Invalid time format. Please use HH:MM (e.g., 14:30).")
        return

    next_spawn = boss_timer.calculate_next_spawn(actual_boss_name, kill_time)

    async with aiosqlite.connect('boss_timer.db') as db:
        await db.execute(
            "INSERT INTO boss_kills (boss_name, kill_time, next_spawn) VALUES (?, ?, ?)",
            (actual_boss_name, kill_time.isoformat(), next_spawn.isoformat())
        )
        await db.commit()

    time_left = boss_timer.format_time_left(next_spawn)
    await ctx.send(f"{actual_boss_name} has been marked as dead at {kill_time.strftime('%H:%M')}. Next spawn in {time_left}.")


@bot.command(name='setboss')
async def set_boss_timer(ctx, boss_name: str, hours: int):
    """Manually set a boss timer"""
    # Use our flexible boss name finder
    actual_boss_name = boss_timer.find_boss_name(boss_name)
    if not actual_boss_name:
        await ctx.send(f"Boss '{boss_name}' not found.")
        return

    kill_time = datetime.now(boss_timer.timezone) - timedelta(hours=hours)
    next_spawn = datetime.now(boss_timer.timezone) + timedelta(hours=hours)

    async with aiosqlite.connect('boss_timer.db') as db:
        await db.execute(
            "INSERT INTO boss_kills (boss_name, kill_time, next_spawn) VALUES (?, ?, ?)",
            (actual_boss_name, kill_time.isoformat(), next_spawn.isoformat())
        )
        await db.commit()

    time_left = boss_timer.format_time_left(next_spawn)
    await ctx.send(f"Timer for {actual_boss_name} has been set. Next spawn in {time_left}.")


@bot.command(name='timezone')
async def set_timezone(ctx, timezone_str: str):
    """Set the timezone for the bot (requires restart)"""
    try:
        new_timezone = pytz.timezone(timezone_str)
        boss_timer.timezone = new_timezone
        await ctx.send(f"Timezone set to {timezone_str}. This change will take effect after restart.")
    except pytz.UnknownTimeZoneError:
        await ctx.send("Unknown timezone. Please use a valid timezone from the IANA Time Zone Database (e.g., 'Asia/Manila', 'America/New_York').")


@bot.command(name='currenttime')
async def current_time(ctx):
    """Show the current time according to the bot's timezone"""
    current_time = datetime.now(boss_timer.timezone)
    await ctx.send(f"Current bot time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")


@bot.command(name='help')
async def bot_help(ctx):
    """Show all available commands"""
    help_text = """
**Boss Timer Bot Commands:**

`!boss <boss_name>` - Get detailed information about a specific boss
`!bosslist` - Display the current boss timer table
`!livebosses` - Start live updating boss timer table in this channel
`!stoplive` - Stop live updating boss timer table in this channel
`!dead <boss_name>` - Mark a boss as dead (uses current time)
`!diedat <boss_name> <HH:MM>` - Mark a boss as dead at a specific time
`!setboss <boss_name> <hours>` - Manually set a boss timer
`!timezone <timezone>` - Set the timezone for the bot (requires restart)
`!currenttime` - Show the current time according to the bot's timezone
`!help` - Show this help message

**Examples:**
`!boss Venatus` - Shows Venatus information
`!dead Venatus` - Marks Venatus as dead at current time
`!diedat Viorent 11:00` - Marks Viorent as dead at 11:00
`!setboss Venatus 5` - Sets Venatus timer to 5 hours
`!livebosses` - Starts a live-updating boss table
`!timezone Asia/Manila` - Sets the timezone to Manila time

**Note:** Boss names are now case-insensitive and space-insensitive. For Lady Dalia, you can use:
- `!boss lady dalia`
- `!boss ladydalia` 
- `!boss dalia`
- `!boss LadyDalia`
"""
    await ctx.send(help_text)

# Run the bot
if __name__ == "__main__":
    bot.run('MTQxMTM1ODY2MDM5NDc1MDAxMg.GDmXHd.OX9RlDJonsiRM99VvzGwxVlIqPCIEARKBINzRc')
