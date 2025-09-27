import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------------
# ⚙️ 환경 변수
# -------------------------------------------------------------------
INFURA_URL = os.getenv("INFURA_URL")         # Infura / Alchemy RPC URL
ETH_PRIVATE_KEY = os.getenv("ETH_PRIVATE_KEY")
MY_ADDRESS = os.getenv("ETH_ADDRESS")

# Web3 연결
w3 = Web3(Web3.HTTPProvider(INFURA_URL))
if not w3.is_connected():
    raise ConnectionError("❌ Ethereum RPC 연결 실패. INFURA_URL 확인 필요")


# -------------------------------------------------------------------
# 🔹 ERC20 ABI 정의
# -------------------------------------------------------------------
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    }
]

ERC20_ABI_DECIMALS = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    }
]


# -------------------------------------------------------------------
# 🔹 ERC20 decimals 조회
# -------------------------------------------------------------------
def get_erc20_decimals(token_address: str) -> int:
    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI_DECIMALS
    )
    return token.functions.decimals().call()


# -------------------------------------------------------------------
# 🔹 ERC20 전송
# -------------------------------------------------------------------
def send_erc20(token_address: str, to_address: str, amount: float, decimals: int):
    """
    ERC20 토큰 전송 함수
    token_address: ERC20 컨트랙트 주소
    to_address: 받는 사람 주소
    amount: 전송 수량 (소수점 단위 입력)
    decimals: 토큰 소수점 자리수 (예: USDT=6, 대부분 ERC20=18)
    """

    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI
    )

    nonce = w3.eth.get_transaction_count(MY_ADDRESS)
    gas_price = w3.eth.gas_price  # ✅ 현재 네트워크 가스비 조회

    tx = token.functions.transfer(
        Web3.to_checksum_address(to_address),
        int(amount * (10 ** decimals))
    ).build_transaction({
        "from": MY_ADDRESS,
        "nonce": nonce,
        "gas": 100000,   # ERC20 전송 기본 예상치
        "gasPrice": gas_price,  # ✅ 동적 가스비 적용
    })

    signed_tx = w3.eth.account.sign_transaction(tx, ETH_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    return w3.to_hex(tx_hash)


# -------------------------------------------------------------------
# 실행 테스트
# -------------------------------------------------------------------
if __name__ == "__main__":
    token_address = "0xc3d91c9c4fcbcda17c36103801f55335531bf379"
    to_address = "0x24f5cceda997b3ca3d837ea1c55f09410e5fb257"

    decimals = get_erc20_decimals(token_address)
    print("Decimals:", decimals)

    tx_hash = send_erc20(token_address, to_address, 0.1, decimals)
    print("TX Hash:", tx_hash)
    print("Etherscan:", f"https://etherscan.io/tx/{tx_hash}")
