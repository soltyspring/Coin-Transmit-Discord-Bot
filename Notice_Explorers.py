import os
import json
import re
import time
import requests
import cloudscraper
from bs4 import BeautifulSoup

# ----------------------------
# 설정
# ----------------------------
LIST_URL = "https://api.bithumb.com/v1/notices"
HEADERS = {"accept": "application/json", "User-Agent": "Mozilla/5.0"}
OUTPUT_FILE = "airdrop_explorers.json"

scraper = cloudscraper.create_scraper()

# ----------------------------
# JSON 저장/불러오기
# ----------------------------
def save_airdrops(data):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_airdrops():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# ----------------------------
# 크롤링 함수
# ----------------------------
def safe_request(url):
    """안전 요청 (2초 지연 포함)"""
    time.sleep(2)
    return scraper.get(url, headers=HEADERS)

def fetch_recent_notices(size=20):
    """최근 공지 size개 가져오기"""
    resp = scraper.get(   # 🔥 requests → scraper
        LIST_URL,
        headers=HEADERS,
        params={"page": 1, "count": size}
    )
    resp.raise_for_status()
    return resp.json()

def fetch_notice_links(url):
    """이벤트 공지에서 거래지원 안내 링크 추출"""
    try:
        resp = safe_request(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ 링크 요청 실패 ({url}) → {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    content_div = soup.select_one("div[class^=NoticeDetailContent_detail-content]")
    if not content_div:
        return []

    links = []
    for a in content_div.find_all("a", href=True):
        text = a.get_text(strip=True)
        if re.search(r"/notice/\d+", a["href"]) and ("거래지원" in text or "거래 지원" in text):
            full_url = a["href"]
            if not full_url.startswith("http"):
                full_url = "https://feed.bithumb.com" + full_url
            links.append({"text": text, "url": full_url})
    return links

def fetch_coins_and_explorers(url):
    """거래지원 안내 공지에서 코인 심볼 + 블록 익스플로러 추출"""
    resp = safe_request(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 제목에서 코인 심볼 추출
    title_tag = soup.select_one("h2, h3, [class^=NoticeDetailHeader_title__]")
    coins = []
    if title_tag:
        coins = re.findall(r"\(([A-Za-z0-9]+)\)", title_tag.get_text())

    # 블록 익스플로러 추출
    explorers = []
    content_div = soup.select_one("div[class^=NoticeDetailContent_detail-content]")
    if content_div:
        for a in content_div.find_all("a", href=True):
            if "블록 익스플로러" in a.get_text(strip=True):
                explorers.append(a["href"])

    # 순서대로 매칭
    matched = []
    for coin, exp in zip(coins, explorers):
        matched.append({
            "chain": detect_chain(exp),
            "coin": coin,
            "contract": exp.split("/")[-1]
        })

    return matched

def detect_chain(url):
    if "etherscan.io" in url: return "ETH"
    if "basescan.org" in url: return "BASE"
    if "bscscan.com" in url: return "BSC"
    if "solscan.io" in url: return "SOL"
    return "UNKNOWN"

# ----------------------------
# 실행
# ----------------------------
if __name__ == "__main__":
    old_data = load_airdrops()
    new_data = []

    notices = fetch_recent_notices(size=20)

for item in notices:
    title = item.get("title", "")
    url = item.get("pc_url")

    # 에어드랍 이벤트만 추출
    if "에어드랍" not in title:
        continue

    print(f"📌 이벤트 공지: {title}")
    print("URL:", url)

    # 이벤트 공지에서 거래지원 안내 링크 추출
    support_links = fetch_notice_links(url)
    print("거래지원 안내 링크:", len(support_links), "개")

    # ✅ 링크가 없으면 그냥 넘어감
    if not support_links:
        print("⚠️ 거래지원 안내 링크 없음 → 스킵")
        continue

    record = {
        "event_title": title,
        "event_url": url,
        "coins": []
    }

    event_coins = re.findall(r"\(([A-Za-z0-9]+)\)", title)

    for link in support_links:
        matched = fetch_coins_and_explorers(link["url"])
        matched = [c for c in matched if c["coin"] in event_coins]
        record["coins"].extend(matched)

    if record["coins"]:
        new_data.append(record)



    save_airdrops(new_data)
    print(f"\n✅ {OUTPUT_FILE} 저장 완료 ({len(new_data)}건)")
