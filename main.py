import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import os, json, re

TOKEN = os.getenv("TOKEN")  # cấu hình trong Railway/Replit

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === ID kênh ===
target_channel_id = 1395784873708486656      # kênh cần bật/tắt quyền xem
announce_channel_id = 1402130773418442863    # kênh DUY NHẤT để bot gửi thông báo/phan hồi

# === File lưu lịch để không mất khi restart ===
SCHEDULE_FILE = "schedules.json"

# === NHÓM ĐỒNG BỘ LỊCH ===
# Mọi user trong cùng một tuple sẽ luôn có lịch giống nhau.
LINK_GROUPS = [
    (1288889343628541994, 994084789697134592),
]

# ---------- Helpers: JSON schedules ----------
def load_schedules():
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {int(k): [(int(a), int(b)) for a, b in v] for k, v in data.items()}
    except Exception:
        # lịch mặc định
        return {
            994084789697134592: [(4, 7), (15, 18)],
            1288889343628541994: [(4, 7), (15, 18)],
            1284898656415125586: [(11, 15), (21, 24)],
            1134008850895343667: [(0, 4)],
            960787999833079881: [(7, 11), (18, 21)],
        }

def save_schedules():
    try:
        serializable = {str(k): list(map(list, v)) for k, v in user_schedules.items()}
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Không thể lưu schedules: {e}")

user_schedules = load_schedules()

# ---------- Helpers: logic ----------
def is_within_time_range(hour: int, ranges):
    return any(start <= hour < end for start, end in ranges)

def parse_ranges(text: str):
    """
    Nhận '4-7,15-18' -> [(4,7),(15,18)]
    """
    text = text.strip()
    if not text:
        raise ValueError("Chuỗi trống.")
    parts = [p.strip() for p in text.split(",")]
    ranges = []
    for part in parts:
        m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", part)
        if not m:
            raise ValueError(f"Định dạng sai: '{part}'. Dùng dạng '4-7,15-18'")
        a, b = int(m.group(1)), int(m.group(2))
        if not (0 <= a <= 24 and 0 <= b <= 24):
            raise ValueError(f"Giờ phải trong khoảng 0–24: '{part}'")
        if not (a < b):
            raise ValueError(f"Giờ bắt đầu phải < giờ kết thúc: '{part}'")
        ranges.append((a, b))
    return ranges

def get_linked_users(user_id: int):
    """
    Trả về tập tất cả user trong cùng nhóm liên kết với user_id (bao gồm chính nó).
    Nếu không thuộc nhóm nào, trả về {user_id}.
    """
    for group in LINK_GROUPS:
        if user_id in group:
            return set(group)
    return {user_id}

def format_ranges(ranges):
    return ", ".join([f"{a}h-{b}h" for a, b in ranges])

def vn_now():
    return datetime.utcnow() + timedelta(hours=7)

# ---------- Helpers: embeds ----------
def embed_open(member_mention: str, channel_id: int, now_dt: datetime):
    e = discord.Embed(
        title="✅ Quyền Truy Cập ĐÃ MỞ",
        description=f"{member_mention} đã được **mở quyền xem** kênh <#{channel_id}>.",
        color=discord.Color.green()
    )
    e.set_footer(text=f"Thời gian: {now_dt.strftime('%H:%M')}")
    return e

def embed_close(member_mention: str, channel_id: int, now_dt: datetime):
    e = discord.Embed(
        title="⛔ Quyền Truy Cập ĐÃ ẨN",
        description=f"{member_mention} đã bị **ẩn quyền xem** kênh <#{channel_id}>.",
        color=discord.Color.red()
    )
    e.set_footer(text=f"Thời gian: {now_dt.strftime('%H:%M')}")
    return e

def embed_set_single(member_mention: str, ranges, applied_now: bool):
    e = discord.Embed(
        title="🛠 Cập Nhật Lịch Truy Cập",
        description=f"Đã cập nhật lịch cho {member_mention}\n**Khoảng:** {format_ranges(ranges)}",
        color=discord.Color.blurple()
    )
    if applied_now:
        e.add_field(name="Áp dụng ngay", value="✅ Đã set quyền tương ứng với giờ hiện tại", inline=False)
    return e

def embed_set_group(members_mentions: str, ranges, applied_now: bool):
    e = discord.Embed(
        title="🛠 Cập Nhật Lịch (Đồng Bộ Nhóm)",
        description=f"Đã cập nhật lịch cho: {members_mentions}\n**Khoảng:** {format_ranges(ranges)}",
        color=discord.Color.gold()
    )
    if applied_now:
        e.add_field(name="Áp dụng ngay", value="✅ Đã set quyền cho toàn bộ nhóm theo giờ hiện tại", inline=False)
    return e

def embed_auto_off(now_dt: datetime, channel_id: int):
    e = discord.Embed(
        title="❌ AutoJoiner đã tắt",
        description=f"Đã **tắt quyền xem** cho AutoJoiner tại kênh <#{channel_id}>.",
        color=discord.Color.red()
    )
    e.set_footer(text=f"Thời gian: {now_dt.strftime('%H:%M')}")
    return e

def embed_auto_on(now_dt: datetime, channel_id: int):
    e = discord.Embed(
        title="✅ AutoJoiner đã bật",
        description=f"Đã **bật quyền xem** cho AutoJoiner tại kênh <#{channel_id}>.",
        color=discord.Color.green()
    )
    e.set_footer(text=f"Thời gian: {now_dt.strftime('%H:%M')}")
    return e

# ---------- Vòng lặp cập nhật quyền mỗi phút ----------
@tasks.loop(minutes=1)
async def update_permissions():
    now = vn_now()
    hour = now.hour
    guild = discord.utils.get(bot.guilds)
    if not guild:
        return

    channel = guild.get_channel(target_channel_id)
    announce_channel = guild.get_channel(announce_channel_id)

    for user_id, schedule in user_schedules.items():
        member = guild.get_member(user_id)
        if not member or not channel:
            continue

        can_view = is_within_time_range(hour, schedule)
        current_perm = channel.overwrites_for(member)
        current_state = current_perm.view_channel

        if current_state != can_view:
            overwrite = discord.PermissionOverwrite()
            overwrite.view_channel = can_view
            await channel.set_permissions(member, overwrite=overwrite)

            if announce_channel:
                if can_view:
                    await announce_channel.send(embed=embed_open(member.mention, target_channel_id, now))
                else:
                    await announce_channel.send(embed=embed_close(member.mention, target_channel_id, now))

# ---------- Lệnh xem lịch tổng ----------
@bot.command()
async def xemlich(ctx):
    e = discord.Embed(
        title="📅 Lịch Truy Cập",
        color=discord.Color.blue(),
        timestamp=vn_now()
    )
    for uid, schedule in user_schedules.items():
        e.add_field(name=f"<@{uid}>", value=format_ranges(schedule), inline=False)

    announce_channel = ctx.guild.get_channel(announce_channel_id)
    if announce_channel:
        await announce_channel.send(embed=e)

# ---------- Lệnh xem lịch 1 người ----------
@bot.command()
async def lich(ctx, user: discord.Member = None):
    if user is None:
        # gửi nhắc sử dụng đúng CŨNG vào kênh chỉ định
        announce_channel = ctx.guild.get_channel(announce_channel_id)
        if announce_channel:
            await announce_channel.send("⚠️ Dùng: `!lich @user` hoặc `!lich USER_ID`")
        return

    schedule = user_schedules.get(user.id)
    announce_channel = ctx.guild.get_channel(announce_channel_id)
    if not schedule:
        if announce_channel:
            await announce_channel.send(f"ℹ️ {user.mention} **chưa có lịch**.")
        return

    if announce_channel:
        await announce_channel.send(embed=embed_set_single(user.mention, schedule, applied_now=False))

# ---------- Lệnh SET lịch (admin) – đồng bộ nếu thuộc nhóm ----------
@bot.command()
@commands.has_permissions(administrator=True)
async def setlich(ctx, user: discord.Member = None, *, ranges_text: str = None):
    if user is None or not ranges_text:
        ch = ctx.guild.get_channel(announce_channel_id)
        if ch:
            await ch.send("⚠️ Dùng: `!setlich @user 4-7,15-18` hoặc `!setlich USER_ID 7-11`")
        return

    try:
        ranges = parse_ranges(ranges_text)
    except ValueError as e:
        ch = ctx.guild.get_channel(announce_channel_id)
        if ch:
            await ch.send(f"❌ {e}")
        return

    linked_users = get_linked_users(user.id)

    # Cập nhật lịch (cho nhóm hoặc 1 người)
    for uid in linked_users:
        user_schedules[uid] = ranges
    save_schedules()

    # Áp dụng ngay
    guild = ctx.guild
    channel = guild.get_channel(target_channel_id)
    now = vn_now()
    hour = now.hour
    applied_now = False

    if channel:
        for uid in linked_users:
            member = guild.get_member(uid)
            if not member:
                continue
            can_view = is_within_time_range(hour, ranges)
            overwrite = discord.PermissionOverwrite()
            overwrite.view_channel = can_view
            await channel.set_permissions(member, overwrite=overwrite)
            applied_now = True

    # Gửi 1 nơi DUY NHẤT: kênh announce_channel_id
    ch = guild.get_channel(announce_channel_id)
    if ch:
        if len(linked_users) > 1:
            mentions_str = ", ".join([f"<@{uid}>" for uid in linked_users])
            await ch.send(embed=embed_set_group(mentions_str, ranges, applied_now))
        else:
            await ch.send(embed=embed_set_single(user.mention, ranges, applied_now))

# ---------- Lệnh tắt/bật quyền cho AutoJoiner ----------
@bot.command()
async def tatauto(ctx):
    guild = ctx.guild
    member = guild.get_member(1386358388497059882)
    channel = guild.get_channel(target_channel_id)
    announce_channel = guild.get_channel(announce_channel_id)
    now = vn_now()

    if not member or not channel:
        if announce_channel:
            await announce_channel.send("⚠️ Không tìm thấy thành viên hoặc channel.")
        return

    overwrite = discord.PermissionOverwrite()
    overwrite.view_channel = False
    await channel.set_permissions(member, overwrite=overwrite)

    if announce_channel:
        await announce_channel.send(embed=embed_auto_off(now, target_channel_id))

@bot.command()
async def batauto(ctx):
    guild = ctx.guild
    member = guild.get_member(1386358388497059882)
    channel = guild.get_channel(target_channel_id)
    announce_channel = guild.get_channel(announce_channel_id)
    now = vn_now()

    if not member or not channel:
        if announce_channel:
            await announce_channel.send("⚠️ Không tìm thấy thành viên hoặc channel.")
        return

    overwrite = discord.PermissionOverwrite()
    overwrite.view_channel = True
    await channel.set_permissions(member, overwrite=overwrite)

    if announce_channel:
        await announce_channel.send(embed=embed_auto_on(now, target_channel_id))

# ---------- Ready ----------
@bot.event
async def on_ready():
    print(f"✅ Bot đã online: {bot.user}")
    update_permissions.start()

bot.run(TOKEN)

