import os
import hmac
import base64
import requests
import json
import datetime
import urllib.parse
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------------
# 환경 변수
# -------------------------------------------------------------------
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_SECRET_KEY = os.getenv("OKX_SECRET_KEY")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
OKX_PROJECT_ID = os.getenv("OKX_PROJECT_ID")

INFURA_URL = os.getenv("INFURA_URL")  # Ethereum RPC
ETH_PRIVATE_KEY = os.getenv("ETH_PRIVATE_KEY")
ETH_ADDRESS = os.getenv("ETH_ADDRESS")

BASE_URL = "https://www.okx.com"   # ✅ OKX DEX 엔드포인트
CHAIN_INDEX = "1"  # Ethereum Mainnet
ETH_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"  # Native ETH

w3 = Web3(Web3.HTTPProvider(INFURA_URL))


# -------------------------------------------------------------------
# OKX 인증 헤더 생성
# -------------------------------------------------------------------
def get_headers(method: str, path: str, params: dict = None, body: str = ""):
    timestamp = datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

    query = ""
    if method == "GET" and params:
        query = "?" + urllib.parse.urlencode(params)

    if method == "POST" and body:
        query = body

    prehash = timestamp + method + path + query
    sign = base64.b64encode(
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


# -------------------------------------------------------------------
# USD → ETH 변환 (quote API 활용)
# -------------------------------------------------------------------
def get_eth_amount_for_usd(to_token_address: str, usd_amount: float):
    path = "/api/v6/dex/aggregator/quote"

    # 소량으로 quote 호출해서 ETH/USD 단가 확인
    params = {
        "chainIndex": CHAIN_INDEX,
        "fromTokenAddress": ETH_TOKEN,
        "toTokenAddress": to_token_address,
        "amount": str(10**15),  # 0.001 ETH (테스트용)
        "slippagePercent": "0.5",
        "userWalletAddress": ETH_ADDRESS,
    }

    url = BASE_URL + path
    headers = get_headers("GET", path, params=params)
    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()

    if data.get("code") != "0":
        raise Exception(f"Quote API error: {data}")

    # ETH 현재가
    eth_price = float(data["data"][0]["fromToken"]["tokenUnitPrice"])  
    print(f"DEBUG ETH Price: ${eth_price:.2f}")

    # usd_amount → 필요한 ETH 수량
    eth_amount = usd_amount / eth_price
    wei_amount = int(Web3.to_wei(eth_amount, "ether"))
    print(f"Buying ${usd_amount} ≈ {eth_amount:.8f} ETH ({wei_amount} wei)")
    return wei_amount


# -------------------------------------------------------------------
# 스왑 실행
# -------------------------------------------------------------------
def swap_eth_to_token(to_token_address: str, wei_amount: int, slippage="0.5") -> str:
    path = "/api/v6/dex/aggregator/swap"
    params = {
        "chainIndex": CHAIN_INDEX,  # Ethereum
        "fromTokenAddress": ETH_TOKEN,  # ETH
        "toTokenAddress": to_token_address,
        "amount": str(wei_amount),   # ✅ wei 단위 그대로 전달
        "slippagePercent": slippage,
        "userWalletAddress": ETH_ADDRESS,
    }

    headers = get_headers("GET", path, params=params)
    resp = requests.get(BASE_URL + path, headers=headers, params=params).json()
    print("DEBUG SWAP Response:", resp)

    if resp.get("code") != "0" or not resp.get("data"):
        raise Exception(f"Swap API error: {resp}")

    tx = resp["data"][0]["tx"]

    # Web3 트랜잭션 생성
    nonce = w3.eth.get_transaction_count(ETH_ADDRESS)
    tx_obj = {
        "from": tx["from"],
        "to": tx["to"],
        "data": tx["data"],
        "value": int(tx["value"]),
        "gas": int(tx["gas"]),
        "gasPrice": int(tx["gasPrice"]),
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
    }

    # 서명 + 전송
    signed_tx = w3.eth.account.sign_transaction(tx_obj, ETH_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    return w3.to_hex(tx_hash)


# -------------------------------------------------------------------
# 실행 예시 ($1 어치 ETH → BTR 토큰)
# -------------------------------------------------------------------
if __name__ == "__main__":
    target_token = "0x6C76dE483F1752Ac8473e2B4983A873991e70dA7"  # 예: BTR 토큰
    fixed_amount = 0.00025  # ETH
    wei_amount = Web3.to_wei(fixed_amount, "ether")

    tx_hash = swap_eth_to_token(target_token, wei_amount)
    print("✅ ETH → 토큰 스왑 실행 완료!")
    print("TX:", tx_hash)
    print(f"https://etherscan.io/tx/{tx_hash}")

