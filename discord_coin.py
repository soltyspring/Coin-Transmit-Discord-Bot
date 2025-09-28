import json, datetime, os, asyncio, discord
from discord.ext import commands, tasks
from discord import ui, ButtonStyle
from collections import OrderedDict
from web3 import Web3
from datetime import datetime, timezone

from eth_coin import get_erc20_decimals, send_erc20
from sol_coin import get_spl_decimals, send_spl_token
from eth_okx_dex_API import swap_eth_to_token
from sol_okx_dex_API import swap_sol_to_token_instruction
from amount import get_amount_from_tx
from eth_okx_dex_API import get_amount_from_tx_eth

TOKENS_FILE = "tokens.json"
NOTICE_FILE = "airdrop_explorers.json"


# -------------------------------------------------------------------
# 토큰 저장 / 불러오기
# -------------------------------------------------------------------
if os.path.exists(TOKENS_FILE):
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        TOKENS = json.load(f)
else:
    TOKENS = {}

def save_tokens():
    # dict 를 OrderedDict 로 정렬해서 저장
    ordered = OrderedDict(TOKENS)
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)

def add_token_first(symbol: str, data: dict):
    global TOKENS
    # 새 항목을 맨 앞에 삽입
    TOKENS = {symbol.lower(): data, **TOKENS}
    save_tokens()

# -------------------------------------------------------------------
# 디스코드 봇 초기화
# -------------------------------------------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------------------------------------------------
# 신규 토큰 등록 버튼 → RegisterModal 연결
# -------------------------------------------------------------------
class RegisterNewTokenView(discord.ui.View):
    def __init__(self, coin_data: dict):
        super().__init__(timeout=None)
        self.coin_data = coin_data

    @discord.ui.button(label="📥 신규 코인 등록하기", style=discord.ButtonStyle.green)
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RegisterModal(
            chain=self.coin_data["chain"].lower(),
            symbol=self.coin_data["coin"],
            address=self.coin_data["contract"]
        )
        await interaction.response.send_modal(modal)

# 등록용 모달
# -------------------------------------------------------------------
class RegisterModal(discord.ui.Modal, title="코인 등록하기"):
    def __init__(self, chain="", symbol="", address=""):
        super().__init__()
        self.chain_input = discord.ui.TextInput(label="체인 (eth/sol)", default=chain, required=True)
        self.symbol_input = discord.ui.TextInput(label="코인 심볼", default=symbol, required=True)
        self.address_input = discord.ui.TextInput(label="컨트렉 주소", default=address, required=True)

        self.add_item(self.chain_input)
        self.add_item(self.symbol_input)
        self.add_item(self.address_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            chain = self.chain_input.value.lower()
            symbol = self.symbol_input.value
            address = self.address_input.value

            async def delayed_save(symbol, address, decimals, tx_hash, wait_sec, chain):
                await asyncio.sleep(wait_sec)
                print(chain, symbol, address, decimals, tx_hash, wait_sec)
                if chain == "eth":
                    save_amount = get_amount_from_tx_eth(tx_hash, address, decimals)
                    add_token_first(symbol.lower(), {
                        "chain": chain,
                        "address": address,
                        "decimals": decimals,
                        "amount": save_amount
                    })
                    save_tokens()
                else:
                    save_amount = get_amount_from_tx(tx_hash)
                    add_token_first(symbol.lower(), {
                        "chain": chain,
                        "address": address,
                        "decimals": decimals,
                        "amount": save_amount
                    })
                    save_tokens()

                # ✅ 최종 메시지
                if save_amount == 0 or str(save_amount).startswith("0.0"):
                    final_msg = f"⚠️ <@{os.getenv('DISCORD_ADMIN_USER_ID')}> {symbol.upper()} 등록완료 : 1인 전송 수량 0.0"
                else:
                    final_msg = f"✅ {symbol.upper()} 등록완료 : 1인 전송 수량 {save_amount}"

                # 공지 메시지 수정
                try:
                    with open("notice_messages.json", "r", encoding="utf-8") as f:
                        notice_map = json.load(f)

                    msg_id = notice_map.get(symbol.lower())
                    if msg_id:
                        announce_channel = bot.get_channel(int(os.getenv("DISCORD_ANNOUNCE_CHANNEL")))
                        if announce_channel:
                            old_msg = await announce_channel.fetch_message(msg_id)
                            new_embed = old_msg.embeds[0]
                            new_embed.description = final_msg
                            await old_msg.edit(embed=new_embed)
                            print(f"🔄 공지 수정 완료: {symbol.upper()} → {final_msg}")
                except Exception as e:
                    print(f"❌ 공지 수정 실패: {e}")

                # 관리자 채널에도 알림
                admin_channel = bot.get_channel(int(os.getenv("DISCORD_ADMIN_CHANNEL")))
                if admin_channel:
                    await admin_channel.send(final_msg)


            if chain == "eth":
                decimals = get_erc20_decimals(address)
                fixed_amount = 0.00025
                tx_hash = swap_eth_to_token(address, Web3.to_wei(fixed_amount, "ether"))
                msg = f"✅ {symbol.upper()} 등록 및 {fixed_amount} ETH 매수!\n[Etherscan](https://etherscan.io/tx/{tx_hash})"
                await interaction.followup.send(msg)
                asyncio.create_task(delayed_save(symbol, address, decimals, tx_hash, 60, "eth"))

            elif chain == "sol":
                decimals = get_spl_decimals(address)
                fixed_amount = 0.0025
                lamports = int(fixed_amount * 10**9)
                tx_hash = str(swap_sol_to_token_instruction(address, lamports))
                msg = f"✅ {symbol.upper()} 등록 및 {fixed_amount} SOL 매수!\n[Solscan](https://solscan.io/tx/{tx_hash})"
                await interaction.followup.send(msg)
                asyncio.create_task(delayed_save(symbol, address, decimals, tx_hash, 20, "sol"))

            else:
                await interaction.followup.send("❌ 지원하지 않는 체인입니다. (eth/sol)")
        except Exception as e:
            await interaction.followup.send(f"❌ 등록 실패: {str(e)}")





    async def refresh_menus(self, interaction: discord.Interaction):
        """관리자/사용자 채널 메뉴 새로고침"""
        admin_channel = interaction.client.get_channel(int(os.getenv("DISCORD_ADMIN_CHANNEL")))
        user_channel = interaction.client.get_channel(int(os.getenv("DISCORD_USER_CHANNEL")))

        if admin_channel:
            await clear_old_menus(admin_channel)
            view_admin = MainView(is_admin=True)
            msg_admin = await admin_channel.send("⚙️ 관리자용 코인 관리 메뉴", view=view_admin)
            view_admin.menu_message = msg_admin

        if user_channel:
            await clear_old_menus(user_channel)
            view_user = MainView(is_admin=False)
            msg_user = await user_channel.send("📤 코인을 전송하려면 클릭하세요:", view=view_user)
            view_user.menu_message = msg_user




# -------------------------------------------------------------------
# 전송용 모달
# -------------------------------------------------------------------
class WalletModal(discord.ui.Modal, title="받는 지갑 주소 입력"):
    wallet = discord.ui.TextInput(label="받는 지갑 주소", required=True)

    def __init__(self, token_symbol: str, parent_message: discord.Message, is_admin: bool):
        super().__init__()
        self.token_symbol = token_symbol
        self.parent_message = parent_message
        self.is_admin = is_admin

    async def on_submit(self, interaction: discord.Interaction):
        token = TOKENS[self.token_symbol]
        amount_value = token["amount"]

        try:
            if token["chain"] == "eth":
                tx_hash = send_erc20(token["address"], self.wallet.value, amount_value, token["decimals"])
                result_msg = (
                    f"🤗 {interaction.user.mention}\n"
                    f"  {amount_value} {self.token_symbol.upper()} 전송 완료!\n"
                    f"[트랜잭션 확인](https://etherscan.io/tx/{tx_hash})"
                )

            elif token["chain"] == "sol":
                sig = send_spl_token(token["address"], self.wallet.value, amount_value, token["decimals"])
                result_msg = (
                    f"🤗 {interaction.user.mention}\n"
                    f"  {amount_value} {self.token_symbol.upper()} 전송 완료!\n"
                    f"[트랜잭션 확인](https://explorer.solana.com/tx/{sig}?cluster=mainnet-beta)"
                )
            else:
                result_msg = "❌ 지원하지 않는 체인입니다."

        except Exception as e:
            result_msg = f"❌ 전송 실패: {str(e)}"

        # ✅ 결과 메시지 (공개 메시지)
        await interaction.response.send_message(result_msg)

        # ✅ 이전 메뉴 삭제
        try:
            await self.parent_message.delete()
        except Exception:
            pass

        # ✅ 새 메뉴 띄우기
        channel = interaction.channel
        view = MainView(is_admin=self.is_admin)
        msg = await channel.send("📤 코인을 전송하려면 클릭하세요:", view=view)
        view.menu_message = msg

# -------------------------------------------------------------------
# 버튼 UI
# -------------------------------------------------------------------
class MainView(discord.ui.View):
    def __init__(self, is_admin=False):
        super().__init__(timeout=None)
        self.is_admin = is_admin
        self.menu_message: discord.Message | None = None

        # ✅ 토큰마다 버튼 생성
        for symbol in TOKENS.keys():
            self.add_item(self.TokenButton(symbol, self))

        # ✅ 관리자 전용 버튼
        if self.is_admin:
            self.add_item(self.RegisterButton())

    class TokenButton(discord.ui.Button):
        def __init__(self, symbol, parent_view):
            super().__init__(
                label=f"📤 {symbol.upper()} 전송",
                style=discord.ButtonStyle.blurple
            )
            self.symbol = symbol
            self.parent_view = parent_view

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_modal(
                WalletModal(self.symbol, self.parent_view.menu_message, self.parent_view.is_admin)
            )

    class RegisterButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="📥 코인 등록 (관리자 전용)", style=discord.ButtonStyle.green)

        async def callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 이 기능은 관리자 전용입니다.", ephemeral=True)
                return
            await interaction.response.send_modal(RegisterModal())
# -------------------------------------------------------------------
# 신규 공지 체크 로직 (한 번 실행)
# -------------------------------------------------------------------
# 👇 run_check_new_notices 안에 embed 전송 직전에 버튼 view 추가
from discord import ui

class DepositView(ui.View):
    def __init__(self, coin_name: str, deposit_url: str):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label=f"👉 {coin_name} 입금하기 👈", url=deposit_url, style=ButtonStyle.link))

# 공지 처리 공통 함수
# -------------------------------------------------------------------
async def process_notices():
    if not os.path.exists(NOTICE_FILE):
        return
    with open(NOTICE_FILE, "r", encoding="utf-8") as f:
        notices = json.load(f)

    announce_channel = bot.get_channel(int(os.getenv("DISCORD_ANNOUNCE_CHANNEL")))
    admin_channel = bot.get_channel(int(os.getenv("DISCORD_ADMIN_CHANNEL")))

    notice_map = {}
    if os.path.exists("notice_messages.json"):
        with open("notice_messages.json", "r", encoding="utf-8") as f:
            notice_map = json.load(f)

    for event in notices:
        for coin in event["coins"]:
            symbol = coin["coin"].lower()
            deposit_url = f"https://www.bithumb.com/react/inout/deposit/{coin['coin']}"

            # 이미 등록된 경우 건너뜀
            if symbol in notice_map:
                continue

            # ✅ 최초 Embed (등록 대기 메시지)
            embed = discord.Embed(
                title=f"🚀 **빗썸 {coin['coin']} 신규 에어드랍** 🚀",
                description="⏳ 등록 완료까지 20초~60초 소요",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="이벤트",
                value=f"[{event['event_title']}]({event['event_url']})",
                inline=False
            )

            chain = coin["chain"].lower()
            if chain == "eth":
                scan_url = f"https://etherscan.io/token/{coin['contract']}"
            elif chain == "sol":
                scan_url = f"https://solscan.io/token/{coin['contract']}"
            else:
                scan_url = coin["contract"]

            embed.add_field(
                name="컨트랙트",
                value=f"[{coin['contract']}]({scan_url})",
                inline=False
            )

            # ✅ 입금 버튼 생성
            deposit_view = DepositView(coin["coin"], deposit_url)

            # 사용자 채널 → 최초 공지 전송
            if announce_channel:
                msg = await announce_channel.send(embed=embed, view=deposit_view)
                notice_map[symbol] = msg.id
                with open("notice_messages.json", "w", encoding="utf-8") as f:
                    json.dump(notice_map, f, indent=2, ensure_ascii=False)

            # 관리자 채널 → 등록 버튼 + 입금 버튼 같이 전송
            if admin_channel:
                view = RegisterNewTokenView(coin)
                for item in deposit_view.children:
                    view.add_item(item)
                await admin_channel.send(embed=embed, view=view)




# -------------------------------------------------------------------
# 기존 메뉴 메시지 삭제 함수
# -------------------------------------------------------------------
async def clear_old_menus(channel: discord.TextChannel):
    async for msg in channel.history(limit=None):  # ✅ limit=None → 전부 확인
        if msg.author == bot.user and (
            "⚙️ 관리자용 코인 관리 메뉴" in msg.content
            or "📤 코인을 전송하려면 클릭하세요:" in msg.content
        ):
            try:
                await msg.delete()
                print(f"🗑️ 이전 메뉴 메시지 삭제: {msg.content}")
            except Exception as e:
                print(f"❌ 메시지 삭제 실패: {e}")


# -------------------------------------------------------------------
# 봇 실행
# -------------------------------------------------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 로그인 완료: {bot.user}")

    # 초기 메뉴 + 공지 실행
    await process_notices()

    # ✅ 루프 시작은 여기서만
    if not check_new_notices.is_running():
        check_new_notices.start()

    # 관리자 / 사용자 채널 메뉴 초기화
    admin_channel = bot.get_channel(int(os.getenv("DISCORD_ADMIN_CHANNEL")))
    user_channel = bot.get_channel(int(os.getenv("DISCORD_USER_CHANNEL")))

    if admin_channel:
        await clear_old_menus(admin_channel)
        view = MainView(is_admin=True)
        msg = await admin_channel.send("⚙️ 관리자용 코인 관리 메뉴", view=view)
        view.menu_message = msg
        print("📨 관리자 채널에 새 메뉴 전송 완료")

    if user_channel:
        await clear_old_menus(user_channel)
        view = MainView(is_admin=False)
        msg = await user_channel.send("📤 코인을 전송하려면 클릭하세요:", view=view)
        view.menu_message = msg
        print("📨 사용자 채널에 새 메뉴 전송 완료")




@tasks.loop(minutes=10)
async def check_new_notices():
    await process_notices()


@check_new_notices.before_loop
async def before_check_new_notices():
    await bot.wait_until_ready()
    print("⏳ check_new_notices 준비 완료")

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("❌ DISCORD_BOT_TOKEN 환경 변수가 필요합니다.")
    bot.run(TOKEN)