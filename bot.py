import discord
from discord.ext import tasks
import asyncio
from datetime import datetime, timezone, timedelta
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
YOUR_USER_ID = int(os.getenv('YOUR_USER_ID', 0))
MUDAE_CHANNEL_ID = 1129823274684137602  # ID of Mudae channel

# File to save cooldowns - MAINTAINS ISO UTC FORMAT!
COOLDOWN_FILE = "cooldowns.json"

# Load or create cooldown file - RESPECTS EXISTING DATA!
def load_cooldowns():
    """Loads existing cooldowns WITHOUT MODIFYING THEM"""
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Error loading {COOLDOWN_FILE}: {e}")
            print("   A new file with empty data will be created")
    return {
        "last_daily": None,
        "last_dk": None,
        "last_vote": None
    }

def save_cooldowns(cooldowns):
    """Saves cooldowns in ISO UTC format (precise and standard format)"""
    with open(COOLDOWN_FILE, 'w') as f:
        json.dump(cooldowns, f)

# Function to create standard footer
def create_footer() -> str:
    """Create standardized footer text."""
    return f"by @potyhx  •  {datetime.now().strftime('Today at %H:%M')}"

# Initialize cooldowns - LOADS EXISTING DATA!
cooldowns = load_cooldowns()
print('╔' + '═' * 60 + '╗')
print('║  COOLDOWNS LOADED FROM FILE                                 ║')
print('╚' + '═' * 60 + '╝')
for cmd, time_str in cooldowns.items():
    status = time_str if time_str else "NEVER USED"
    print(f'• {cmd}: {status}')
print('')

intents = discord.Intents.default()
intents.message_content = True  # Required to read messages
intents.members = True
bot = discord.Client(intents=intents)

def get_time_remaining(last_used_str, cooldown_hours=20):
    """Calculates remaining time with precision (hours and minutes) - MAINTAINS UTC"""
    if not last_used_str:
        return "Available", timedelta(hours=0)
    
    # Convert string to datetime with UTC timezone - RESPECTS EXISTING FORMAT!
    last_used = datetime.fromisoformat(last_used_str)
    if last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=timezone.utc)
    
    next_available = last_used + timedelta(hours=cooldown_hours)
    now = datetime.now(timezone.utc)
    
    if now >= next_available:
        return "Available", timedelta(hours=0)
    
    remaining = next_available - now
    total_minutes = remaining.total_seconds() // 60
    
    if total_minutes >= 60:
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        return f"{hours}h {minutes}m", remaining
    else:
        minutes = int(total_minutes)
        return f"{minutes}m", remaining

def format_last_used(time_str):
    """Formats the last time a command was used - SHOWS IN READABLE FORMAT"""
    if not time_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        # Show in readable format (without specific timezone)
        return dt.strftime("%d/%m %H:%M")
    except Exception as e:
        print(f"Error formatting date: {e}")
        return "Format error"

def get_time_until_next_wa(now=None):
    """Calculates time until next minute 03"""
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Next minute 03 of this hour or the next
    next_wa = now.replace(minute=3, second=0, microsecond=0)
    if now.minute > 3 or (now.minute == 3 and now.second > 0):
        next_wa += timedelta(hours=1)
    
    time_diff = next_wa - now
    total_minutes = time_diff.total_seconds() // 60
    
    if total_minutes >= 60:
        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        return f"{hours}h {minutes}m", time_diff
    else:
        minutes = int(total_minutes)
        return f"{minutes}m", time_diff

def update_cooldown(command_type):
    """Updates cooldown for a specific command - MAINTAINS ISO UTC FORMAT"""
    now_utc = datetime.now(timezone.utc).isoformat()
    
    if command_type == "daily":
        cooldowns["last_daily"] = now_utc
        print(f"[{datetime.now().strftime('%H:%M')}] $daily detected and registered")
    elif command_type == "dk":
        cooldowns["last_dk"] = now_utc
        print(f"[{datetime.now().strftime('%H:%M')}] $dk detected and registered")
    elif command_type == "vote":
        cooldowns["last_vote"] = now_utc
        print(f"[{datetime.now().strftime('%H:%M')}] $vote detected and registered")
    
    save_cooldowns(cooldowns)
    return now_utc

@tasks.loop(minutes=1)
async def send_mudae_reminder():
    """Sends consolidated reminder every hour at minute :03"""
    now = datetime.now(timezone.utc)
    
    # Only send at minute :03
    if now.minute != 3:
        return
    
    user = bot.get_user(YOUR_USER_ID)
    if not user:
        try:
            user = await bot.fetch_user(YOUR_USER_ID)
        except discord.NotFound:
            print("Error: User not found. Verify YOUR_USER_ID in .env")
            return
    
    # Calculate remaining times - $vote is now 12 hours
    daily_status, daily_remaining_time = get_time_remaining(cooldowns["last_daily"], 20)
    dk_status, dk_remaining_time = get_time_remaining(cooldowns["last_dk"], 20)
    vote_status, _ = get_time_remaining(cooldowns["last_vote"], 12)  # 12 HOURS FOR $VOTE!
    
    # Calculate time for NEXT $wa (minute 03 of next hour)
    next_wa_time, next_wa_delta = get_time_until_next_wa(now + timedelta(minutes=1))
    
    # Create message embed
    embed = discord.Embed(
        title="Mudae Helper: Announcements",
        description="",
        color=discord.Color.from_rgb(88, 101, 242),  # COLOR CHANGED!
    )

    # Main commands with exact times
    embed.add_field(
        name="Main Commands",
        value=(
            f">>> **$wa:** **NOW!**\n"
            f"**$daily:** {daily_status} (20h)\n"
            f"**$dk:** {dk_status} (20h)\n"
            f"**$vote:** {vote_status} (12h)\n"
            f"**Next $wa:** {next_wa_time}"
        ),
        inline=False
    )
    
    # Last used
    embed.add_field(
        name="Last Usage",
        value=(
            f">>> **$daily:** {format_last_used(cooldowns['last_daily'])}\n"
            f"**$dk:** {format_last_used(cooldowns['last_dk'])}\n"
            f"**$vote:** {format_last_used(cooldowns['last_vote'])}"
        ),
        inline=False
    )
    
    # Set images and footer
    embed.set_footer(text=create_footer(), icon_url=bot.user.display_avatar.url)
    
    try:
        await user.send(embed=embed)
        print(f"[{now.strftime('%H:%M')}] Sent consolidated reminder to {user.name} (minute 03)")
    except discord.Forbidden:
        print("Cannot send you DMs. Open a message with me first!")
    except Exception as e:
        print(f"Error sending message: {e}")

@bot.event
async def on_ready():
    print(f'{bot.user} is ready and running')
    print('╔' + '═' * 60 + '╗')
    print('║  MUDAE BOT - EXISTING DATA RESPECTED                      ║')
    print('╚' + '═' * 60 + '╝')
    print(f'User ID: {YOUR_USER_ID}')
    print(f'Mudae Channel: <#{MUDAE_CHANNEL_ID}>')
    print(f'Notifications every hour at minute :03 (UTC time)')
    print(f'OPEN A DM WITH ME TO RECEIVE NOTIFICATIONS!')
    print(f'Manual commands: !used daily, !used dk, !used vote, !status')
    
    # Verify bot has access to channel
    channel = bot.get_channel(MUDAE_CHANNEL_ID)
    if channel:
        print(f'Bot has access to Mudae channel: {channel.name}')
    else:
        print(f'Warning: Cannot access Mudae channel (ID: {MUDAE_CHANNEL_ID})')
        print('   Make sure the bot is in the server and has permissions to view the channel')
    
    # Start reminder loop
    send_mudae_reminder.start()

@bot.event
async def on_message(message):
    """Handle messages - AUTOMATIC DETECTION + MANUAL COMMANDS"""
    
    # Ignore messages from bot itself
    if message.author.id == bot.user.id:
        return
    
    # --- AUTOMATIC DETECTION IN MUDAE CHANNEL ---
    if message.channel.id == MUDAE_CHANNEL_ID and message.author.id == YOUR_USER_ID:
        content = message.content.strip().lower()
        
        # Detect $daily
        if content == "$daily":
            update_cooldown("daily")
            print(f"[AUTO] $daily detected in channel by {message.author.name}")
        
        # Detect $dk
        elif content == "$dk":
            update_cooldown("dk")
            print(f"[AUTO] $dk detected in channel by {message.author.name}")
        
        # Detect $vote - IMPORTANT!
        elif content == "$vote":
            update_cooldown("vote")
            print(f"[AUTO] $vote detected in channel by {message.author.name}")
    
    # --- MANUAL COMMANDS (via DM or any channel) ---
    if message.author.id != YOUR_USER_ID:
        return
    
    content = message.content.strip().lower()
    
    # Command to view current status IMPROVED
    if content == "!status":
        now = datetime.now(timezone.utc)
        
        # Get remaining times
        daily_status, daily_remaining = get_time_remaining(cooldowns["last_daily"], 20)
        dk_status, dk_remaining = get_time_remaining(cooldowns["last_dk"], 20)
        vote_status, _ = get_time_remaining(cooldowns["last_vote"], 12)  # 12 HOURS!
        
        # Time for next $wa
        next_wa_time, next_wa_delta = get_time_until_next_wa(now)
        
        # Calculate remaining time for daily and dk in detailed format (with seconds)
        def format_detailed_time(remaining_delta):
            if remaining_delta.total_seconds() <= 0:
                return "Available"
            
            total_seconds = int(remaining_delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        
        # Create detailed embed
        embed = discord.Embed(
            title="Mudae Helper: Cooldowns",
            description="",
            color=discord.Color.from_rgb(88, 101, 242),  # COLOR CHANGED!
        )
        
        # Time for next commands (without brackets, with seconds)
        embed.add_field(
            name="Next Commands",
            value=(
                f">>> **$wa:** {next_wa_time}\n"
                f"**$daily:** {format_detailed_time(daily_remaining)} (20h)\n"
                f"**$dk:** {format_detailed_time(dk_remaining)} (20h)\n"
                f"**$vote:** {format_detailed_time(get_time_remaining(cooldowns['last_vote'], 12)[1])} (12h)"
            ),
            inline=False
        )
        
        # Last used (without "Uruguay Time")
        embed.add_field(
            name="Last Usage",
            value=(
                f">>> **$daily:** {format_last_used(cooldowns['last_daily'])}\n"
                f"**$dk:** {format_last_used(cooldowns['last_dk'])}\n"
                f"**$vote:** {format_last_used(cooldowns['last_vote'])}"
            ),
            inline=False
        )
        
        # Set images and footer
        embed.set_footer(text=create_footer(), icon_url=bot.user.display_avatar.url)
        
        await message.channel.send(embed=embed)
        print(f"[{now.strftime('%H:%M')}] !status executed by {message.author.name}")
    
    # Command to mark $daily as used (manual)
    elif content in ["!used daily", "!daily", "$daily"]:
        update_cooldown("daily")
        response = "$daily registered successfully\nNext available in 20 hours"
        await message.channel.send(response)
    
    # Command to mark $dk as used (manual)
    elif content in ["!used dk", "!dk", "$dk"]:
        update_cooldown("dk")
        response = "$dk registered successfully\nNext available in 20 hours"
        await message.channel.send(response)
    
    # Command to mark $vote as used - 12 HOURS!
    elif content in ["!used vote", "!vote", "$vote"]:
        update_cooldown("vote")
        response = "$vote registered successfully\nNext available in 12 hours"
        await message.channel.send(response)
    
    # Help command
    elif content == "!help" or content == "!ayuda":
        help_text = f"""
YOUR DATA IS SAFE!
The bot loads and respects the times from your `cooldowns.json` file
Never resets your existing cooldowns
Maintains ISO UTC format in file for mathematical precision
Shows times in clean format without unnecessary emojis

MAIN FEATURES:
NOTIFICATIONS AT MINUTE 03! - Every hour at :03 UTC
AUTOMATIC DETECTION in channel <#{MUDAE_CHANNEL_ID}>
20 HOURS for $daily and $dk
12 HOURS for $vote
IMPROVED !status COMMAND with exact times

AVAILABLE COMMANDS:
• !status - Shows detailed remaining times
• !used daily - Force register $daily
• !used dk - Force register $dk  
• !used vote - Force register $vote (12h cooldown)
• !help - Show this help

NORMAL FLOW:
1. Every hour at :03 UTC you receive a DM with all times
2. Send $wa, $daily, $dk, $vote in <#{MUDAE_CHANNEL_ID}>
3. The bot automatically detects your commands and respects your existing data
4. Use !status anytime to see exact times

"""
        await message.channel.send(help_text)

# Run the bot
if __name__ == "__main__":
    print(f'Target channel: ID {MUDAE_CHANNEL_ID}')
    print(f'Target user: ID {YOUR_USER_ID}')
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("Invalid token. Verify DISCORD_TOKEN in .env file")
    except Exception as e:
        print(f"Unexpected error: {e}")