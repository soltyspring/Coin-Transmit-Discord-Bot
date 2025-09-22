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

    tx = token.functions.transfer(
        Web3.to_checksum_address(to_address),
        int(amount * (10 ** decimals))
    ).build_transaction({
        "from": MY_ADDRESS,
        "nonce": nonce,
        "gas": 100000,  # ERC20 전송은 가스가 네이티브 전송보다 큼
        "gasPrice": w3.to_wei("30", "gwei"),
    })

    signed_tx = w3.eth.account.sign_transaction(tx, ETH_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

    return w3.to_hex(tx_hash)
