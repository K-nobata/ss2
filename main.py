# main.py
import os
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

STEAM_API_KEY = os.getenv("STEAM_API_KEY")

APP_LIST_API = (
    f"https://api.steampowered.com/IStoreService/GetAppList/v1/"
    f"?key={STEAM_API_KEY}&include_games=1"
)

JP_REVIEW_URL = "https://store.steampowered.com/appreviews/{appid}?json=1&language=japanese&purchase_type=all&num_per_page=0"
ALL_REVIEW_URL = "https://store.steampowered.com/appreviews/{appid}?json=1&language=all&purchase_type=all&num_per_page=0"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids={appid}&l=japanese&cc=jp"

# 調整可能
SLEEP_BETWEEN_REQUESTS = float(os.getenv("SLEEP_BETWEEN_REQUESTS", "0.25"))
MAX_APPS = int(os.getenv("MAX_APPS", "0"))
SAVE_EVERY = int(os.getenv("SAVE_EVERY", "50"))

OUT_FILE = "data.json"
TMP_FILE = "data_partial.json"

def make_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429,500,502,503,504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "steam-ranking-bot/1.2 (+https://github.com/K-nobata/ss2)"
    })
    return session

session = make_session()

def get_app_list():
    r = session.get(APP_LIST_API, timeout=30)
    r.raise_for_status()
    return r.json().get("response", {}).get("apps", [])

def get_review_summary(appid, url):
    try:
        r = session.get(url.format(appid=appid), timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("query_summary")
    except Exception:
        return None

def get_app_details(appid):
    """
    取得する情報：
      - release_date
      - genres
      - categories
      - price_overview
    """
    try:
        r = session.get(APP_DETAILS_URL.format(appid=appid), timeout=20)
        if r.status_code != 200:
            return None

        outer = r.json().get(str(appid), {})
        if not outer.get("success"):
            return None

        data = outer.get("data", {})

        # release date
        release_date = data.get("release_date", {}).get("date")

        # genres
        genres = [g["description"] for g in data.get("genres", [])]

        # categories
        categories = [c["description"] for c in data.get("categories", [])]

        # price overview (optional)
        price_overview = data.get("price_overview")
        if price_overview:
            initial = price_overview.get("initial")          # 割引前 (cents)
            final = price_overview.get("final")              # 現在価格 (cents)
            discount_percent = price_overview.get("discount_percent")
        else:
            initial = None
            final = None
            discount_percent = None

        return {
            "release_date": release_date,
            "genres": genres,
            "categories": categories,
            "price_initial": initial,
            "price_final": final,
            "discount_percent": discount_percent
        }

    except Exception:
        return None

def save_results(results, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def main():
    if not STEAM_API_KEY:
        print("ERROR: STEAM_API_KEY not set.")
        return

    apps = get_app_list()
    results = []
    limit = MAX_APPS if MAX_APPS > 0 else len(apps)

    for i, app in enumerate(apps[:limit]):
        appid = app.get("appid")
        name = app.get("name", "").strip()

        if i % 100 == 0:
            print(f"Progress: {i}/{limit} | results: {len(results)}")

        # ① 日本語レビュー集計
        jp = get_review_summary(appid, JP_REVIEW_URL)
        if not jp or jp.get("total_reviews", 0) < 200:
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue

        total_jp = jp["total_reviews"]
        positive_rate_jp = round(jp["total_positive"] / total_jp * 100, 2)

        # ② 全言語レビュー
        all_qs = get_review_summary(appid, ALL_REVIEW_URL)
        if all_qs:
            total_all = all_qs.get("total_reviews", 0)
            positive_rate_all = round(all_qs.get("total_positive", 0) / max(total_all, 1) * 100, 2)
        else:
            total_all = None
            positive_rate_all = None

        # ③ 詳細情報（タグ・ジャンル・発売日・価格）
        details = get_app_details(appid)
        if not details:
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue

        entry = {
            "appid": appid,
            "name": name,
            "release_date": details["release_date"],
            "genres": details["genres"],
            "categories": details["categories"],
            "total_reviews_jp": total_jp,
            "positive_rate_jp": positive_rate_jp,
            "total_reviews_all": total_all,
            "positive_rate_all": positive_rate_all,
            "store_url": f"https://store.steampowered.com/app/{appid}",
            "image_url": f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_231x87.jpg",
            "price_initial": details["price_initial"],
            "price_final": details["price_final"],
            "discount_percent": details["discount_percent"],
        }

        results.append(entry)

        if len(results) % SAVE_EVERY == 0:
            save_results(results, TMP_FILE)

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    # sort by JP review rate
    results.sort(key=lambda x: x["positive_rate_jp"], reverse=True)

    save_results(results, OUT_FILE)

    try:
        if os.path.exists(TMP_FILE):
            os.remove(TMP_FILE)
    except:
        pass

    print(f"Done. {len(results)} games saved.")

if __name__ == "__main__":
    main()
