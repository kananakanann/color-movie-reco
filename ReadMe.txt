Flask サーバーアクセス方法まとめ

1. 同じ Wi-Fi にいる場合（ローカル LAN アクセス）

条件
-PC とスマホが同じ Wi-Fi（同じSSID）に接続している
-PCで py app.py を起動している

アクセスURL
http://（PCのIPアドレス）:5000

app.pyを実行して，一番下の
 * Running on http:
のURLから飛べる

------------------------------------------------------------------------

2. 違う Wi-Fi にいる場合（ngrok を使用して外部公開）

条件
１．PCで Flask (py app.py) を起動している
２．別のPowerShellで ngrok http 5000 を実行している


C:\Users\admin\Downloads\ngrok-v3-stable-windows-amd64>
の場所で
ngrok http 5000
を実行

Forwarding https://extravascular-initiatorily-willis.ngrok-free.dev -> http://localhost:5000

この最初のURLに飛ぶ


注意点
- 無料版 ngrok は起動ごとにURLが変わる
- PCやngrokを閉じるとアクセス不可になる
- HTTPSでスマホからも安全に利用できる
