import os
import json
import base58
from dotenv import load_dotenv

from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.transaction import Transaction
from solders.message import Message
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction as TransactionInstruction, AccountMeta
from solders.sysvar import RENT
from solders.system_program import ID as SYS_PROGRAM_ID
from spl.token.instructions import transfer, TransferParams
from spl.token.constants import (
    TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
)

# -------------------------------------------------------------------
# ⚙️ 설정
# -------------------------------------------------------------------
load_dotenv()
SOL_PRIVATE_KEY = os.getenv("SOL_PRIVATE_KEY")

# 개인키 로드
secret = base58.b58decode(SOL_PRIVATE_KEY)
kp = Keypair.from_bytes(secret)
client = Client("https://api.mainnet-beta.solana.com")

# 토큰 데이터 저장 파일
TOKENS_FILE = "tokens.json"


# -------------------------------------------------------------------
# 🔹 유틸 함수
# -------------------------------------------------------------------
def format_amount(amount: float, decimals: int = 9) -> str:
    return f"{amount:.{decimals}f}".rstrip("0").rstrip(".")


def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


# -------------------------------------------------------------------
# 🔹 ATA 계산
# -------------------------------------------------------------------
def derive_ata(owner: Pubkey, mint: Pubkey, token_program_id: Pubkey) -> Pubkey:
    seeds = [bytes(owner), bytes(token_program_id), bytes(mint)]
    ata, _ = Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)
    return ata

def create_associated_token_account_idempotent(
    payer: Pubkey,
    owner: Pubkey,
    mint: Pubkey,
    token_program_id: Pubkey,
):
    ata = derive_ata(owner, mint, token_program_id)
    keys = [
        AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
        AccountMeta(pubkey=ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner, is_signer=False, is_writable=False),
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=RENT, is_signer=False, is_writable=False),
    ]
    return TransactionInstruction(
        program_id=ASSOCIATED_TOKEN_PROGRAM_ID,
        accounts=keys,
        data=bytes([1]),
    )


# -------------------------------------------------------------------
# 🔹 Token Program 자동 감지
# -------------------------------------------------------------------
def detect_token_program(mint: Pubkey) -> Pubkey:
    resp = client.get_account_info(mint)
    if not resp.value:
        raise ValueError("❌ Mint account not found")
    owner = resp.value.owner
    if owner == TOKEN_2022_PROGRAM_ID:
        return TOKEN_2022_PROGRAM_ID
    elif owner == TOKEN_PROGRAM_ID:
        return TOKEN_PROGRAM_ID
    else:
        raise ValueError(f"❌ Unknown token program: {owner}")


# -------------------------------------------------------------------
# 🔹 SPL Token 전송
# -------------------------------------------------------------------
def send_spl_token(mint_address: str, wallet_address: str, amount: float, decimals: int):
    mint = Pubkey.from_string(mint_address)
    sender = kp.pubkey()
    wallet = Pubkey.from_string(wallet_address)

    program_id = detect_token_program(mint)
    sender_ata = derive_ata(sender, mint, program_id)
    recipient_ata = derive_ata(wallet, mint, program_id)

    lamports = int(amount * (10 ** decimals))

    create_ata_ix = create_associated_token_account_idempotent(
        payer=sender, owner=wallet, mint=mint, token_program_id=program_id
    )
    transfer_ix = transfer(
        TransferParams(
            program_id=program_id,
            source=sender_ata,
            dest=recipient_ata,
            owner=sender,
            amount=lamports,
            signers=[],
        )
    )

    recent_blockhash = client.get_latest_blockhash().value.blockhash
    msg = Message([create_ata_ix, transfer_ix], payer=sender)
    txn = Transaction([kp], msg, recent_blockhash)

    sig = client.send_raw_transaction(bytes(txn), opts=TxOpts(skip_preflight=True))
    return sig.value


# -------------------------------------------------------------------
# 🔹 SPL Token decimals 조회
# -------------------------------------------------------------------
def get_spl_decimals(mint_address: str) -> int:
    """Solana 토큰 decimals 조회"""
    resp = client.get_token_supply(Pubkey.from_string(mint_address))
    if resp.value:
        return resp.value.decimals
    else:
        raise ValueError("❌ Mint account not found")
