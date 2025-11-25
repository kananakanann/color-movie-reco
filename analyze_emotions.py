import json
import os
from collections import defaultdict
from typing import Dict, List
from transformers import pipeline

# ========= 入出力 =========
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
REVIEWS_PATH = os.path.join(DATA_DIR, "review_texts.json")   # { "movie_id": ["rev1", "rev2", ...] }
MOVIES_PATH  = os.path.join(DATA_DIR, "movies_data.json")    # [ {id, title, ...}, ... ]
OUTPUT_PATH  = os.path.join(DATA_DIR, "movies_with_emotions.json")

# ========= モデル設定 =========
MODEL_NAME = "nateraw/bert-base-uncased-emotion"
MAX_LEN_CHARS = 2000     # レビューが長すぎる場合は文字数で軽く切る
BATCH_SIZE = 16          # バッチ推論サイズ
ROUND_DECIMALS = 2       # 出力の丸め（例：0.5, 0.17, 0.3）

def analyze_all() -> None:
    # データ読み込み
    with open(REVIEWS_PATH, "r", encoding="utf-8") as f:
        reviews_map: Dict[str, List[str]] = json.load(f)
    with open(MOVIES_PATH, "r", encoding="utf-8") as f:
        movies = json.load(f)

    # 感情分類パイプライン（全ラベルのスコアを返す）
    clf = pipeline("text-classification", model=MODEL_NAME,
                   return_all_scores=True, truncation=True)

    # ラベル順を一度取得（固定化）
    probe = clf(["test"])[0]
    label_order = [x["label"] for x in probe]  # ['sadness','joy','love','anger','fear','surprise']

    def chunk(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i+n]

    # 映画ごとの平均スコアを計算
    movie_emotions: Dict[str, Dict[str, float]] = {}

    for movie in movies:
        mid = str(movie["id"])
        texts = reviews_map.get(mid, [])
        if not texts:
            continue

        # 過度な長文はカット
        texts = [t[:MAX_LEN_CHARS] for t in texts if t and t.strip()]
        if not texts:
            continue

        # ラベル合計値を初期化
        label_sums = defaultdict(float)
        total_reviews = 0

        # バッチ実行
        for batch in chunk(texts, BATCH_SIZE):
            try:
                outputs = clf(batch)  # List[List[{label, score}, ...]]
            except Exception as e:
                print(f"[WARN] Inference failed for movie_id={mid} ({movie.get('title')}): {e}")
                continue

            for res in outputs:
                if not res:
                    continue
                for item in res:
                    label_sums[item["label"]] += float(item["score"])
                total_reviews += 1

        if total_reviews == 0:
            continue

        # 平均スコア
        avg_scores = {lbl: (label_sums.get(lbl, 0.0) / total_reviews) for lbl in label_order}
        avg_scores_rounded = {lbl: round(score, ROUND_DECIMALS) for lbl, score in avg_scores.items()}
        movie_emotions[mid] = avg_scores_rounded

    # 出力用に movies に結合
    enriched = []
    for movie in movies:
        mid = str(movie["id"])
        scores = movie_emotions.get(mid)
        if not scores:
            continue
        # 代表感情（平均スコア最大）
        rep = max(scores.items(), key=lambda kv: kv[1])[0]
        movie_out = dict(movie)
        movie_out["emotions_avg"] = scores
        movie_out["representative_emotion"] = rep
        movie_out["review_count_used"] = len(reviews_map.get(mid, []))
        enriched.append(movie_out)

    # 保存
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved: {OUTPUT_PATH}")
    print(f"   Movies analyzed: {len(enriched)}")
    if enriched:
        print("   Example:", enriched[0]["title"], enriched[0]["emotions_avg"])

if __name__ == "__main__":
    analyze_all()
