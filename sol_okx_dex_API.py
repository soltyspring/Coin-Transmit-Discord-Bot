import os
import base64
import base58
import requests
import datetime
import urllib.parse
import hmac, base64 as b64
from dotenv import load_dotenv

from solana.rpc.api import Client
from solana.rpc.types import TxOpts

from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0
from solders.system_program import transfer, TransferParams
import nacl.signing

# SPL Token (주소 계산만 사용)
from spl.token.constants import WRAPPED_SOL_MINT, TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address

load_dotenv()

# ---------------------------------------------------------
# 환경 변수
# ---------------------------------------------------------
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_SECRET_KEY = os.getenv("OKX_SECRET_KEY")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
OKX_PROJECT_ID = os.getenv("OKX_PROJECT_ID")

SOL_PRIVATE_KEY = os.getenv("SOL_PRIVATE_KEY")  # base58 인코딩된 개인키
SOL_ADDRESS = os.getenv("SOL_ADDRESS")          # 지갑 주소

client = Client("https://api.mainnet-beta.solana.com")
CHAIN_INDEX = "501"
BASE_URL = "https://www.okx.com"


# ---------------------------------------------------------
# OKX 인증 헤더
# ---------------------------------------------------------
def get_headers(method: str, path: str, params: dict = None, body: str = ""):
    timestamp = datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    query = ""
    if method == "GET" and params:
        query = "?" + urllib.parse.urlencode(params)
    if method == "POST" and body:
        query = body
    prehash = timestamp + method + path + query
    sign = b64.b64encode(
        hmac.new(OKX_SECRET_KEY.encode(), prehash.encode(), "sha256").digest()
    ).decode()
    return {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": OKX_API_KEY,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": OKX_API_PASSPHRASE,
        "OK-ACCESS-PROJECT": OKX_PROJECT_ID,
    }


# ---------------------------------------------------------
# Keypair 로딩
# ---------------------------------------------------------
def load_keypair_from_base58(b58_key: str) -> Keypair:
    secret = base58.b58decode(b58_key)
    if len(secret) == 32:
        sk = nacl.signing.SigningKey(secret)
        secret = sk.encode() + sk.verify_key.encode()
    elif len(secret) != 64:
        raise ValueError("지원되지 않는 키 형식 (32 또는 64 바이트여야 함)")
    return Keypair.from_bytes(secret)


# ---------------------------------------------------------
# Instruction Helpers (solders 전용)
# ---------------------------------------------------------

def create_associated_token_account_solders(payer: Pubkey, owner: Pubkey, mint: Pubkey) -> Instruction:
    """ATA 생성 Instruction (solders 전용)"""
    ata = get_associated_token_address(owner, mint)
    return Instruction(
        program_id=ASSOCIATED_TOKEN_PROGRAM_ID,
        accounts=[
            AccountMeta(payer, is_signer=True, is_writable=True),
            AccountMeta(ata, is_signer=False, is_writable=True),
            AccountMeta(owner, is_signer=False, is_writable=False),
            AccountMeta(mint, is_signer=False, is_writable=False),
            AccountMeta(Pubkey.from_string("11111111111111111111111111111111"), is_signer=False, is_writable=False),  # System Program
            AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(Pubkey.from_string("SysvarRent111111111111111111111111111111111"), is_signer=False, is_writable=False),
        ],
        data=b"",  # create_associated_token_account는 data 없음
    )

def sync_native_solders(account: Pubkey) -> Instruction:
    """wSOL sync_native Instruction (solders 전용)"""
    return Instruction(
        program_id=TOKEN_PROGRAM_ID,
        accounts=[AccountMeta(account, is_signer=False, is_writable=True)],
        data=bytes([17]),  # SyncNative opcode
    )


# ---------------------------------------------------------
# wSOL ATA 체크 및 래핑
# ---------------------------------------------------------
def ensure_wsol_account(min_lamports: int):
    owner = Pubkey.from_string(SOL_ADDRESS)
    wsol_ata = get_associated_token_address(owner, WRAPPED_SOL_MINT)

    # wSOL ATA 잔액 확인
    balance_resp = client.get_token_account_balance(wsol_ata)
    current_balance = 0
    if balance_resp.value is not None:
        current_balance = int(balance_resp.value.amount)  # lamports 단위

    print(f"[INFO] 현재 wSOL 잔액: {current_balance} lamports")

    # 필요한 수량보다 부족하면만 래핑
    if current_balance < min_lamports:
        print(f"[INFO] wSOL 부족 → {min_lamports - current_balance} lamports 래핑 필요")

        info = client.get_account_info(wsol_ata)
        instructions = []

        if info.value is None:
            print("[INFO] wSOL ATA 없음 → 생성")
            instructions.append(
                create_associated_token_account_solders(
                    payer=owner,
                    owner=owner,
                    mint=WRAPPED_SOL_MINT,
                )
            )

        # SOL → wSOL 입금
        wrap_amount = min_lamports - current_balance
        print(f"[INFO] {wrap_amount} lamports SOL → wSOL 래핑")
        instructions.append(
            transfer(TransferParams(from_pubkey=owner, to_pubkey=wsol_ata, lamports=wrap_amount))
        )

        # sync_native 호출
        instructions.append(sync_native_solders(wsol_ata))

        # 트랜잭션 실행
        bh_resp = client.get_latest_blockhash()
        blockhash = bh_resp.value.blockhash

        kp = load_keypair_from_base58(SOL_PRIVATE_KEY)
        msg = MessageV0.try_compile(
            payer=owner,
            instructions=instructions,
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash,
        )
        tx = VersionedTransaction(msg, [kp])
        sig = client.send_raw_transaction(bytes(tx), opts=TxOpts(skip_preflight=True))
        print("[INFO] wSOL 래핑 완료:", sig.value)
    else:
        print("[INFO] wSOL 충분 → 래핑 생략")

    return wsol_ata


# ---------------------------------------------------------
# OKX API → solders.Instruction 변환
# ---------------------------------------------------------
def build_instructions(instr_list: list) -> list:
    instructions = []
    for instr in instr_list:
        accounts = [
            AccountMeta(
                pubkey=Pubkey.from_string(acc["pubkey"]),
                is_signer=acc["isSigner"],
                is_writable=acc["isWritable"],
            )
            for acc in instr["accounts"]
        ]
        data = base64.b64decode(instr["data"])
        instructions.append(
            Instruction(
                program_id=Pubkey.from_string(instr["programId"]),
                accounts=accounts,
                data=data,
            )
        )
    return instructions


# ---------------------------------------------------------
# SOL → SPL 토큰 스왑 실행
# ---------------------------------------------------------
def swap_sol_to_token_instruction(to_token_address: str, lamports: int, slippage="5") -> str:
    # 1. 먼저 wSOL 준비
    ensure_wsol_account(lamports)

    # 2. OKX aggregator swap instruction API
    path = "/api/v6/dex/aggregator/swap-instruction"
    params = {
        "chainIndex": CHAIN_INDEX,
        "fromTokenAddress": str(WRAPPED_SOL_MINT),
        "toTokenAddress": to_token_address,
        "amount": str(lamports),
        "slippagePercent": slippage,
        "userWalletAddress": SOL_ADDRESS,
    }
    headers = get_headers("GET", path, params=params)
    resp = requests.get(BASE_URL + path, headers=headers, params=params).json()
    print("DEBUG Swap API Response:", resp)

    if resp.get("code") != "0" or not resp.get("data"):
        raise Exception(f"Swap-instruction API failed: {resp}")

    swap_data = resp["data"]
    instr_list = swap_data["instructionLists"]

    # Instruction 생성 (전부 solders.Instruction)
    instructions = build_instructions(instr_list)

    # 최신 blockhash
    bh_resp = client.get_latest_blockhash()
    blockhash = bh_resp.value.blockhash   # ✅ Hash.from_string 제거

    # 트랜잭션 생성 및 서명
    keypair = load_keypair_from_base58(SOL_PRIVATE_KEY)
    msg = MessageV0.try_compile(
        payer=Pubkey.from_string(SOL_ADDRESS),
        instructions=instructions,
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    tx = VersionedTransaction(msg, [keypair])

    # 전송
    result = client.send_raw_transaction(bytes(tx), opts=TxOpts(skip_preflight=True))
    return result.value


# ---------------------------------------------------------
# 실행 예시
# ---------------------------------------------------------
if __name__ == "__main__":
    holo_token = "69RX85eQoEsnZvXGmLNjYcWgVkp9r2JjahVm99KbJETU"  # HOLO
    tx_hash = swap_sol_to_token_instruction(holo_token, lamports=2_500_000)
    print("✅ SOL → HOLO 스왑 실행 완료!")
    print("TX:", tx_hash)
    print(f"https://solscan.io/tx/{tx_hash}")
