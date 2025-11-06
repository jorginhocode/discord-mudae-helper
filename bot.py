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
MUDAE_CHANNEL_ID = 1129823274684137602  # ID of Mudae channel

# CONFIGURATION FILES
COOLDOWN_FILE = "cooldowns.json"
CONFIG_FILE = "config.json"

# Track recent commands for timing accuracy
recent_commands = {}  # {user_id: {"command": "daily/dk/vote", "timestamp": datetime, "username": str}}

# Track who has received notifications this hour to prevent duplicates
notified_users = {}  # {user_id: last_notification_hour}

# Load configuration - ONLY ALLOWED USERS WILL BE PROCESSED
def load_config():
    """Loads allowed users from config.json - ONLY THESE USERS WILL BE PROCESSED"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                allowed_users = config.get("allowed_users", [])
                # Convert to integers if they're strings in JSON
                return [int(user_id) for user_id in allowed_users]
        except Exception as e:
            print(f"❌ Error loading {CONFIG_FILE}: {e}")
            print("   Using empty allowed users list")
    else:
        print(f"⚠️ Warning: {CONFIG_FILE} not found!")
        print("   Create a config.json file with your allowed users")
        print("   Example format:")
        print('   {')
        print('     "allowed_users": [')
        print('       985284787252105226,')
        print('       1152991512620171346,')
        print('       1151649685858160670')
        print('     ]')
        print('   }')
    
    return []

# Load or create cooldown file
def load_cooldowns():
    """Loads existing cooldowns WITHOUT MODIFYING THEM"""
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Warning: Error loading {COOLDOWN_FILE}: {e}")
            print("   A new file with empty data will be created")
    return {}

def save_cooldowns(cooldowns):
    """Saves cooldowns in ISO UTC format (precise and standard format)"""
    with open(COOLDOWN_FILE, 'w') as f:
        json.dump(cooldowns, f, indent=2)

# Function to create standard footer
def create_footer() -> str:
    """Create standardized footer text."""
    return f"by @potyhx  •  {datetime.now().strftime('Today at %H:%M')}"

# Initialize configuration
allowed_users = load_config()
print('╔' + '═' * 60 + '╗')
print('║  ALLOWED USERS CONFIGURATION                               ║')
print('╚' + '═' * 60 + '╝')
if allowed_users:
    print(f'✅ {len(allowed_users)} users allowed:')
    for user_id in allowed_users:
        print(f'   • {user_id}')
else:
    print('❌ NO USERS ALLOWED - Create config.json to enable features')
print('')

# Initialize cooldowns
cooldowns = load_cooldowns()
print('╔' + '═' * 60 + '╗')
print('║  COOLDOWNS LOADED FROM FILE                                 ║')
print('╚' + '═' * 60 + '╝')
for user_id, user_data in cooldowns.items():
    print(f'User {user_id}:')
    for cmd, time_str in user_data.items():
        if cmd == "user_account":
            print(f'  • {cmd}: {time_str}')
        else:
            status = time_str if time_str else "NEVER USED"
            print(f'  • {cmd}: {status}')
print('')

intents = discord.Intents.default()
intents.message_content = True  # Required to read messages
intents.members = True
bot = discord.Client(intents=intents)

def get_user_display_name(user):
    """Get the best display name for a user (global name if available, else username#discriminator)"""
    if hasattr(user, 'global_name') and user.global_name:
        return f"{user.global_name} ({user.name})"
    return f"{user.name}#{user.discriminator}"

def is_user_allowed(user_id):
    """Check if user is in allowed list"""
    return int(user_id) in allowed_users

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

def format_timedelta(remaining_delta):
    """Format timedelta to human-readable string with seconds precision"""
    if remaining_delta.total_seconds() <= 0:
        return "Available"
    
    total_seconds = int(remaining_delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    
    return " ".join(parts)

def update_cooldown(user_id, command_type, username=None):
    """Updates cooldown for a specific command - MAINTAINS ISO UTC FORMAT"""
    now_utc = datetime.now(timezone.utc).isoformat()
    user_id_str = str(user_id)
    
    # Only update if user is allowed
    if not is_user_allowed(user_id):
        print(f"⚠️ Attempt to update cooldown for non-allowed user {user_id} - BLOCKED")
        return None
    
    # Initialize user if not exists
    if user_id_str not in cooldowns:
        cooldowns[user_id_str] = {
            "user_account": username or f"user_{user_id}",
            "last_daily": None,
            "last_dk": None,
            "last_vote": None
        }
    # Update username if provided (keeps newest name)
    elif username:
        cooldowns[user_id_str]["user_account"] = username
    
    if command_type == "daily":
        cooldowns[user_id_str]["last_daily"] = now_utc
        user_display = cooldowns[user_id_str]["user_account"]
        print(f"[{datetime.now().strftime('%H:%M')}] $daily registered successfully for {user_display} ({user_id})")
    elif command_type == "dk":
        cooldowns[user_id_str]["last_dk"] = now_utc
        user_display = cooldowns[user_id_str]["user_account"]
        print(f"[{datetime.now().strftime('%H:%M')}] $dk registered successfully for {user_display} ({user_id})")
    elif command_type == "vote":
        cooldowns[user_id_str]["last_vote"] = now_utc
        user_display = cooldowns[user_id_str]["user_account"]
        print(f"[{datetime.now().strftime('%H:%M')}] $vote registered successfully for {user_display} ({user_id})")
    
    save_cooldowns(cooldowns)
    return now_utc

@tasks.loop(minutes=1)
async def send_mudae_reminder():
    """Sends consolidated reminder every hour at minute :03 ONLY TO ALLOWED USERS"""
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    
    # Only send at minute :03
    if now.minute != 3:
        return
    
    # Clean up notified_users dictionary (remove entries older than 1 hour)
    for user_id in list(notified_users.keys()):
        if current_hour != notified_users[user_id]:
            del notified_users[user_id]
    
    # Send reminder ONLY to allowed users in cooldowns
    for user_id_str in list(cooldowns.keys()):
        user_id = int(user_id_str)
        
        # Skip if user is not allowed
        if not is_user_allowed(user_id):
            continue
        
        # Skip if already notified this hour
        if user_id in notified_users and notified_users[user_id] == current_hour:
            continue
        
        user = bot.get_user(user_id)
        if not user:
            try:
                user = await bot.fetch_user(user_id)
                # Update username if we can fetch the user
                username = get_user_display_name(user)
                if user_id_str in cooldowns:
                    cooldowns[user_id_str]["user_account"] = username
                    save_cooldowns(cooldowns)
            except discord.NotFound:
                print(f"Error: User {user_id} not found. Removing from cooldowns.")
                cooldowns.pop(user_id_str, None)
                save_cooldowns(cooldowns)
                continue
        
        # Get username for display
        username = cooldowns[user_id_str].get("user_account", str(user_id))
        
        # Get user's cooldowns
        user_cooldowns = cooldowns[user_id_str]
        
        # Calculate remaining times - $vote is now 12 hours
        daily_status, daily_remaining_time = get_time_remaining(user_cooldowns["last_daily"], 20)
        dk_status, dk_remaining_time = get_time_remaining(user_cooldowns["last_dk"], 20)
        vote_status, _ = get_time_remaining(user_cooldowns["last_vote"], 12)  # 12 HOURS FOR $VOTE!
        
        # Calculate time for NEXT $wa (minute 03 of next hour)
        next_wa_time, next_wa_delta = get_time_until_next_wa(now + timedelta(minutes=1))
        
        # Create message embed
        embed = discord.Embed(
            title="Mudae Helper: Announcements",
            description=f"Account: **{username}**",
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
                f">>> **$daily:** {format_last_used(user_cooldowns['last_daily'])}\n"
                f"**$dk:** {format_last_used(user_cooldowns['last_dk'])}\n"
                f"**$vote:** {format_last_used(user_cooldowns['last_vote'])}"
            ),
            inline=False
        )
        
        # Set images and footer
        embed.set_footer(text=create_footer(), icon_url=bot.user.display_avatar.url)
        
        try:
            await user.send(embed=embed)
            print(f"[{now.strftime('%H:%M')}] ✅ Sent consolidated reminder to {username} (minute 03)")
            # Mark as notified for this hour
            notified_users[user_id] = current_hour
        except discord.Forbidden:
            print(f"❌ Cannot send DMs to user {username}. Open a message with me first!")
        except Exception as e:
            print(f"❌ Error sending message to {username}: {e}")

    # Save notified_users state (optional but helpful for restarts)
    with open("notified_users.json", "w") as f:
        json.dump({str(k): v for k, v in notified_users.items()}, f)

@bot.event
async def on_ready():
    print(f'{bot.user} is ready and running')
    print('╔' + '═' * 60 + '╗')
    print('║  MUDAE BOT - USER ACCESS CONTROLLED                       ║')
    print('╚' + '═' * 60 + '╝')
    print(f'Mudae Channel: <#{MUDAE_CHANNEL_ID}>')
    print(f'Notifications every hour at minute :03 (UTC time)')
    print(f'OPEN A DM WITH ME TO RECEIVE NOTIFICATIONS!')
    print(f'Manual commands: !used daily, !used dk, !used vote, !status')
    
    # Load notified_users state if exists
    global notified_users
    if os.path.exists("notified_users.json"):
        try:
            with open("notified_users.json", "r") as f:
                data = json.load(f)
                notified_users = {int(k): v for k, v in data.items()}
            print(f"Loaded notification state for {len(notified_users)} users")
        except Exception as e:
            print(f"Error loading notification state: {e}")
            notified_users = {}
    
    # Verify bot has access to channel
    channel = bot.get_channel(MUDAE_CHANNEL_ID)
    if channel:
        print(f'Bot has access to Mudae channel: {channel.name}')
    else:
        print(f'⚠️ Warning: Cannot access Mudae channel (ID: {MUDAE_CHANNEL_ID})')
        print('   Make sure the bot is in the server and has permissions to view the channel')
    
    # Start reminder loop
    send_mudae_reminder.start()

@bot.event
async def on_message(message):
    """Handle messages - AUTOMATIC DETECTION + MANUAL COMMANDS (ONLY FOR ALLOWED USERS)"""
    
    # Ignore messages from bot itself
    if message.author.id == bot.user.id:
        return
    
    # Check if user is allowed
    user_allowed = is_user_allowed(message.author.id)
    
    # --- DETECT USER COMMANDS IN MUDAE CHANNEL (ONLY ALLOWED USERS) ---
    if message.channel.id == MUDAE_CHANNEL_ID:
        content = message.content.lower().strip()
        
        # Only process commands from allowed users
        if user_allowed:
            # Ensure user exists in cooldowns
            user_id_str = str(message.author.id)
            if user_id_str not in cooldowns:
                username = get_user_display_name(message.author)
                cooldowns[user_id_str] = {
                    "user_account": username,
                    "last_daily": None,
                    "last_dk": None,
                    "last_vote": None
                }
                save_cooldowns(cooldowns)
                print(f"🆕 New allowed user added: {username} ({message.author.id})")
            
            username = get_user_display_name(message.author)
            if content == "$daily":
                recent_commands[message.author.id] = {"command": "daily", "timestamp": datetime.now(timezone.utc), "username": username}
            elif content == "$dk":
                recent_commands[message.author.id] = {"command": "dk", "timestamp": datetime.now(timezone.utc), "username": username}
            elif content == "$vote":
                recent_commands[message.author.id] = {"command": "vote", "timestamp": datetime.now(timezone.utc), "username": username}
        else:
            # Optional: Send a warning message (comment out if not wanted)
            if content in ["$daily", "$dk", "$vote", "$wa"]:
                await message.channel.send(f"❌ User {message.author.mention} is not authorized to use Mudae commands. Contact the bot owner.")
                print(f"🚫 Unauthorized command attempt by {message.author.name} ({message.author.id}) in Mudae channel")
    
    # --- DETECT MUDAE'S RESPONSES (ONLY PROCESS FOR ALLOWED USERS) ---
    if message.author.id == 432610292342587392:  # Mudae bot ID
        content_lower = message.content.lower()
        
        # Clean up old entries in recent_commands (older than 15 seconds)
        now = datetime.now(timezone.utc)
        recent_commands_to_remove = []
        for user_id, cmd_data in recent_commands.items():
            if (now - cmd_data["timestamp"]).total_seconds() > 15:
                recent_commands_to_remove.append(user_id)
        for user_id in recent_commands_to_remove:
            del recent_commands[user_id]
        
        # Check if Mudae confirms daily reward (emoji check)
        if "✅" in message.content or "white_check_mark" in content_lower:
            # Find user who sent daily command recently (only allowed users)
            for user_id, cmd_data in recent_commands.items():
                if cmd_data["command"] == "daily" and is_user_allowed(user_id):
                    await message.channel.send("$daily registered successfully")
                    update_cooldown(user_id, "daily", cmd_data.get("username"))
                    # Remove from tracking
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    break
        
        # Check if Mudae confirms dk reward (SUCCESS case)
        elif "kakera" in content_lower and ("añadidos" in content_lower or "agregados" in content_lower or "added" in content_lower):
            # Find user who sent dk command recently (only allowed users)
            for user_id, cmd_data in recent_commands.items():
                if cmd_data["command"] == "dk" and is_user_allowed(user_id):
                    await message.channel.send("$dk registered successfully")
                    update_cooldown(user_id, "dk", cmd_data.get("username"))
                    # Remove from tracking
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    break
        
        # Check if Mudae is saying you CAN'T use dk (COOLDOWN case) → LOG IT (only for allowed users)
        elif "siguiente $dk" in content_lower or "próximo $dk" in content_lower or "next $dk" in content_lower:
            # Find user who sent dk command recently (only allowed users)
            for user_id, cmd_data in recent_commands.items():
                if cmd_data["command"] == "dk" and is_user_allowed(user_id):
                    user_name = cmd_data.get("username", str(user_id))
                    
                    # Get remaining time from cooldowns data
                    user_cooldowns = cooldowns.get(str(user_id), {})
                    last_dk = user_cooldowns.get("last_dk")
                    remaining_time_str = "unknown"
                    
                    if last_dk:
                        _, remaining_delta = get_time_remaining(last_dk, 20)
                        remaining_time_str = format_timedelta(remaining_delta)
                    
                    print(f"[COOLDOWN] User {user_name} tried to use $dk but has {remaining_time_str} remaining")
                    # Remove from tracking to avoid duplicate logs
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    break
        
        # Check if Mudae is saying you CAN'T use daily (COOLDOWN case) → LOG IT (only for allowed users)
        elif "you can claim your daily reward again" in content_lower or "puedes reclamar tu recompensa diaria de nuevo" in content_lower:
            # Find user who sent daily command recently (only allowed users)
            for user_id, cmd_data in recent_commands.items():
                if cmd_data["command"] == "daily" and is_user_allowed(user_id):
                    user_name = cmd_data.get("username", str(user_id))
                    
                    # Get remaining time from cooldowns data
                    user_cooldowns = cooldowns.get(str(user_id), {})
                    last_daily = user_cooldowns.get("last_daily")
                    remaining_time_str = "unknown"
                    
                    if last_daily:
                        _, remaining_delta = get_time_remaining(last_daily, 20)
                        remaining_time_str = format_timedelta(remaining_delta)
                    
                    print(f"[COOLDOWN] User {user_name} tried to use $daily but has {remaining_time_str} remaining")
                    # Remove from tracking
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    break
        
        # Check if Mudae is saying you CAN'T use vote (COOLDOWN case) → LOG IT (only for allowed users)
        elif "you can vote again" in content_lower or "puedes votar de nuevo" in content_lower:
            # Find user who sent vote command recently (only allowed users)
            for user_id, cmd_data in recent_commands.items():
                if cmd_data["command"] == "vote" and is_user_allowed(user_id):
                    user_name = cmd_data.get("username", str(user_id))
                    
                    # Get remaining time from cooldowns data
                    user_cooldowns = cooldowns.get(str(user_id), {})
                    last_vote = user_cooldowns.get("last_vote")
                    remaining_time_str = "unknown"
                    
                    if last_vote:
                        _, remaining_delta = get_time_remaining(last_vote, 12)
                        remaining_time_str = format_timedelta(remaining_delta)
                    
                    print(f"[COOLDOWN] User {user_name} tried to use $vote but has {remaining_time_str} remaining")
                    # Remove from tracking
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    break
        
        # Check if Mudae confirms vote reward
        elif ("votar" in content_lower or "voto" in content_lower or "vote" in content_lower) and ("gracias" in content_lower or "thank" in content_lower):
            # Find user who sent vote command recently (only allowed users)
            for user_id, cmd_data in recent_commands.items():
                if cmd_data["command"] == "vote" and is_user_allowed(user_id):
                    await message.channel.send("$vote registered successfully")
                    update_cooldown(user_id, "vote", cmd_data.get("username"))
                    # Remove from tracking
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    break
    
    # --- MANUAL COMMANDS (via DM or any channel) - ONLY ALLOWED USERS ---
    content = message.content.strip().lower()
    
    # Command to view current status IMPROVED
    if content == "!status":
        if not user_allowed:
            await message.channel.send("❌ You are not authorized to use this command. Contact the bot owner.")
            print(f"🚫 Unauthorized !status attempt by {message.author.name} ({message.author.id})")
            return
        
        user_id = str(message.author.id)
        username = get_user_display_name(message.author)
        
        # Initialize user if not exists
        if user_id not in cooldowns:
            cooldowns[user_id] = {
                "user_account": username,
                "last_daily": None,
                "last_dk": None,
                "last_vote": None
            }
            save_cooldowns(cooldowns)
        
        user_cooldowns = cooldowns[user_id]
        now = datetime.now(timezone.utc)
        
        # Get remaining times
        daily_status, daily_remaining = get_time_remaining(user_cooldowns["last_daily"], 20)
        dk_status, dk_remaining = get_time_remaining(user_cooldowns["last_dk"], 20)
        vote_status, vote_remaining = get_time_remaining(user_cooldowns["last_vote"], 12)  # 12 HOURS!
        
        # Time for next $wa
        next_wa_time, next_wa_delta = get_time_until_next_wa(now)
        
        # Create detailed embed
        embed = discord.Embed(
            title="Mudae Helper: Cooldowns",
            description=f"Account: **{username}**",
            color=discord.Color.from_rgb(88, 101, 242),  # COLOR CHANGED!
        )
        
        # Time for next commands (without brackets, with seconds)
        embed.add_field(
            name="Next Commands",
            value=(
                f">>> **$wa:** {next_wa_time}\n"
                f"**$daily:** {format_timedelta(daily_remaining)} (20h)\n"
                f"**$dk:** {format_timedelta(dk_remaining)} (20h)\n"
                f"**$vote:** {format_timedelta(vote_remaining)} (12h)"
            ),
            inline=False
        )
        
        # Last used (without "Uruguay Time")
        embed.add_field(
            name="Last Usage",
            value=(
                f">>> **$daily:** {format_last_used(user_cooldowns['last_daily'])}\n"
                f"**$dk:** {format_last_used(user_cooldowns['last_dk'])}\n"
                f"**$vote:** {format_last_used(user_cooldowns['last_vote'])}"
            ),
            inline=False
        )
        
        # Set images and footer
        embed.set_footer(text=create_footer(), icon_url=bot.user.display_avatar.url)
        
        await message.channel.send(embed=embed)
        print(f"[{now.strftime('%H:%M')}] !status executed by {username}")
    
    # Command to mark $daily as used (manual) - ONLY ALLOWED USERS
    elif content in ["!used daily", "!daily", "$daily"]:
        if not user_allowed:
            await message.channel.send("❌ You are not authorized to use this command. Contact the bot owner.")
            print(f"🚫 Unauthorized $daily attempt by {message.author.name} ({message.author.id})")
            return
        
        # Only respond if this is DM/manual command, not channel command
        if message.channel.id != MUDAE_CHANNEL_ID:
            username = get_user_display_name(message.author)
            update_cooldown(message.author.id, "daily", username)
            response = "$daily registered successfully\nNext available in 20 hours"
            await message.channel.send(response)
    
    # Command to mark $dk as used (manual) - ONLY ALLOWED USERS
    elif content in ["!used dk", "!dk", "$dk"]:
        if not user_allowed:
            await message.channel.send("❌ You are not authorized to use this command. Contact the bot owner.")
            print(f"🚫 Unauthorized $dk attempt by {message.author.name} ({message.author.id})")
            return
        
        # Only respond if this is DM/manual command, not channel command
        if message.channel.id != MUDAE_CHANNEL_ID:
            username = get_user_display_name(message.author)
            update_cooldown(message.author.id, "dk", username)
            response = "$dk registered successfully\nNext available in 20 hours"
            await message.channel.send(response)
    
    # Command to mark $vote as used (manual) - ONLY ALLOWED USERS
    elif content in ["!used vote", "!vote", "$vote"]:
        if not user_allowed:
            await message.channel.send("❌ You are not authorized to use this command. Contact the bot owner.")
            print(f"🚫 Unauthorized $vote attempt by {message.author.name} ({message.author.id})")
            return
        
        # Only respond if this is DM/manual command, not channel command
        if message.channel.id != MUDAE_CHANNEL_ID:
            username = get_user_display_name(message.author)
            update_cooldown(message.author.id, "vote", username)
            response = "$vote registered successfully\nNext available in 12 hours"
            await message.channel.send(response)
    
    # Help command
    elif content == "!help" or content == "!ayuda":
        help_text = f"""
✅ **AUTHORIZED USERS ONLY** ✅
This bot only works for pre-configured users in `config.json`

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
AUTOMATIC USER NAMING - Your @username is saved automatically

AVAILABLE COMMANDS (for authorized users only):
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

YOUR ACCOUNT IS AUTOMATICALLY REGISTERED:
• Only your pre-authorized accounts are tracked
• Your data is stored by your unique User ID (never changes)
• Unauthorized users (including other bots) are completely ignored
"""
        await message.channel.send(help_text)

# Run the bot
if __name__ == "__main__":
    print('Starting Mudae Bot - USER ACCESS CONTROLLED SYSTEM...')
    print(f'Target channel: ID {MUDAE_CHANNEL_ID}')
    print('Time system and automatic detection activated')
    print('File format: ISO UTC (precise) • Visualization: Clean and without emojis')
    print('✨ ONLY AUTHORIZED USERS FROM config.json WILL BE PROCESSED ✨')
    
    # Final check: Warn if no allowed users
    if not allowed_users:
        print('⚠️  WARNING: No allowed users configured!')
        print('   Create config.json with your user IDs to enable functionality')
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid token. Verify DISCORD_TOKEN in .env file")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
