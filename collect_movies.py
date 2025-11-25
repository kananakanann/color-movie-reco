# myproject/collect_movies.py
# TMDbから人気順で映画を取得し、直URLフォールバック方式のみでレビューを取得。
# myproject/data/ に映画情報(movies_data.json)とレビュー(review_texts.json)を保存。

import json
import os
import time
import random
import requests
from typing import Dict, List, Any, Optional

from config import (
    TMDB_API_KEY,
    GENRE_ID,               # [] の場合は全ジャンル対象
    DISCOVER_PAGES,
    MAX_REVIEWS_PER_MOVIE,
    REQUEST_SLEEP_SEC,
    MAX_RETRIES,
)

# --------- 保存先パス ---------
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MOVIES_PATH = os.path.join(DATA_DIR, "movies_data.json")
REVIEWS_PATH = os.path.join(DATA_DIR, "review_texts.json")

# --------- TMDb 基本 ---------
BASE_URL = "https://api.themoviedb.org/3"

# --------- 収集ポリシー ---------
SORT_BY = "vote_average.desc" #高評価順
VOTE_COUNT_MIN = 300
MIN_REQUIRED_REVIEWS = 1

# ============================================================
# ユーティリティ
# ============================================================

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

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

def backoff_sleep(base: float, attempt: int):
    time.sleep(base * (2 ** attempt) + random.uniform(0, base))

# ============================================================
# TMDb API
# ============================================================

def discover_movies(page: int, genre_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "page": page,
        "sort_by": SORT_BY,
        "vote_count.gte": VOTE_COUNT_MIN,
    }
    if genre_id is not None:
        params["with_genres"] = genre_id

    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        print(f"[ERROR] discover {url} {resp.status_code}")
        return None
    except requests.RequestException as e:
        print(f"[ERROR] discover exception: {e}")
        return None

def get_movie_reviews_direct_url(movie_id: int, page: int) -> Optional[Dict[str, Any]]:
    """
    直URLでレビュー取得（api_keyクエリ直書き + キャッシュバスター）。
    """
    ts = int(time.time() * 1000)
    url = (f"{BASE_URL}/movie/{movie_id}/reviews"
           f"?api_key={TMDB_API_KEY}&page={page}&language=en-US&_={ts}")
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(0.5)
            resp2 = requests.get(url, timeout=20)
            if resp2.status_code == 200:
                return resp2.json()
        print(f"[WARN] direct_url {movie_id} page={page} -> {resp.status_code}")
        return None
    except requests.RequestException as e:
        print(f"[ERROR] direct_url reviews exception: {e}")
        return None

# ============================================================
# 整形・フィルタ
# ============================================================

def movie_record_from_result(res: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": res.get("id"),
        "title": res.get("title") or res.get("original_title"),
        "overview": res.get("overview"),
        "release_date": res.get("release_date"),
        "genre_ids": res.get("genre_ids", []),
        "original_language": res.get("original_language"),
        "vote_average": res.get("vote_average"),
        "vote_count": res.get("vote_count"),
        "poster_path": res.get("poster_path"),
        "backdrop_path": res.get("backdrop_path"),
        "popularity": res.get("popularity"),
    }

def extract_review_texts(reviews: List[Dict[str, Any]]) -> List[str]:
    texts = []
    for r in reviews:
        content = r.get("content")
        if content and content.strip():
            texts.append(content.strip())
    return texts

def collect_reviews_for_movie(movie_id: int, max_count: int) -> List[str]:
    """直URLだけでレビュー収集"""
    collected: List[str] = []
    page = 1
    while len(collected) < max_count:
        data = get_movie_reviews_direct_url(movie_id, page)
        if not data:
            break

        results = data.get("results", [])
        if not results:
            break

        texts = extract_review_texts(results)
        collected.extend(texts)

        total_pages = data.get("total_pages", page)
        page += 1
        if page > total_pages or len(collected) >= max_count:
            break
    return collected[:max_count]

# ============================================================
# メイン
# ============================================================

def main():
    ensure_data_dir()

    movies_data: List[Dict[str, Any]] = load_json(MOVIES_PATH, default=[])
    reviews_map: Dict[str, List[str]] = load_json(REVIEWS_PATH, default={})
    saved_ids = {m["id"] for m in movies_data if "id" in m}

    target_genres: List[Optional[int]] = GENRE_ID if GENRE_ID else [None]

    processed = 0
    kept_movies = 0

    for g in target_genres:
        g_label = "ALL" if g is None else str(g)
        print(f"[INFO] Discovering movies (genre={g_label}) pages=1..{DISCOVER_PAGES}")

        for page in range(1, DISCOVER_PAGES + 1):
            disc = discover_movies(page=page, genre_id=g)
            if not disc:
                continue
            results = disc.get("results", [])
            for res in results:
                rec = movie_record_from_result(res)
                mid = rec.get("id")
                if mid is None:
                    continue
                processed += 1
                key = str(mid)

                if key in reviews_map and len(reviews_map[key]) >= MIN_REQUIRED_REVIEWS:
                    if mid not in saved_ids:
                        movies_data.append(rec)
                        saved_ids.add(mid)
                        kept_movies += 1
                        save_json(MOVIES_PATH, movies_data)
                    continue

                texts = collect_reviews_for_movie(mid, MAX_REVIEWS_PER_MOVIE)
                if len(texts) >= MIN_REQUIRED_REVIEWS:
                    reviews_map[key] = texts
                    save_json(REVIEWS_PATH, reviews_map)
                    if mid not in saved_ids:
                        movies_data.append(rec)
                        saved_ids.add(mid)
                        kept_movies += 1
                        save_json(MOVIES_PATH, movies_data)

                if processed % 20 == 0:
                    print(f"[INFO] processed={processed}, kept_movies={kept_movies}")

            save_json(MOVIES_PATH, movies_data)
            save_json(REVIEWS_PATH, reviews_map)

    print("[DONE]")
    print(f"Processed: {processed}, Saved movies: {len(movies_data)}, Reviews: {len(reviews_map)}")

if __name__ == "__main__":
    main()
