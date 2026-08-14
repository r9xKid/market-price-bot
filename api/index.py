from http.server import BaseHTTPRequestHandler
import json
import urllib.request


class handler(BaseHTTPRequestHandler):

    def do_GET(self):

        try:
            url = "https://call5.tgju.org/ajax.json"

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Referer": "https://www.tgju.org/"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=15
            ) as response:

                raw = response.read().decode(
                    "utf-8",
                    errors="ignore"
                )

            data = json.loads(raw)

            body = json.dumps(
                {
                    "success": True,
                    "tgju_data": data
                },
                ensure_ascii=False
            ).encode("utf-8")

            self.send_response(200)

        except Exception as e:

            body = json.dumps(
                {
                    "success": False,
                    "error": str(e)
                },
                ensure_ascii=False
            ).encode("utf-8")

            self.send_response(500)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)
