import os
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
NOTICE_CHANNEL_ID = int(os.getenv("DISCORD_ADMIN_CHANNEL"))

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ 로그인: {bot.user}")

    channel = bot.get_channel(NOTICE_CHANNEL_ID)

    # 최근 100개 메시지 가져와서 모두 삭제 (필요 시 제한 늘리기)
    async for msg in channel.history(limit=100):
        await msg.delete()
    print("📢 공지 채널 메시지 삭제 완료!")

bot.run(TOKEN)