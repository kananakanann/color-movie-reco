import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import heapq

# ====== 入出力パス ======
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ENRICHED_PATH = os.path.join(DATA_DIR, "movies_with_emotions.json")  

ALLOWED_EMOTIONS = {"joy", "sadness", "anger", "fear", "love", "surprise"}

# 任意：ラベルのゆるい同義語（必要に応じて拡張）
EMOTION_SYNONYMS = {
    "happy": "joy",
    "happiness": "joy",
    "delight": "joy",
    "fun": "joy",
    "romance": "love",
    "romantic": "love",
    "scary": "fear",
    "afraid": "fear",
    "angry": "anger",
    "mad": "anger",
    "shock": "surprise",
    "shocking": "surprise",
    "depressing": "sadness",
    "blue": "sadness",
}

@dataclass
class Filters:
    min_review_count: int = 0 # 最低レビュー数
    min_vote_count: int = 0
    min_vote_average: float = 0.0
    year_range: Optional[Tuple[int, int]] = None   # (min_year, max_year)
    include_genres: Optional[List[int]] = None
    exclude_genres: Optional[List[int]] = None
    query_text: Optional[str] = None               # タイトル or 概要に含む文字列（大小無視）

def _parse_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    m = re.match(r"(\d{4})", date_str)
    return int(m.group(1)) if m else None

def _normalize_emotion(e: str) -> Optional[str]:
    if not e:
        return None
    e_norm = e.strip().lower()
    if e_norm in ALLOWED_EMOTIONS:
        return e_norm
    # 同義語マッピング
    if e_norm in EMOTION_SYNONYMS:
        return EMOTION_SYNONYMS[e_norm]
    return None

def _intersects(a: List[int], b: List[int]) -> bool:
    return bool(set(a).intersection(b))

def _text_match(q: str, *fields: str) -> bool:
    q_norm = q.strip().lower()
    for f in fields:
        if f and q_norm in f.lower():
            return True
    return False

def _confidence_boost(review_count: int, cap: float = 0.2, ref: int = 100) -> float:
    """
    レビュー数に応じて 0〜cap を加点（信頼度ブースト）。
    例: review_count=100 付近で上限 cap、10 なら ~cap/2 くらい。
    """
    import math
    if review_count <= 0:
        return 0.0
    val = math.log1p(review_count) / math.log1p(ref)
    return max(0.0, min(cap, val * cap))

def load_movies() -> List[Dict]:
    if not os.path.exists(ENRICHED_PATH):
        raise FileNotFoundError(f"Not found: {ENRICHED_PATH}. Run Step 2 to create it.")
    with open(ENRICHED_PATH, "r", encoding="utf-8") as f:
        movies = json.load(f)
    # 事前整形（年の追加）
    for m in movies:
        m["_year"] = _parse_year(m.get("release_date"))
    return movies

def recommend_by_emotion(
    target_emotion: str,
    top_k: int = 10,
    filters: Filters = Filters(),
    use_confidence_boost: bool = True,
    secondary_sort: str = "vote_count"  # 同点時の安定キー: "vote_count" or "title"
) -> List[Dict]:
    e = _normalize_emotion(target_emotion)
    if not e:
        raise ValueError(
            f"Unsupported emotion: {target_emotion}. "
            f"Choose from {sorted(ALLOWED_EMOTIONS)} or a known synonym."
        )

    movies = load_movies()

    # ---- 基本フィルタ ----
    cands: List[Dict] = []
    for m in movies:
        # 必須データ
        emotions = m.get("emotions_avg") or {}
        if e not in emotions:
            continue

        # レビュー本数下限
        if m.get("review_count_used", 0) < filters.min_review_count:
            continue
        # 投票数・平均による下限
        if filters.min_vote_count and (m.get("vote_count") or 0) < filters.min_vote_count:
            continue
        if filters.min_vote_average and (m.get("vote_average") or 0.0) < filters.min_vote_average:
            continue
        # 年レンジ
        if filters.year_range:
            y = m.get("_year")
            y_min, y_max = filters.year_range
            if (y is None) or not (y_min <= y <= y_max):
                continue
        # ジャンル条件
        g_ids = m.get("genre_ids") or []
        if filters.include_genres and not _intersects(g_ids, filters.include_genres):
            continue
        if filters.exclude_genres and _intersects(g_ids, filters.exclude_genres):
            continue
        # テキスト検索
        if filters.query_text and not _text_match(filters.query_text, m.get("title", ""), m.get("overview", "")):
            continue

        # スコア計算
        base = float(emotions.get(e, 0.0))
        score = base
        if use_confidence_boost:
            score += _confidence_boost(int(m.get("review_count_used", 0)))
        # 同点時の安定化補助キー
        if secondary_sort == "vote_count":
            tie = int(m.get("vote_count") or 0)
        else:
            tie = m.get("title") or ""
        m["_score_tuple"] = (score, tie)
        cands.append(m)

    if not cands:
        return []

    # ---- 上位N件 (高速抽出) ----
    # _score_tuple で比較。score 大 → 小、vote_count 大 → 小
    def key_fn(mm: Dict):
        return (mm["_score_tuple"][0], mm["_score_tuple"][1])

    top = heapq.nlargest(top_k, cands, key=key_fn)

    # ---- 整形して返す ----
    out = []
    for m in top:
        out.append({
            "id": m.get("id"),
            "title": m.get("title"),
            "year": m.get("_year"),
            "genres": m.get("genre_ids"),
            "vote_average": m.get("vote_average"),
            "vote_count": m.get("vote_count"),
            "review_count_used": m.get("review_count_used"),
            "emotion": e,
            "emotion_score": round(float(m.get("emotions_avg", {}).get(e, 0.0)), 3),
            "emotions_avg": m.get("emotions_avg"),  # 全感情プロファイル
            "overview": m.get("overview"),
            "genre_ids": m.get("genre_ids", []),
        })
    return out

# ====== CLI ======
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Recommend movies by emotion (Step 3).")
    p.add_argument("--emotion", "-e", required=True,
                   help="Emotion: joy | sadness | anger | fear | love | surprise (or simple synonyms)")
    p.add_argument("--topk", "-k", type=int, default=10, help="Top N results (default: 10)")
    p.add_argument("--min-review-count", type=int, default=5, help="Minimum reviews used in averaging")
    p.add_argument("--min-vote-count", type=int, default=0, help="Minimum TMDb vote_count")
    p.add_argument("--min-vote-average", type=float, default=0.0, help="Minimum TMDb vote_average")
    p.add_argument("--year-min", type=int)
    p.add_argument("--year-max", type=int)
    p.add_argument("--include-genres", type=str, help="Comma-separated genre IDs to include (e.g., 18,35)")
    p.add_argument("--exclude-genres", type=str, help="Comma-separated genre IDs to exclude")
    p.add_argument("--query", type=str, help="Keyword contained in title or overview (case-insensitive)")
    p.add_argument("--no-boost", action="store_true", help="Disable confidence boost by review counts")
    return p.parse_args()

def _parse_genre_list(s: Optional[str]) -> Optional[List[int]]:
    if not s:
        return None
    return [int(x) for x in re.split(r"[,\s]+", s.strip()) if x]

def main():
    args = _parse_args()
    yr = None
    if args.year_min is not None and args.year_max is not None:
        yr = (args.year_min, args.year_max)

    flt = Filters(
        min_review_count=args.min_review_count,
        min_vote_count=args.min_vote_count,
        min_vote_average=args.min_vote_average,
        year_range=yr,
        include_genres=_parse_genre_list(args.include_genres),
        exclude_genres=_parse_genre_list(args.exclude_genres),
        query_text=args.query,
    )

    results = recommend_by_emotion(
        target_emotion=args.emotion,
        top_k=args.topk,
        filters=flt,
        use_confidence_boost=not args.no_boost,
    )

    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
