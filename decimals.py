import asyncio
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from spl.token._layouts import MINT_LAYOUT

async def get_token_decimals(mint_address: str):
    client = AsyncClient("https://api.mainnet-beta.solana.com")
    resp = await client.get_account_info(Pubkey.from_string(mint_address))
    await client.close()

    if resp.value is None:
        print("❌ Mint 계정을 못 찾음")
        return None

    # 최신 solana-py: resp.value.data는 BinaryData 객체
    raw_data = bytes(resp.value.data)   # 바로 bytes로 변환 가능

    decoded = MINT_LAYOUT.parse(raw_data)
    decimals = decoded.decimals

    print("✅ Decimals:", decimals)
    return decimals

# 실행
if __name__ == "__main__":
    asyncio.run(get_token_decimals(input()))
