import requests
import json

# 試験用 appid リスト（後で自動取得に切り替える）
APP_IDS = [570, 730, 440, 238960, 413150]  # Dota2, CSGO, TF2, Risk of Rain, Stardew Valley など

def get_reviews(appid):
    url = f"https://store.steampowered.com/appreviews/{appid}?json=1&language=japanese&purchase_type=all"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    data = res.json()
    if "query_summary" not in data:
        return None
    q = data["query_summary"]

    return {
        "appid": appid,
        "total_reviews": q.get("total_reviews", 0),
        "positive": q.get("total_positive", 0),
        "negative": q.get("total_negative", 0),
        "positive_rate": round((q.get("total_positive", 0) / max(q.get("total_reviews", 1), 1)) * 100, 2)
    }


def fetch_data():
    results = []
    for appid in APP_IDS:
        r = get_reviews(appid)
        if r:
            # ストアURL & 画像URL追加
            r["store_url"] = f"https://store.steampowered.com/app/{appid}"
            r["image_url"] = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_231x87.jpg"
            results.append(r)

    # 日本語レビュー高評価率でソート
    results.sort(key=lambda x: x["positive_rate"], reverse=True)

    # JSON出力
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    fetch_data()
