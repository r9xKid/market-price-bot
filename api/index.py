from http.server import BaseHTTPRequestHandler
import json
import urllib.request


SYMBOLS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "wti": "CL=F",
    "brent": "BZ=F",
}


def get_price(symbol):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?range=1d&interval=2m"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode())

    result = data["chart"]["result"][0]
    meta = result["meta"]

    return meta.get("regularMarketPrice")


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            import urllib.parse

            prices = {}

            for name, symbol in SYMBOLS.items():
                prices[name] = get_price(symbol)

            body = json.dumps({
                "success": True,
                "prices": prices
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
