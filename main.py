import discord
from discord.ext import commands, tasks
import os
import requests
import json
import asyncio
from datetime import datetime, timezone, timedelta, date

WIB = timezone(timedelta(hours=7))

# =====================
# secrets
# =====================
TOKEN = os.getenv("TOKEN")
ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE")
ROBLOX_BOT_USER_ID = os.getenv("ROBLOX_BOT_USER_ID")

# =====================
# ganti ini
# =====================
ALLOWED_USERS = [884745169050681386]
CHANNEL_ID = 1507944297318715392
DASHBOARD_CHANNEL_ID = 1507944297318715392

ROBLOX_FILE = "users.json"
HISTORY_FILE = "history.json"

last_status = {}
last_location_cache = {}
dashboard_message_ids = {}
dashboard_channel_id_active = None

# =====================
# discord setup
# =====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =====================
# helper json
# =====================
def load_users():
    try:
        with open(ROBLOX_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_users(users):
    with open(ROBLOX_FILE, "w") as f:
        json.dump(users, f)

def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def add_history(uid: int, username: str, prev_label: str, new_label: str, location: str):
    history = load_history()
    key = str(uid)
    today = str(date.today())
    now = datetime.now(WIB).strftime("%H:%M:%S")

    if key not in history:
        history[key] = {"username": username, "logs": {}}

    history[key]["username"] = username

    if today not in history[key]["logs"]:
        history[key]["logs"][today] = []

    history[key]["logs"][today].append({
        "time": now,
        "from": prev_label,
        "to": new_label,
        "location": location
    })

    logs = history[key]["logs"]
    sorted_days = sorted(logs.keys(), reverse=True)
    for old_day in sorted_days[30:]:
        del logs[old_day]

    save_history(history)

# =====================
# helper roblox
# =====================
user_info_cache = {}

def get_roblox_user_info(user_id):
    if user_id in user_info_cache:
        return user_info_cache[user_id]
    url = f"https://users.roblox.com/v1/users/{user_id}"
    r = requests.get(url)
    data = r.json()
    info = {
        "name": data.get("name", str(user_id)),
        "display_name": data.get("displayName", str(user_id)),
        "id": user_id
    }
    user_info_cache[user_id] = info
    return info

def get_roblox_avatar_url(user_id):
    try:
        url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=false"
        r = requests.get(url)
        data = r.json()
        return data["data"][0]["imageUrl"]
    except:
        return None

def get_roblox_presence(users):
    url = "https://presence.roblox.com/v1/presence/users"
    r = requests.post(
        url,
        json={"userIds": users},
        cookies={".ROBLOSECURITY": ROBLOX_COOKIE}
    )
    data = r.json().get("userPresences", [])
    # Debug: print location tiap user
    for u in data:
        print(f"UID: {u['userId']} | presence: {u['userPresenceType']} | location: {u.get('lastLocation')!r}")
    return data

def get_online_friends():
    if not ROBLOX_BOT_USER_ID:
        return set()
    try:
        url = f"https://friends.roblox.com/v1/users/{ROBLOX_BOT_USER_ID}/friends/online"
        r = requests.get(url, cookies={".ROBLOSECURITY": ROBLOX_COOKIE})
        data = r.json()
        return {friend["id"] for friend in data.get("data", [])}
    except Exception as e:
        print(f"Friends API error: {e}")
        return set()

# =====================
# status config
# =====================
status_map = {
    0: "Offline",
    1: "Online",
    2: "In Game",
    3: "Roblox Studio"
}

status_color = {
    0: discord.Color.from_rgb(128, 128, 128),
    1: discord.Color.from_rgb(87, 242, 135),
    2: discord.Color.from_rgb(88, 101, 242),
    3: discord.Color.from_rgb(254, 231, 92),
    99: discord.Color.from_rgb(255, 100, 200),
}

status_emoji = {
    0: "🔴",
    1: "🟢",
    2: "🎮",
    3: "🛠️",
    99: "👻"
}

def resolve_status(user: dict, online_friend_ids: set) -> tuple:
    presence = user.get("userPresenceType", 0)
    last_location = (user.get("lastLocation") or "").strip()
    uid = user.get("userId")

    if presence != 0:
        label = status_map.get(presence, "Unknown")
        color = status_color.get(presence, discord.Color.default())
        emoji = status_emoji.get(presence, "❓")
        return label, color, emoji, last_location, presence

    in_friends_online = uid in online_friend_ids

    if in_friends_online and last_location:
        return "Online (Hidden)", status_color[99], status_emoji[99], last_location, 99
    elif in_friends_online:
        return "Online (Hidden)", status_color[99], status_emoji[99], "", 99
    else:
        return "Offline", status_color[0], status_emoji[0], "", 0

# =====================
# embed builders
# =====================
def build_status_embed(user_info: dict, status_label: str, color, emoji: str, location: str, prev_label: str = None) -> discord.Embed:
    username = user_info["name"]
    display_name = user_info["display_name"]
    user_id = user_info["id"]
    profile_url = f"https://www.roblox.com/users/{user_id}/profile"
    now = datetime.now(timezone.utc)

    if prev_label:
        embed = discord.Embed(title=f"{emoji} Status berubah", color=color, timestamp=now)
        embed.add_field(name="Sebelumnya", value=f"`{prev_label}`", inline=True)
        embed.add_field(name="Sekarang", value=f"`{status_label}`", inline=True)
    else:
        embed = discord.Embed(title=f"{emoji} {status_label}", color=color, timestamp=now)

    embed.set_author(
        name=f"{display_name} (@{username})",
        url=profile_url,
        icon_url=get_roblox_avatar_url(user_id) or ""
    )

    if location:
        embed.add_field(name="🗺️ Game", value=location, inline=False)

    embed.set_footer(text=f"Roblox ID: {user_id}")
    return embed

def build_list_embed(users_data: list) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Daftar User Roblox",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    if users_data:
        lines = []
        for uid in users_data:
            info = get_roblox_user_info(uid)
            lines.append(f"**{info['display_name']}** (@{info['name']}) — `{uid}`")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Total: {len(users_data)} user")
    else:
        embed.description = "Belum ada user yang ditambahkan."
    return embed

def build_history_embed(uid: int, username: str, target_date: str = None) -> discord.Embed:
    history = load_history()
    key = str(uid)
    today = str(date.today())
    check_date = target_date or today

    embed = discord.Embed(
        title=f"📅 History — @{username}",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    if key not in history or check_date not in history[key].get("logs", {}):
        embed.description = f"Tidak ada history untuk tanggal `{check_date}`."
        return embed

    logs = history[key]["logs"][check_date]
    lines = []
    for entry in logs:
        loc = f" • {entry['location']}" if entry.get("location") else ""
        lines.append(f"`{entry['time']}` {entry['from']} → **{entry['to']}**{loc}")

    embed.description = "\n".join(lines) or "Tidak ada perubahan status hari ini."
    embed.set_footer(text=f"Tanggal: {check_date} • Total perubahan: {len(logs)}")
    return embed

# =====================
# ready
# =====================
@bot.event
async def on_ready():
    print(f"{bot.user} online!")
    if not check_roblox.is_running():
        check_roblox.start()
        print("Roblox monitor started")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(f"Pesan masuk: {message.content} dari {message.author}")
    await bot.process_commands(message)

# =====================
# basic commands
# =====================
@bot.command()
async def ping(ctx):
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{round(bot.latency * 1000)}ms`",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command()
async def clear(ctx, amount: int = 10):
    if ctx.author.id not in ALLOWED_USERS:
        await ctx.send("Lu gak punya akses ❌")
        return
    if amount < 1 or amount > 100:
        await ctx.send("Jumlah harus antara 1-100.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    embed = discord.Embed(
        title="🗑️ Chat Dibersihin",
        description=f"`{len(deleted) - 1}` pesan berhasil dihapus.",
        color=discord.Color.orange()
    )
    confirm = await ctx.send(embed=embed)
    await confirm.delete(delay=3)

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        try:
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
            await channel.connect()
            await ctx.send(f"Masuk ke **{channel}**")
        except Exception as e:
            await ctx.send(f"Gagal masuk voice: {e}")
    else:
        await ctx.send("Masuk voice dulu bang")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Cabut dari voice")

# =====================
# roblox commands
# =====================
@bot.command()
async def addroblox(ctx, user_id: int):
    if ctx.author.id not in ALLOWED_USERS:
        await ctx.message.delete()
        await ctx.send("Lu gak punya akses ❌", delete_after=3)
        return
    await ctx.message.delete()
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)
        embed = discord.Embed(
            title="✅ User Ditambahkan",
            description=f"Roblox ID `{user_id}` berhasil ditambahkan ke monitor.",
            color=discord.Color.green()
        )
        msg = await ctx.send(embed=embed)
        await msg.delete(delay=5)
    else:
        msg = await ctx.send("User sudah ada di daftar.")
        await msg.delete(delay=3)

@bot.command()
async def listroblox(ctx):
    users = load_users()
    await ctx.send(embed=build_list_embed(users))

@bot.command()
async def delroblox(ctx, user_id: int):
    if ctx.author.id not in ALLOWED_USERS:
        await ctx.send("Lu gak punya akses ❌")
        return
    users = load_users()
    if user_id in users:
        users.remove(user_id)
        save_users(users)
        embed = discord.Embed(
            title="🗑️ User Dihapus",
            description=f"Roblox ID `{user_id}` dihapus dari monitor.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("User tidak ditemukan.")

@bot.command()
async def itemroblox(ctx, *, username: str):
    try:
        r = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False}
        )
        data = r.json()

        if not data.get("data"):
            await ctx.send(f"Username `{username}` tidak ditemukan di Roblox.")
            return

        user = data["data"][0]
        uid = user["id"]
        display_name = user.get("displayName", username)
        name = user.get("name", username)
        profile_url = f"https://www.roblox.com/users/{uid}/profile"

        r2 = requests.get(
            f"https://avatar.roblox.com/v1/users/{uid}/currently-wearing",
            cookies={".ROBLOSECURITY": ROBLOX_COOKIE}
        )
        wearing_data = r2.json()
        asset_ids = wearing_data.get("assetIds", [])

        if not asset_ids:
            await ctx.send(f"User `{username}` tidak pakai item apapun atau datanya tidak tersedia.")
            return

        items_detail = []
        for aid in asset_ids:
            try:
                rd = requests.get(f"https://economy.roblox.com/v2/assets/{aid}/details")
                detail = rd.json()
                item_name = detail.get("Name", f"Item {aid}")
                catalog_url = f"https://www.roblox.com/catalog/{aid}"
                items_detail.append({"id": aid, "name": item_name, "url": catalog_url})
            except:
                items_detail.append({"id": aid, "name": f"Item {aid}", "url": f"https://www.roblox.com/catalog/{aid}"})

        ids_param = "&".join([f"assetIds={i['id']}" for i in items_detail])
        r4 = requests.get(
            f"https://thumbnails.roblox.com/v1/assets?{ids_param}&returnPolicy=PlaceHolder&size=150x150&format=Png&isCircular=false"
        )
        thumb_map = {}
        for t in r4.json().get("data", []):
            thumb_map[t["targetId"]] = t.get("imageUrl", "")

        header_embed = discord.Embed(
            title=f"👗 Item yang dipakai — {display_name} (@{name})",
            description=f"[Lihat Profil]({profile_url}) • Total item: `{len(asset_ids)}`",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=header_embed)

        for item in items_detail:
            item_embed = discord.Embed(
                title=item["name"],
                url=item["url"],
                color=discord.Color.blurple()
            )
            thumb_url = thumb_map.get(item["id"], "")
            if thumb_url:
                item_embed.set_thumbnail(url=thumb_url)
            item_embed.set_footer(text=f"Asset ID: {item['id']}")
            await ctx.send(embed=item_embed)

    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.command()
async def avaroblox(ctx, *, username: str):
    try:
        r = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False}
        )
        data = r.json()

        if not data.get("data"):
            await ctx.send(f"Username `{username}` tidak ditemukan di Roblox.")
            return

        user = data["data"][0]
        uid = user["id"]
        display_name = user.get("displayName", username)
        name = user.get("name", username)
        profile_url = f"https://www.roblox.com/users/{uid}/profile"

        r2 = requests.get(
            f"https://thumbnails.roblox.com/v1/users/avatar?userIds={uid}&size=720x720&format=Png&isCircular=false"
        )
        thumb_data = r2.json()
        avatar_url = thumb_data["data"][0]["imageUrl"]

        embed = discord.Embed(
            title=f"{display_name} (@{name})",
            url=profile_url,
            color=discord.Color.blurple()
        )
        embed.set_image(url=avatar_url)
        embed.set_footer(text=f"Roblox ID: {uid}")

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.command()
async def dashboard(ctx):
    global dashboard_message_ids, dashboard_channel_id_active
    if ctx.author.id not in ALLOWED_USERS:
        await ctx.send("Lu gak punya akses ❌")
        return
    users = load_users()
    if not users:
        await ctx.send("Belum ada user yang ditambahkan.")
        return
    try:
        presence_data = get_roblox_presence(users)
        online_friend_ids = get_online_friends()

        dashboard_message_ids = {}
        dashboard_channel_id_active = ctx.channel.id

        presence_map = {u["userId"]: u for u in presence_data}
        for uid in users:
            user = presence_map.get(uid)
            if not user:
                continue
            user_info = get_roblox_user_info(uid)
            status_label, color, emoji, location, _ = resolve_status(user, online_friend_ids)
            embed = build_status_embed(user_info, status_label, color, emoji, location)
            msg = await ctx.send(embed=embed)
            dashboard_message_ids[uid] = msg.id

        print(f"Dashboard dibuat untuk {len(dashboard_message_ids)} user")
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.command()
async def historyroblox(ctx, username: str, tanggal: str = None):
    await ctx.message.delete()

    users = load_users()
    target_uid = None
    for uid in users:
        info = get_roblox_user_info(uid)
        if info["name"].lower() == username.lower():
            target_uid = uid
            break

    if not target_uid:
        msg = await ctx.send(f"Username `{username}` tidak ditemukan di daftar monitor.")
        await msg.delete(delay=5)
        return

    try:
        embed = build_history_embed(target_uid, username, tanggal)
        await ctx.author.send(embed=embed)
    except discord.Forbidden:
        msg = await ctx.send(embed=embed, delete_after=10)

# =====================
# auto monitor + dashboard refresh
# =====================
@tasks.loop(seconds=20)
async def check_roblox():
    global dashboard_message_ids, dashboard_channel_id_active
    users = load_users()
    if not users:
        return
    try:
        presence_data = get_roblox_presence(users)
        online_friend_ids = get_online_friends()
        presence_map = {u["userId"]: u for u in presence_data}

        for user in presence_data:
            uid = user["userId"]
            status_label, color, emoji, location, _ = resolve_status(user, online_friend_ids)

            if location:
                last_location_cache[uid] = location

            if uid not in last_status:
                last_status[uid] = status_label
                continue

            if last_status[uid] != status_label:
                prev = last_status[uid]
                last_status[uid] = status_label

                saved_location = location or last_location_cache.get(uid, "")

                user_info = get_roblox_user_info(uid)
                add_history(uid, user_info["name"], prev, status_label, saved_location)

                if status_label == "Offline":
                    last_location_cache.pop(uid, None)

        if dashboard_message_ids and dashboard_channel_id_active:
            dashboard_channel = bot.get_channel(dashboard_channel_id_active)
            if dashboard_channel:
                for uid, msg_id in list(dashboard_message_ids.items()):
                    user = presence_map.get(uid)
                    if not user:
                        continue
                    try:
                        msg = await dashboard_channel.fetch_message(msg_id)
                        user_info = get_roblox_user_info(uid)
                        status_label, color, emoji, location, _ = resolve_status(user, online_friend_ids)
                        embed = build_status_embed(user_info, status_label, color, emoji, location)
                        await msg.edit(embed=embed)
                        await asyncio.sleep(2)
                    except discord.NotFound:
                        print(f"Dashboard embed untuk {uid} tidak ditemukan, dihapus dari list")
                        del dashboard_message_ids[uid]
                    except Exception as e:
                        print(f"Error update dashboard uid {uid}: {e}")

    except Exception as e:
        print("Error monitor:", e)

@check_roblox.error
async def check_roblox_error(error):
    print(f"check_roblox error, restarting: {error}")
    if not check_roblox.is_running():
        check_roblox.restart()

bot.run(TOKEN)
