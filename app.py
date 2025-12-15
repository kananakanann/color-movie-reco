# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for

import os
import json
from datetime import datetime

from recommend import recommend_by_emotion, Filters, ALLOWED_EMOTIONS


def create_app():
    app = Flask(__name__)

    # ------- ログ用設定 -------
    LOG_DIR = "logs"
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, "color_experiment_log.jsonl")

    # ---------- 感情→映画（既存） ----------
    @app.get("/")
    def index():
        """
        トップ画面（感情で探す）。
        emotion パラメータが無いときは /color にリダイレクトする。
        emotion が指定されているときは従来通りレコメンド実行。
        """
        emotion = (request.args.get("emotion") or "").strip()

        # 初手アクセス（emotion が空）のときは /color へ飛ばす
        if not emotion:
            return redirect(url_for("color_page"))

        topk = _to_int(request.args.get("topk"), default=10)
        min_review_count = _to_int(request.args.get("min_review_count"), default=5)
        min_vote_count = _to_int(request.args.get("min_vote_count"), default=0)
        min_vote_average = _to_float(request.args.get("min_vote_average"), default=0.0)
        year_min = _to_int(request.args.get("year_min"))
        year_max = _to_int(request.args.get("year_max"))
        include_genres = _parse_genre_list(request.args.get("include_genres"))
        exclude_genres = _parse_genre_list(request.args.get("exclude_genres"))
        query = (request.args.get("query") or "").strip()
        use_boost = request.args.get("use_boost", "1") != "0"  # "0"なら無効

        results = None
        error_msg = None

        if emotion:
            if emotion.lower() not in ALLOWED_EMOTIONS:
                error_msg = f"emotion は {sorted(ALLOWED_EMOTIONS)} から選んでください。"
            else:
                yr = None
                if year_min is not None and year_max is not None:
                    if year_min > year_max:
                        year_min, year_max = year_max, year_min
                    yr = (year_min, year_max)

                filters = Filters(
                    min_review_count=min_review_count,
                    min_vote_count=min_vote_count,
                    min_vote_average=min_vote_average,
                    year_range=yr,
                    include_genres=include_genres,
                    exclude_genres=exclude_genres,
                    query_text=query or None,
                )
                try:
                    results = recommend_by_emotion(
                        target_emotion=emotion,
                        top_k=topk,
                        filters=filters,
                        use_confidence_boost=use_boost,
                    )
                except FileNotFoundError as e:
                    error_msg = f"{e}（先に Step2: analyze_emotions.py を実行して JSON を生成してください）"
                except ValueError as e:
                    error_msg = str(e)
                except Exception as e:
                    error_msg = f"サーバー側でエラーが発生しました: {e}"

        return render_template(
            "index.html",
            emotions=sorted(ALLOWED_EMOTIONS),
            form=dict(
                emotion=emotion,
                topk=topk,
                min_review_count=min_review_count,
                min_vote_count=min_vote_count,
                min_vote_average=min_vote_average,
                year_min=year_min,
                year_max=year_max,
                include_genres=",".join(map(str, include_genres)) if include_genres else "",
                exclude_genres=",".join(map(str, exclude_genres)) if exclude_genres else "",
                query=query,
                use_boost="1" if use_boost else "0",
            ),
            results=results,
            error_msg=error_msg,
        )

    # ---------- 色UIページ ----------
    @app.get("/color")
    def color_page():
        return render_template("colors.html")

    # ---------- 色→推定感情→映画レコメンド（JSON） ----------
    #　ここいらない？？ 消したらダメだった
    @app.post("/api/recommend_by_emotion_from_color")
    def api_recommend_by_emotion_from_color():
        """
        JSON入力例:
        {
          "emotion": "joy",
          "topk": 20,
          "min_review_count": 5,
          "use_boost": true
        }
        """
        data = request.get_json(force=True) or {}
        emotion = (data.get("emotion") or "").strip()
        topk = int(data.get("topk", 10))
        min_review_count = int(data.get("min_review_count", 5))
        use_boost = bool(data.get("use_boost", True))

        if not emotion:
            return jsonify({"error": "emotion が空です。"}), 400
        if emotion.lower() not in ALLOWED_EMOTIONS:
            return jsonify({"error": f"emotion は {sorted(ALLOWED_EMOTIONS)} から選んでください。"}), 400

        filters = Filters(min_review_count=min_review_count)
        try:
            recs = recommend_by_emotion(
                target_emotion=emotion,
                top_k=topk,
                filters=filters,
                use_confidence_boost=use_boost,
            )
        except FileNotFoundError as e:
            return jsonify({"error": f"{e}（先に Step2: analyze_emotions.py を実行して JSON を生成してください）"}), 500
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"サーバー側でエラーが発生しました: {e}"}), 500

        return jsonify({"results": recs})

        
    # ---------- 色実験ログ保存用API ----------
    @app.post("/api/log_color_experiment")
    def log_color_experiment():
        """
        実験用ログ保存API。

        JSON例：
        {
          "selected_colors": ["#ff6699", "#ffff00"],
          "inferred_emotions": ["love", "joy"],
          "color_details": [...],          // selected 配列そのままでもOK
          "topk": 10,
          "min_review_count": 5,
          "use_boost": true,
          "recommend_results": {
              "love": [ {...}, {...}, ... ],
              "joy":  [ {...}, {...}, ... ]
          }
        }
        """
        data = request.get_json(force=True) or {}

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "selected_colors": data.get("selected_colors"),
            "inferred_emotions": data.get("inferred_emotions"),
            "color_details": data.get("color_details"),
            "topk": data.get("topk"),
            "min_review_count": data.get("min_review_count"),
            "use_boost": data.get("use_boost"),
            "recommend_results": data.get("recommend_results"),
        }

        # JSON Lines 形式で1行ごとに追記
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return jsonify({"status": "ok"})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # ---------- ログ確認用 ----------
    @app.get("/admin/logs")
    def view_logs():
        """
        実験ログをブラウザで確認する簡易ビュー。
        """
        if not os.path.exists(LOG_FILE):
            return "ログファイルがまだありません。", 404

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 最新が下、読みやすいように <pre>で囲む
        html = "<h2>Color Experiment Logs</h2><pre>"
        html += "".join(lines)
        html += "</pre>"
        return html


    return app

# グローバルな app 変数を作る
app = create_app()


# ------- ユーティリティ -------
def _to_int(s, default=None):
    try:
        return int(s) if s not in (None, "") else default
    except ValueError:
        return default


def _to_float(s, default=None):
    try:
        return float(s) if s not in (None, "") else default
    except ValueError:
        return default


def _parse_genre_list(s):
    if not s:
        return None
    import re
    vals = [x for x in re.split(r"[,\s]+", s.strip()) if x]
    try:
        nums = [int(v) for v in vals]
        return nums if nums else None
    except ValueError:
        return None


if __name__ == "__main__":
    # ローカルで python app.py したとき用
    port = int(os.getenv("PORT", "5000"))
    #app = create_app() 
    app.run(host="0.0.0.0", port=port, debug=True)