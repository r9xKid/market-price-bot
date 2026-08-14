from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse
import urllib.request


def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHANNEL_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    request = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            result = send_telegram(
                "🤖 تست موفق!\n\n"
                "ربات Market Price Bot با موفقیت به کانال متصل شد."
            )

            body = json.dumps({
                "success": True,
                "telegram": result
            }).encode()

            self.send_response(200)

        except Exception as e:
            body = json.dumps({
                "success": False,
                "error": str(e)
            }).encode()

            self.send_response(500)

        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)
