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

# === Cấu hình ID kênh ===
target_channel_id = 1395784873708486656  # kênh cần bật/tắt quyền xem
log_channel_id = 1402130773418442863     # kênh để gửi thông báo/log

# === File lưu lịch để không mất khi restart ===
SCHEDULE_FILE = "schedules.json"

# === NHÓM ĐỒNG BỘ LỊCH ===
# Mọi user trong cùng một tuple sẽ luôn có lịch giống nhau.
LINK_GROUPS = [
    (1288889343628541994, 994084789697134592),  # <@1288889343628541994> <-> <@994084789697134592>
]

def load_schedules():
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {int(k): [(int(a), int(b)) for a, b in v] for k, v in data.items()}
    except Exception:
        # lịch mặc định
        return {
            994084789697134592: [(4, 7), (15, 18)],            # A
            1288889343628541994: [(4, 7), (15, 18)],           # B (đồng bộ với A)
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

# === Helpers ===
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

# === Cập nhật quyền mỗi phút (giờ VN) ===
@tasks.loop(minutes=1)
async def update_permissions():
    now = datetime.utcnow() + timedelta(hours=7)
    hour = now.hour
    guild = discord.utils.get(bot.guilds)
    if not guild:
        return
    channel = guild.get_channel(target_channel_id)
    log_channel = guild.get_channel(log_channel_id)

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

            if log_channel:
                status = "✅ **ĐÃ MỞ**" if can_view else "⛔ **ĐÃ ẨN**"
                await log_channel.send(
                    f"{status} quyền xem channel cho <@{user_id}> lúc `{now.strftime('%H:%M')}`"
                )

# === Lệnh xem lịch tổng ===
@bot.command()
async def xemlich(ctx):
    embed = discord.Embed(
        title="📅 Lịch Truy Cập",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow() + timedelta(hours=7)
    )
    for uid, schedule in user_schedules.items():
        ranges = [f"{start}h - {end}h" for start, end in schedule]
        user_name = f"<@{uid}>"
        embed.add_field(name=user_name, value=", ".join(ranges), inline=False)
    await ctx.send(embed=embed)

# === Lệnh xem lịch 1 người: !lich @user / !lich 123456789 ===
@bot.command()
async def lich(ctx, user: discord.Member = None):
    if user is None:
        await ctx.send("⚠️ Dùng: `!lich @user` hoặc `!lich USER_ID`")
        return
    uid = user.id
    schedule = user_schedules.get(uid)
    if not schedule:
        await ctx.send(f"ℹ️ {user.mention} **chưa có lịch**.")
        return
    ranges = ", ".join([f"{a}h-{b}h" for a, b in schedule])
    await ctx.send(f"📅 Lịch của {user.mention}: {ranges}")

# === Lệnh SET lịch: chỉ admin; tự ĐỒNG BỘ nhóm liên kết ===
@bot.command()
@commands.has_permissions(administrator=True)
async def setlich(ctx, user: discord.Member = None, *, ranges_text: str = None):
    """
    Ví dụ:
    !setlich @user 4-7,15-18
    !setlich 1234567890 7-11
    """
    if user is None or not ranges_text:
        await ctx.send("⚠️ Dùng: `!setlich @user 4-7,15-18` hoặc `!setlich USER_ID 7-11`")
        return

    try:
        ranges = parse_ranges(ranges_text)
    except ValueError as e:
        await ctx.send(f"❌ {e}")
        return

    # Tìm nhóm liên kết (nếu có)
    linked_users = get_linked_users(user.id)

    # Cập nhật lịch cho toàn bộ nhóm
    for uid in linked_users:
        user_schedules[uid] = ranges

    save_schedules()

    # Áp dụng ngay: set permission theo giờ hiện tại cho cả nhóm
    guild = ctx.guild
    channel = guild.get_channel(target_channel_id)
    log_channel = guild.get_channel(log_channel_id)
    now = datetime.utcnow() + timedelta(hours=7)
    hour = now.hour
    status_texts = []

    if channel:
        for uid in linked_users:
            member = guild.get_member(uid)
            if not member:
                continue
            can_view = is_within_time_range(hour, ranges)
            overwrite = discord.PermissionOverwrite()
            overwrite.view_channel = can_view
            await channel.set_permissions(member, overwrite=overwrite)
            status = "✅ **ĐÃ MỞ**" if can_view else "⛔ **ĐÃ ẨN**"
            status_texts.append(f"{status} <@{uid}>")

        # Gửi log tóm tắt
        if log_channel and status_texts:
            await log_channel.send(
                "🛠 **Đã cập nhật lịch (đồng bộ nhóm)**: "
                + ", ".join([f"<@{uid}>" for uid in linked_users]) + "\n"
                + "Khoảng: " + ", ".join([f"{a}h-{b}h" for a, b in ranges]) + "\n"
                + f"Áp dụng ngay lúc `{now.strftime('%H:%M')}` → "
                + "; ".join(status_texts)
            )

    # Phản hồi tại kênh gọi lệnh
    await ctx.send(
        "✅ Đã đặt lịch (đồng bộ nhóm) cho: "
        + ", ".join([f"<@{uid}>" for uid in linked_users])
        + f" → " + ", ".join([f"{a}h-{b}h" for a, b in ranges])
    )

# === Lệnh tắt/bật quyền cho AutoJoiner ===
@bot.command()
async def tatauto(ctx):
    guild = ctx.guild
    member = guild.get_member(1386358388497059882)
    channel = guild.get_channel(target_channel_id)
    log_channel = guild.get_channel(log_channel_id)

    if not member or not channel:
        await ctx.send("⚠️ Không tìm thấy thành viên hoặc channel.")
        return

    overwrite = discord.PermissionOverwrite()
    overwrite.view_channel = False
    await channel.set_permissions(member, overwrite=overwrite)

    if log_channel:
        await log_channel.send("❌ AutoJoiner đã tắt")

    await ctx.send("✅ Đã tắt quyền xem channel cho AutoJoiner.")

@bot.command()
async def batauto(ctx):
    guild = ctx.guild
    member = guild.get_member(1386358388497059882)
    channel = guild.get_channel(target_channel_id)
    log_channel = guild.get_channel(log_channel_id)

    if not member or not channel:
        await ctx.send("⚠️ Không tìm thấy thành viên hoặc channel.")
        return

    overwrite = discord.PermissionOverwrite()
    overwrite.view_channel = True
    await channel.set_permissions(member, overwrite=overwrite)

    if log_channel:
        await log_channel.send("✅ AutoJoiner đã được bật")

    await ctx.send("✅ Đã bật quyền xem channel cho AutoJoiner.")

# === Ready ===
@bot.event
async def on_ready():
    print(f"✅ Bot đã online: {bot.user}")
    update_permissions.start()

bot.run(TOKEN)
