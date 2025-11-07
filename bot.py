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
recent_commands = {}  # {user_id: {"command": "daily/dk/vote", "timestamp": datetime, "username": str, "vote_stage": int}}

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
intents.message_content = True
intents.members = True
intents.reactions = True
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
        return dt.strftime("%d/%m %H:%M")
    except Exception as e:
        print(f"Error formatting date: {e}")
        return "Format error"

def get_time_until_next_wa(now=None):
    """Calculates time until next minute 03"""
    if now is None:
        now = datetime.now(timezone.utc)
    
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
    
    if not is_user_allowed(user_id):
        return None
    
    if user_id_str not in cooldowns:
        cooldowns[user_id_str] = {
            "user_account": username or f"user_{user_id}",
            "last_daily": None,
            "last_dk": None,
            "last_vote": None
        }
    elif username:
        cooldowns[user_id_str]["user_account"] = username
    
    if command_type == "daily":
        cooldowns[user_id_str]["last_daily"] = now_utc
        user_display = cooldowns[user_id_str]["user_account"]
        print(f"[{datetime.now().strftime('%H:%M')}] $daily registered for {user_display}")
    elif command_type == "dk":
        cooldowns[user_id_str]["last_dk"] = now_utc
        user_display = cooldowns[user_id_str]["user_account"]
        print(f"[{datetime.now().strftime('%H:%M')}] $dk registered for {user_display}")
    elif command_type == "vote":
        cooldowns[user_id_str]["last_vote"] = now_utc
        user_display = cooldowns[user_id_str]["user_account"]
        print(f"[{datetime.now().strftime('%H:%M')}] $vote registered for {user_display}")
    
    save_cooldowns(cooldowns)
    return now_utc

@tasks.loop(minutes=1)
async def send_mudae_reminder():
    """Sends consolidated reminder every hour at minute :03 ONLY TO ALLOWED USERS"""
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    
    if now.minute != 3:
        return
    
    for user_id in list(notified_users.keys()):
        if current_hour != notified_users[user_id]:
            del notified_users[user_id]
    
    for user_id_str in list(cooldowns.keys()):
        user_id = int(user_id_str)
        
        if not is_user_allowed(user_id):
            continue
        
        if user_id in notified_users and notified_users[user_id] == current_hour:
            continue
        
        user = bot.get_user(user_id)
        if not user:
            try:
                user = await bot.fetch_user(user_id)
                username = get_user_display_name(user)
                if user_id_str in cooldowns:
                    cooldowns[user_id_str]["user_account"] = username
                    save_cooldowns(cooldowns)
            except discord.NotFound:
                cooldowns.pop(user_id_str, None)
                save_cooldowns(cooldowns)
                continue
        
        username = cooldowns[user_id_str].get("user_account", str(user_id))
        user_cooldowns = cooldowns[user_id_str]
        
        daily_status, _ = get_time_remaining(user_cooldowns["last_daily"], 20)
        dk_status, _ = get_time_remaining(user_cooldowns["last_dk"], 20)
        vote_status, _ = get_time_remaining(user_cooldowns["last_vote"], 12)
        
        next_wa_time, _ = get_time_until_next_wa(now + timedelta(minutes=1))
        
        embed = discord.Embed(
            title="Mudae Helper: Announcements",
            description=f"Account: **{username}**",
            color=discord.Color.from_rgb(88, 101, 242),
        )

        embed.add_field(
            name="Main Commands",
            value=(
                f">>> **$wa:** **NOW!**\n"
                f"**$daily:** {daily_status}\n"
                f"**$dk:** {dk_status}\n"
                f"**$vote:** {vote_status}\n"
                f"**Next $wa:** {next_wa_time}"
            ),
            inline=False
        )
        
        embed.set_footer(text=create_footer(), icon_url=bot.user.display_avatar.url)
        
        try:
            await user.send(embed=embed)
            print(f"[{now.strftime('%H:%M')}] ✅ Reminder sent to {username}")
            notified_users[user_id] = current_hour
        except discord.Forbidden:
            print(f"❌ Cannot send DMs to {username}. Open a message with me first!")
        except Exception as e:
            print(f"❌ Error sending to {username}: {e}")

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
    
    global notified_users
    if os.path.exists("notified_users.json"):
        try:
            with open("notified_users.json", "r") as f:
                data = json.load(f)
                notified_users = {int(k): v for k, v in data.items()}
            print(f"Loaded notification state for {len(notified_users)} users")
        except Exception as e:
            notified_users = {}
    
    channel = bot.get_channel(MUDAE_CHANNEL_ID)
    if channel:
        print(f'Bot has access to Mudae channel: {channel.name}')
    else:
        print(f'⚠️ Warning: Cannot access Mudae channel (ID: {MUDAE_CHANNEL_ID})')
        print('   Make sure the bot is in the server and has permissions to view the channel')
    
    send_mudae_reminder.start()

@bot.event
async def on_message(message):
    """Handle messages - AUTOMATIC DETECTION + MANUAL COMMANDS (ONLY FOR ALLOWED USERS)"""
    
    if message.author.id == bot.user.id:
        return
    
    user_allowed = is_user_allowed(message.author.id)
    
    # --- DETECT USER COMMANDS IN MUDAE CHANNEL (ONLY ALLOWED USERS) ---
    if message.channel.id == MUDAE_CHANNEL_ID:
        content = message.content.lower().strip()
        
        if user_allowed:
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
            
            username = get_user_display_name(message.author)
            
            # SPECIAL HANDLING FOR $VOTE - requires 2 executions
            if content == "$vote":
                current_time = datetime.now(timezone.utc)
                
                # Check if this user already has a vote tracking
                if message.author.id in recent_commands:
                    user_cmd = recent_commands[message.author.id]
                    
                    # If they're in stage 1 (first $vote executed), now they're in stage 2
                    if user_cmd.get("command") == "vote" and user_cmd.get("vote_stage", 0) == 1:
                        recent_commands[message.author.id] = {
                            "command": "vote",
                            "timestamp": current_time,
                            "username": username,
                            "vote_stage": 2  # Second execution - waiting for Mudae's response
                        }
                        print(f"[VOTE] {username} executed $vote second time - waiting for Mudae response")
                    else:
                        # Reset to stage 1 if they executed $vote again after cooldown
                        recent_commands[message.author.id] = {
                            "command": "vote",
                            "timestamp": current_time,
                            "username": username,
                            "vote_stage": 1  # First execution
                        }
                        print(f"[VOTE] {username} executed $vote first time")
                else:
                    # First time executing $vote
                    recent_commands[message.author.id] = {
                        "command": "vote",
                        "timestamp": current_time,
                        "username": username,
                        "vote_stage": 1  # First execution
                    }
                    print(f"[VOTE] {username} executed $vote first time")
            
            # Regular commands ($daily and $dk)
            elif content == "$daily":
                recent_commands[message.author.id] = {
                    "command": "daily", 
                    "timestamp": datetime.now(timezone.utc), 
                    "username": username
                }
            elif content == "$dk":
                recent_commands[message.author.id] = {
                    "command": "dk", 
                    "timestamp": datetime.now(timezone.utc), 
                    "username": username
                }
    
    # --- DETECT MUDAE'S RESPONSES (ONLY PROCESS FOR ALLOWED USERS) ---
    if message.author.id == 432610292342587392:  # Mudae bot ID
        content_lower = message.content.lower()
        
        has_checkmark = False
        try:
            for reaction in message.reactions:
                if str(reaction.emoji) == "✅" and reaction.count > 0:
                    has_checkmark = True
                    break
        except Exception:
            pass
        
        now = datetime.now(timezone.utc)
        # Create a list of items to process to avoid modifying dict during iteration
        commands_to_process = list(recent_commands.items())
        
        for user_id, cmd_data in commands_to_process:
            # Clean up old entries first
            if (now - cmd_data["timestamp"]).total_seconds() > 45:
                if user_id in recent_commands:
                    del recent_commands[user_id]
                continue
            
            # $daily confirmation
            if has_checkmark or "✅" in message.content or "white_check_mark" in content_lower or "daily reward" in content_lower or "recompensa diaria" in content_lower:
                if cmd_data["command"] == "daily" and is_user_allowed(user_id):
                    update_cooldown(user_id, "daily", cmd_data.get("username"))
                    if user_id in recent_commands:
                        del recent_commands[user_id]
            
            # $dk confirmation
            elif "kakera" in content_lower and (
                "añadidos a tu colección" in content_lower or
                "añadido a tu colección" in content_lower or
                "agregados a tu colección" in content_lower or
                "added to your collection" in content_lower or
                "added to your list" in content_lower or
                "you received" in content_lower or
                "kakera added" in content_lower
            ):
                if cmd_data["command"] == "dk" and is_user_allowed(user_id):
                    update_cooldown(user_id, "dk", cmd_data.get("username"))
                    if user_id in recent_commands:
                        del recent_commands[user_id]
            
            # $dk cooldown message
            elif "you can use $dk again" in content_lower or "puedes usar $dk de nuevo" in content_lower or "next $dk" in content_lower or "próximo $dk" in content_lower or "siguiente $dk" in content_lower:
                if cmd_data["command"] == "dk" and is_user_allowed(user_id):
                    user_name = cmd_data.get("username", str(user_id))
                    user_cooldowns = cooldowns.get(str(user_id), {})
                    last_dk = user_cooldowns.get("last_dk")
                    if last_dk:
                        _, remaining_delta = get_time_remaining(last_dk, 20)
                        remaining_time_str = format_timedelta(remaining_delta)
                        print(f"[COOLDOWN] {user_name} tried $dk but has {remaining_time_str} remaining")
                    if user_id in recent_commands:
                        del recent_commands[user_id]
            
            # $daily cooldown message
            elif "you can claim your daily reward again" in content_lower or "puedes reclamar tu recompensa diaria de nuevo" in content_lower or "next daily" in content_lower or "próximo daily" in content_lower or "siguiente daily" in content_lower:
                if cmd_data["command"] == "daily" and is_user_allowed(user_id):
                    user_name = cmd_data.get("username", str(user_id))
                    user_cooldowns = cooldowns.get(str(user_id), {})
                    last_daily = user_cooldowns.get("last_daily")
                    if last_daily:
                        _, remaining_delta = get_time_remaining(last_daily, 20)
                        remaining_time_str = format_timedelta(remaining_delta)
                        print(f"[COOLDOWN] {user_name} tried $daily but has {remaining_time_str} remaining")
                    if user_id in recent_commands:
                        del recent_commands[user_id]
            
            # SPECIAL $VOTE HANDLING - Improved with cooldown check
            if "puedes votar nuevamente en" in content_lower or "you can vote again in" in content_lower:
                if cmd_data.get("command") == "vote" and cmd_data.get("vote_stage", 0) == 2 and is_user_allowed(user_id):
                    username = cmd_data.get("username", f"user_{user_id}")
                    user_id_str = str(user_id)
                    
                    # Check if user already has an active vote cooldown
                    if user_id_str in cooldowns and cooldowns[user_id_str].get("last_vote"):
                        last_vote_str = cooldowns[user_id_str]["last_vote"]
                        if last_vote_str:
                            status, remaining = get_time_remaining(last_vote_str, 12)
                            if status != "Available":
                                remaining_time_str = format_timedelta(remaining)
                                print(f"[COOLDOWN] {username} already has active vote cooldown - {remaining_time_str} remaining")
                                if user_id in recent_commands:
                                    del recent_commands[user_id]
                                continue
                    
                    # Only update cooldown if no active cooldown exists
                    update_cooldown(user_id, "vote", username)
                    if user_id in recent_commands:
                        del recent_commands[user_id]
                    print(f"[VOTE] ✅ $vote registered successfully for {username}")
            
            # $vote already used / on cooldown (immediate response)
            elif "¡puedes votar en este momento!" in content_lower or "you can vote right now!" in content_lower:
                if cmd_data.get("command") == "vote" and cmd_data.get("vote_stage", 0) == 2 and is_user_allowed(user_id):
                    username = cmd_data.get("username", f"user_{user_id}")
                    user_id_str = str(user_id)
                    
                    # Check existing cooldown
                    if user_id_str in cooldowns and cooldowns[user_id_str].get("last_vote"):
                        last_vote_str = cooldowns[user_id_str]["last_vote"]
                        if last_vote_str:
                            status, remaining = get_time_remaining(last_vote_str, 12)
                            if status != "Available":
                                remaining_time_str = format_timedelta(remaining)
                                print(f"[COOLDOWN] {username} tried $vote but has {remaining_time_str} remaining")
                    
                    if user_id in recent_commands:
                        del recent_commands[user_id]
    
    # --- MANUAL COMMANDS (via DM or any channel) - ONLY ALLOWED USERS ---
    content = message.content.strip().lower()
    
    if content == "!status":
        if not user_allowed:
            return
        
        user_id = str(message.author.id)
        username = get_user_display_name(message.author)
        
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
        
        daily_status, daily_remaining = get_time_remaining(user_cooldowns["last_daily"], 20)
        dk_status, dk_remaining = get_time_remaining(user_cooldowns["last_dk"], 20)
        vote_status, vote_remaining = get_time_remaining(user_cooldowns["last_vote"], 12)
        
        next_wa_time, _ = get_time_until_next_wa(now)
        
        embed = discord.Embed(
            title="Mudae Helper: Cooldowns",
            description=f"Account: **{username}**",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        
        embed.add_field(
            name="Next Commands",
            value=(
                f">>> **$wa:** {next_wa_time}\n"
                f"**$daily:** {format_timedelta(daily_remaining)}\n"
                f"**$dk:** {format_timedelta(dk_remaining)}\n"
                f"**$vote:** {format_timedelta(vote_remaining)}"
            ),
            inline=False
        )
        
        embed.set_footer(text=create_footer(), icon_url=bot.user.display_avatar.url)
        
        await message.channel.send(embed=embed)
        print(f"[{now.strftime('%H:%M')}] !status used by {username}")
    
    elif content in ["!used daily", "!daily", "$daily"]:
        if not user_allowed:
            return
        
        if message.channel.id != MUDAE_CHANNEL_ID:
            username = get_user_display_name(message.author)
            update_cooldown(message.author.id, "daily", username)
            await message.channel.send("$daily registered successfully\nNext available in 20 hours")
    
    elif content in ["!used dk", "!dk", "$dk"]:
        if not user_allowed:
            return
        
        if message.channel.id != MUDAE_CHANNEL_ID:
            username = get_user_display_name(message.author)
            update_cooldown(message.author.id, "dk", username)
            await message.channel.send("$dk registered successfully\nNext available in 20 hours")
    
    elif content in ["!used vote", "!vote", "$vote"]:
        if not user_allowed:
            return
        
        if message.channel.id != MUDAE_CHANNEL_ID:
            username = get_user_display_name(message.author)
            update_cooldown(message.author.id, "vote", username)
            await message.channel.send("$vote registered successfully\nNext available in 12 hours")
    
    elif content == "!help" or content == "!ayuda":
        help_text = f"""
✅ **AUTHORIZED USERS ONLY** ✅
This bot only works for pre-configured users in `config.json`

MAIN FEATURES:
NOTIFICATIONS AT MINUTE 03! - Every hour at :03 UTC
AUTOMATIC DETECTION in channel <#{MUDAE_CHANNEL_ID}>
20 HOURS for $daily and $dk
12 HOURS for $vote

AVAILABLE COMMANDS (for authorized users only):
• !status - Shows detailed remaining times
• !used daily - Force register $daily
• !used dk - Force register $dk  
• !used vote - Force register $vote (12h cooldown)
• !help - Show this help

NORMAL FLOW:
1. Every hour at :03 UTC you receive a DM with all times
2. Send $wa, $daily, $dk, $vote in <#{MUDAE_CHANNEL_ID}>
3. The bot automatically detects your commands
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
    print('✨ ONLY AUTHORIZED USERS FROM config.json WILL BE PROCESSED ✨')
    
    if not allowed_users:
        print('⚠️  WARNING: No allowed users configured!')
        print('   Create config.json with your user IDs to enable functionality')
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid token. Verify DISCORD_TOKEN in .env file")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
