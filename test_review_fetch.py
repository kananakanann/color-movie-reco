import requests
import json
import os

API_KEY = "ec8dafa527d136f835ac45ce0553dbae"
MOVIE_ID = 109445  # Frozen II
URL = f"https://api.themoviedb.org/3/movie/{MOVIE_ID}/reviews"

params = {
    "api_key": API_KEY,
    "page": 1,
    "language": "en-US",  # 英語レビュー
}

response = requests.get(URL, params=params, timeout=20)

if response.status_code == 200:
    data = response.json()
    reviews = data.get("results", [])
    print(f"✅ {len(reviews)} reviews fetched for movie_id={MOVIE_ID}")

    # 保存先フォルダを確実に作成
    DATA_DIR = os.path.join("data")
    os.makedirs(DATA_DIR, exist_ok=True)

    # JSON保存
    out_path = os.path.join(DATA_DIR, "test_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    print(f"💾 Reviews saved to {out_path}")

    # 最初の数件だけ表示
    for i, review in enumerate(reviews[:3]):
        print(f"\nReview {i+1} by {review['author']}:")
        print(review['content'][:300], "...")
else:
    print("❌ Error:", response.status_code, response.text)
