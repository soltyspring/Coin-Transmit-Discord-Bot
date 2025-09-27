import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

from discord_coin import MainView  # ✅ 기존에 작성한 View 불러오기

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ 로그인 완료: {bot.user}")

    admin_channel_id = int(os.getenv("DISCORD_ADMIN_CHANNEL"))
    user_channel_id = int(os.getenv("DISCORD_USER_CHANNEL"))

    admin_channel = bot.get_channel(admin_channel_id)
    user_channel = bot.get_channel(user_channel_id)

    # 관리자 채널 초기화
    if admin_channel:
        await admin_channel.purge(limit=None)
        view = MainView(is_admin=True)
        msg = await admin_channel.send("⚙️ 관리자용 코인 관리 메뉴", view=view)
        view.menu_message = msg
        print("📨 관리자 채널 초기화 및 메뉴 전송 완료")
    else:
        print("❌ 관리자 채널을 찾을 수 없습니다")

    # 사용자 채널 초기화
    if user_channel:
        await user_channel.purge(limit=None)
        view = MainView(is_admin=False)
        msg = await user_channel.send("📤 코인을 전송하려면 클릭하세요:", view=view)
        view.menu_message = msg
        print("📨 사용자 채널 초기화 및 메뉴 전송 완료")
    else:
        print("❌ 사용자 채널을 찾을 수 없습니다")

    # ✅ 초기화 후 봇 자동 종료 (원하면 유지도 가능)
    await bot.close()


if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("❌ DISCORD_BOT_TOKEN 환경 변수가 필요합니다.")
    bot.run(TOKEN)
