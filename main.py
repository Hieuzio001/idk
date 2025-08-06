import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import os

TOKEN = os.getenv("TOKEN")  # Token của bạn sẽ cấu hình trong Railway sau

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Gán thông tin ID
target_channel_id = 1395784873708486656  # Channel để bật/tắt view
log_channel_id = 1402130773418442863     # Channel để gửi thông báo

# Lịch truy cập của từng user
user_schedules = {
    994084789697134592: [(4, 7), (15, 18)],
    1284898656415125586: [(11, 15), (21, 24)],
    1134008850895343667: [(0, 4)],
    960787999833079881: [(7, 11), (18, 21)],
}

def is_within_time_range(hour, ranges):
    return any(start <= hour < end for start, end in ranges)

@tasks.loop(minutes=1)
async def update_permissions():
    now = datetime.utcnow() + timedelta(hours=7)
    hour = now.hour
    guild = discord.utils.get(bot.guilds)
    channel = guild.get_channel(target_channel_id)
    log_channel = guild.get_channel(log_channel_id)

    for user_id, schedule in user_schedules.items():
        member = guild.get_member(user_id)
        if not member or not channel:
            continue

        can_view = is_within_time_range(hour, schedule)
        current_perm = channel.overwrites_for(member)

        if current_perm.view_channel != can_view:
            overwrite = discord.PermissionOverwrite()
            overwrite.view_channel = can_view
            await channel.set_permissions(member, overwrite=overwrite)
            if log_channel:
                status = "✅ **ĐÃ MỞ**" if can_view else "⛔ **ĐÃ ẨN**"
                await log_channel.send(
                    f"{status} quyền xem channel cho <@{user_id}> lúc `{now.strftime('%H:%M')}`"
                )

@bot.command()
async def xemlich(ctx):
    embed = discord.Embed(title="📅 Lịch Truy Cập", color=0x2ecc71)
    for uid, schedule in user_schedules.items():
        ranges = [f"{start}h - {end}h" for start, end in schedule]
        embed.add_field(name=f"<@{uid}>", value=", ".join(ranges), inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Bot đã online: {bot.user}")
    update_permissions.start()

bot.run(TOKEN)
