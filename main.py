# main.py
import os
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 設定（必要なら環境変数で上書き）
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
APP_LIST_API = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={STEAM_API_KEY}&include_games=1"
JP_REVIEW_URL = "https://store.steampowered.com/appreviews/{appid}?json=1&language=japanese&purchase_type=all&num_per_page=0"
ALL_REVIEW_URL = "https://store.steampowered.com/appreviews/{appid}?json=1&language=all&purchase_type=all&num_per_page=0"

# 調整可能なパラメータ（Actions内では環境変数で上書き可）
SLEEP_BETWEEN_REQUESTS = float(os.getenv("SLEEP_BETWEEN_REQUESTS", "0.2"))  # 連続リクエスト間隔（秒）
MAX_APPS = int(os.getenv("MAX_APPS", "200"))  # 0 は無制限。開発中は 100 などに
SAVE_EVERY = int(os.getenv("SAVE_EVERY", "50"))  # 部分保存の頻度

OUT_FILE = "data.json"
TMP_FILE = "data_partial.json"

# セッション + リトライ設定
def make_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429,500,502,503,504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "steam-ranking-bot/1.0 (+https://github.com/K-nobata/ss2)"
    })
    return session

session = make_session()

def get_app_list():
    print("⏳ Fetching AppList...")
    r = session.get(APP_LIST_API, timeout=30)
    r.raise_for_status()
    data = r.json()
    apps = data.get("response", {}).get("apps", [])
    print(f"✅ AppList retrieved. {len(apps)} apps found.")
    return apps

def get_review_summary(appid, url_template):
    url = url_template.format(appid=appid)
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if "query_summary" not in data:
            return None
        qs = data["query_summary"]
        # query_summary keys: total_reviews, total_positive, total_negative...
        return qs
    except Exception as e:
        # エラーは None を返してスキップ（リトライは session の retry がする）
        return None

def save_results(results, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def main():
    if not STEAM_API_KEY:
        print("ERROR: STEAM_API_KEY not set in environment.")
        return

    apps = get_app_list()
    results = []
    total = len(apps)
    limit = MAX_APPS if MAX_APPS > 0 else total

    for i, app in enumerate(apps[:limit]):
        appid = app.get("appid")
        name = app.get("name", "").strip()
        if i % 100 == 0:
            print(f"Progress: {i}/{limit} apps processed. Current results: {len(results)}")

        # 1) 日本語レビュー集計（まずは日本語のみでフィルタ）
        jp_qs = get_review_summary(appid, JP_REVIEW_URL)
        if not jp_qs:
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue

        total_jp = jp_qs.get("total_reviews", 0)
        if total_jp < 200:
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue

        positive_jp = jp_qs.get("total_positive", 0)
        positive_rate_jp = round((positive_jp / max(total_jp, 1)) * 100, 2)

        # 2) 全言語レビュー集計（より正確な全体比率を取る）
        all_qs = get_review_summary(appid, ALL_REVIEW_URL)
        if all_qs:
            total_all = all_qs.get("total_reviews", 0)
            positive_all = all_qs.get("total_positive", 0)
            positive_rate_all = round((positive_all / max(total_all, 1)) * 100, 2)
        else:
            total_all = None
            positive_rate_all = None

        # 3) store url / image / game name（AppList の name を使用）
        store_url = f"https://store.steampowered.com/app/{appid}"
        # 画像は一般的な capsule path を使う（存在しない場合もある）
        image_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_231x87.jpg"

        entry = {
            "appid": appid,
            "name": name,
            "total_reviews_jp": total_jp,
            "positive_rate_jp": positive_rate_jp,
            "total_reviews_all": total_all,
            "positive_rate_all": positive_rate_all,
            "store_url": store_url,
            "image_url": image_url
        }
        results.append(entry)

        # 部分保存（中断・タイムアウト対策）
        if (len(results) % SAVE_EVERY) == 0:
            print(f"Saving partial results ({len(results)}) to {TMP_FILE}...")
            save_results(results, TMP_FILE)

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    # ソート（日本語高評価率順降順）
    results.sort(key=lambda x: (x.get("positive_rate_jp") or 0), reverse=True)

    # 保存
    save_results(results, OUT_FILE)
    # もし途中ファイルがあれば削除
    try:
        if os.path.exists(TMP_FILE):
            os.remove(TMP_FILE)
    except Exception:
        pass

    print(f"🎉 Done. {len(results)} games with JP reviews >= 200 were saved to {OUT_FILE}.")

if __name__ == "__main__":
    main()
