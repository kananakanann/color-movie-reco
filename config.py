# myproject/config.py

# ====== 必須設定 ======
TMDB_API_KEY = "ec8dafa527d136f835ac45ce0553dbae"

# ====== 収集パラメータ ======
# ジャンルは複数指定可能（例：Action=28, Comedy=35, Drama=18）
# 空リスト [] にすると全ジャンルが対象
GENRE_ID = []          
DISCOVER_PAGES = 50         # 映画リストを取得するページ数（1ページ=20作品）
MAX_REVIEWS_PER_MOVIE = 100  # 1映画あたりの最大レビュー数
REVIEWS_LANG = "en"        # "en", "ja" など。Noneなら全言語
REQUEST_SLEEP_SEC = 0.12   # API呼び出し間隔（秒）
MAX_RETRIES = 3            # APIリトライ回数

#====データ増やす手順====
#１．DISCOVER_PAGES のパラメータをいじる
#２．py collect_movies.pyを実行
#３．py analyze_emotions.pyを実行
