# -*- coding: utf-8 -*-
"""
color_emotion_answers.csv から
色ごとの加重平均分布＋上位2感情(閾値=0で常に最大2)を算出し、
CSVとJSONの両方で保存するスクリプト。
"""

import pandas as pd
import json
from pathlib import Path

# ========== パス設定 ==========
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INPUT_CSV = DATA_DIR / "color_emotion_answers.csv"
OUTPUT_CSV = DATA_DIR / "color_top2.csv"
OUTPUT_JSON = DATA_DIR / "color_top2.json"

# ========== 定数 ==========
# stageごとの重み（一次0.8 / 二次0.2 / 三次0）
STAGE_WEIGHTS = {1: 0.8, 2: 0.2, 3: 0.0}
# 閾値（0により常に2つ採用：2位が負でない限り条件を満たす）
THRESHOLD = 0.3

# ========== 感情名ゆれマップ ==========
ALIAS = {
    # タイポ
    "amger": "anger",
    "fwar": "fear",

    # 主要6感情
    "anger": "anger",
    "fear": "fear", "恐怖": "fear",
    "joy": "joy", "ほんわかする": "joy", "陽気": "joy",
    "sadness": "sadness", "切なさ": "sadness",
    "love": "love", "愛": "love", "やさしさ": "love",
    "surprise": "surprise", "驚き": "surprise",
    "N": "none",
}

def main():
    # 読み込み
    df = pd.read_csv(INPUT_CSV, encoding="utf-8")

    # 前処理
    for col in ["color_code", "color_name", "raw_label"]:
        df[col] = df[col].astype(str).str.strip()

    # stage/percent の型を厳格化
    df["stage"] = pd.to_numeric(df["stage"], errors="coerce").astype("Int64")
    # percentは%記号や全角混入にも耐性
    df["percent"] = (
        df["percent"]
        .astype(str)
        .str.replace("％", "%", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("%", "", regex=False)
    )
    df["percent"] = pd.to_numeric(df["percent"], errors="coerce")

    # 有効行のみ残す
    df = df.dropna(subset=["color_code", "color_name", "stage", "raw_label", "percent"])
    df = df[df["percent"] >= 0]

    # ラベル正規化
    df["base_emotion"] = df["raw_label"].map(ALIAS).fillna(df["raw_label"])
    # none は除外
    df = df[df["base_emotion"] != "none"]

    # 加重平均
    df["weighted_percent"] = df.apply(
        lambda r: r["percent"] * STAGE_WEIGHTS.get(int(r["stage"]), 0.0),
        axis=1
    )

    results = []
    for (color, name), group in df.groupby(["color_code", "color_name"], sort=False):
        sum_w = group["weighted_percent"].sum()
        if sum_w == 0:
            # すべてnone等で除外されたケース
            continue

        agg = (
            group.groupby("base_emotion", as_index=False)["weighted_percent"].sum()
            .sort_values("weighted_percent", ascending=False)
        )
        agg["prob"] = agg["weighted_percent"] / sum_w

        # 上位2件
        top = agg.head(2)
        top_emotions = top["base_emotion"].tolist()
        top_probs = top["prob"].tolist()

        # 閾値判定
        if len(top_probs) > 1 and top_probs[1] < THRESHOLD * top_probs[0]:
            top_emotions = [top_emotions[0]]
            top_probs = [top_probs[0]]

        results.append({
            "color_code": color,
            "color_name": name,
            "top_emotions": top_emotions,
            "probs": [round(float(p), 3) for p in top_probs],
        })

    # 出力
    out_df = pd.DataFrame(results)
    out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"✅ Saved CSV → {OUTPUT_CSV}")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print(f"✅ Saved JSON → {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
