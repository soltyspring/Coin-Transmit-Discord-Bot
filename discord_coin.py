import discord
from discord import app_commands
from discord.ext import commands
import os, json
from dotenv import load_dotenv
from datetime import datetime

# Solana 모듈
from sol_coin import send_spl_token, format_amount, get_spl_decimals
# Ethereum 모듈
from eth_coin import send_erc20, get_erc20_decimals

# -------------------------------------------------------------------
# ⚙️ 설정
# -------------------------------------------------------------------
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TOKENS_FILE = "tokens.json"

# 하루 사용 제한
USAGE_LIMIT = {}  # {user_id: {"count": int, "date": str}}
MAX_USAGE = 3     # 하루 3번

def check_usage(user_id: int) -> bool:
    today = datetime.utcnow().date().isoformat()
    record = USAGE_LIMIT.get(user_id)

    if record is None or record["date"] != today:
        USAGE_LIMIT[user_id] = {"count": 0, "date": today}

    if USAGE_LIMIT[user_id]["count"] >= MAX_USAGE:
        return False

    USAGE_LIMIT[user_id]["count"] += 1
    return True


# -------------------------------------------------------------------
# 🔹 토큰 저장/로드
# -------------------------------------------------------------------
def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

TOKENS = load_tokens()


# -------------------------------------------------------------------
# 🤖 디스코드 봇
# -------------------------------------------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"🔗 Slash commands synced: {len(synced)}개")
    except Exception as e:
        print(f"❌ Sync 실패: {e}")


# -------------------------------------------------------------------
# 🔹 관리자 전용 체크
# -------------------------------------------------------------------
def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


# -------------------------------------------------------------------
# 🔹 토큰 등록 (decimals 자동 감지)
# -------------------------------------------------------------------
@tree.command(name="registertoken", description="토큰 등록 (관리자 전용, decimals 자동 감지)")
@is_admin()
async def registertoken(
    interaction: discord.Interaction,
    chain: str,      # sol / eth
    name: str,       # 토큰 이름
    address: str,    # Mint 주소(솔라나) 또는 컨트랙트 주소(이더리움)
    amount: float    # 기본 전송 수량
):
    chain = chain.lower()
    if chain not in ["sol", "eth"]:
        await interaction.response.send_message("❌ chain 값은 `sol` 또는 `eth` 만 가능합니다.")
        return

    try:
        if chain == "sol":
            decimals = get_spl_decimals(address)
        else:
            decimals = get_erc20_decimals(address)
    except Exception as e:
        await interaction.response.send_message(f"❌ Decimals 자동 감지 실패: {e}")
        return

    TOKENS[name] = {
        "chain": chain,
        "address": address,
        "decimals": decimals,
        "amount": amount
    }
    save_tokens(TOKENS)

    await interaction.response.send_message(
        f"✅ 토큰 등록 완료!\n"
        f"체인: `{chain}`\n이름: `{name}`\n주소: `{address}`\nDecimals: `{decimals}`\nAmount: `{amount}`"
    )


# -------------------------------------------------------------------
# 🔹 Modal (지갑주소 입력)
# -------------------------------------------------------------------
class WalletModal(discord.ui.Modal, title="지갑 주소 입력"):
    wallet = discord.ui.TextInput(label="받는 지갑 주소", required=True)

    def __init__(self, name: str, data: dict):
        super().__init__()
        self.name = name
        self.data = data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.data["chain"] == "sol":
                sig = send_spl_token(
                    self.data["address"],
                    str(self.wallet),
                    self.data["amount"],
                    self.data["decimals"]
                )
                link = f"https://solscan.io/tx/{sig}"
            else:  # eth
                sig = send_erc20(
                    self.data["address"],
                    str(self.wallet),
                    self.data["amount"],
                    self.data["decimals"]
                )
                link = f"https://etherscan.io/tx/{sig}"

            await interaction.response.send_message(
                f"✅ {self.data['amount']} {self.name} 전송 완료!\n[트랜잭션 확인]({link})"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 전송 실패: {e}")


# -------------------------------------------------------------------
# 🔹 드롭다운 (토큰 선택)
# -------------------------------------------------------------------
class TokenSelect(discord.ui.View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=60)
        self.author = author

        options = [
            discord.SelectOption(
                label=name,
                description=f"{format_amount(data['amount'], data['decimals'])}개 전송",
                value=name
            )
            for name, data in TOKENS.items()
        ]

        self.select = discord.ui.Select(
            placeholder="코인을 선택하세요",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("❌ 이 메뉴는 당신이 사용할 수 없습니다.", ephemeral=True)
            return

        name = self.select.values[0]
        data = TOKENS[name]
        await interaction.response.send_modal(WalletModal(name, data))


# -------------------------------------------------------------------
# 🔹 /send (하루 3회 제한)
# -------------------------------------------------------------------
@tree.command(name="send", description="토큰 전송 (드롭다운 선택 → 지갑주소 입력)")
async def send(interaction: discord.Interaction):
    if not check_usage(interaction.user.id):
        await interaction.response.send_message("❌ 하루 사용 가능 횟수(3회)를 모두 사용했습니다.", ephemeral=True)
        return

    if not TOKENS:
        await interaction.response.send_message("❌ 등록된 토큰이 없습니다. `/registertoken` 먼저 실행하세요.")
        return

    await interaction.response.send_message(
        "📌 전송할 코인을 선택하세요:",
        view=TokenSelect(interaction.user)
    )


# -------------------------------------------------------------------
# 실행
# -------------------------------------------------------------------
bot.run(DISCORD_TOKEN)
