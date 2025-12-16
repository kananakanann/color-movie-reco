# myproject/add_certification.py
import os
import json
import time
import requests
from typing import Optional, Dict, Any

from config import TMDB_API_KEY

BASE_URL = "https://api.themoviedb.org/3"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MOVIES_PATH = os.path.join(DATA_DIR, "movies_data.json")

def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def get_release_dates(movie_id: int) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/movie/{movie_id}/release_dates"
    params = {"api_key": TMDB_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] release_dates movie_id={movie_id} status={r.status_code}")
        return None
    except requests.RequestException as e:
        print(f"[ERROR] release_dates exception: {e}")
        return None

def pick_certification(release_dates_json: Dict[str, Any], country: str) -> Optional[str]:
    # その国のcertificationを優先して返す（空文字は無視）
    for block in release_dates_json.get("results", []):
        if block.get("iso_3166_1") != country:
            continue
        for rd in block.get("release_dates", []):
            cert = (rd.get("certification") or "").strip()
            if cert:
                return cert
    return None

def main():
    movies = load_json(MOVIES_PATH, default=[])
    updated = 0

    for i, m in enumerate(movies, 1):
        mid = m.get("id")
        if not mid:
            continue

        # すでに入ってるならスキップ（必要なら消して全更新でもOK）
        if "jp_certification" in m:
            continue

        data = get_release_dates(mid)
        if not data:
            continue

        jp = pick_certification(data, "JP")
        us = pick_certification(data, "US")

        # 表示用に持っておく（JP優先、なければUS）
        m["jp_certification"] = jp  # 例: "PG12", "R15+", "R18+", "G" など
        m["us_certification"] = us  # 例: "PG-13", "R" など
        m["display_certification"] = jp or us  # 画面表示に使う

        updated += 1
        if updated % 20 == 0:
            save_json(MOVIES_PATH, movies)
            print(f"[INFO] updated={updated}")

        time.sleep(0.15)  # 叩きすぎ防止（必要なら調整）

    save_json(MOVIES_PATH, movies)
    print(f"[DONE] updated={updated} / total={len(movies)}")

if __name__ == "__main__":
    main()
