# amount.py
import requests
import os
from dotenv import load_dotenv

load_dotenv()
SOL_RPC_URL = os.getenv("RPC_URL")
SOL_ADDRESS = os.getenv("SOL_ADDRESS")   # 내 지갑 주소 환경변수에서 가져오기

def get_amount_from_tx(tx_hash: str) -> float:
    """
    Solana 트랜잭션에서 SOL_ADDRESS 기준으로 받은 SPL 토큰을 찾아
    실제 수량의 1/20 값 반환
    """
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                tx_hash,
                {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0},
            ],
        }
        resp = requests.post(SOL_RPC_URL, headers=headers, json=payload)
        data = resp.json()

        if "result" not in data or data["result"] is None:
            print(f"❌ Solana RPC 응답 오류: {data}")
            return 0.0

        meta = data["result"]["meta"]

        # pre/post 토큰 잔고 비교
        pre_tokens = {t["accountIndex"]: t for t in meta.get("preTokenBalances", [])}
        post_tokens = {t["accountIndex"]: t for t in meta.get("postTokenBalances", [])}

        buy_amount = 0.0
        for idx, post in post_tokens.items():
            if post["owner"] == SOL_ADDRESS:
                pre_amount = int(pre_tokens.get(idx, {}).get("uiTokenAmount", {}).get("amount", 0))
                post_amount = int(post["uiTokenAmount"]["amount"])
                diff = post_amount - pre_amount
                decimals = int(post["uiTokenAmount"]["decimals"])
                if diff > 0:
                    buy_amount = diff / (10 ** decimals)

        # 👉 받은 토큰 1/20 반환
        return buy_amount / 20

    except Exception as e:
        print(f"❌ amount.py 에러: {e}")
        return 0.0


# 실행 테스트
if __name__ == "__main__":
    tx_hash = input("SOL tx hash 입력: ").strip()
    amount = get_amount_from_tx(tx_hash)
    print(f"매수 토큰 1/20 수량: {amount}")
