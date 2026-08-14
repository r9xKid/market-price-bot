from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone


SYMBOLS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "wti": "CL=F",
    "brent": "BZ=F",
}


def get_price(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?range=1d&interval=2m"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        data = json.loads(response.read().decode())

    return data["chart"]["result"][0]["meta"]["regularMarketPrice"]


def supabase_request(method, path, data=None):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]

    body = None

    if data is not None:
        body = json.dumps(data).encode()

    request = urllib.request.Request(
        base + "/rest/v1/" + path,
        data=body,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else []


def get_previous(asset):
    rows = supabase_request(
        "GET",
        f"prices?asset=eq.{asset}&select=price&order=updated_at.desc&limit=1"
    )

    if not rows:
        return None

    return float(rows[0]["price"])


def save_price(asset, price):
    supabase_request(
        "POST",
        "prices",
        {
            "asset": asset,
            "price": price,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHANNEL_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
    }).encode()

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode())


def do_market_update():
    prices = {}

    for asset, symbol in SYMBOLS.items():
        prices[asset] = get_price(symbol)

    changes = {}

    for asset, price in prices.items():
        previous = get_previous(asset)

        if previous and previous != 0:
            change = ((price - previous) / previous) * 100
            changes[asset] = change
        else:
            changes[asset] = 0

        save_price(asset, price)

    lines = [
        "📊 نوسان بازار",
        "",
    ]

    names = {
        "gold": "🥇 طلا",
        "silver": "🥈 نقره",
        "wti": "🛢 WTI",
        "brent": "🛢 Brent",
    }

    for asset in SYMBOLS:
        change = changes[asset]

        if change == 0:
            continue

        arrow = "▲" if change > 0 else "▼"

        lines.append(
            f"{names[asset]}\n"
            f"${prices[asset]:,.2f}  {arrow} {abs(change):.2f}%"
        )
        lines.append("")

    lines.append(
        "⏱ " + datetime.now().strftime("%H:%M")
    )

    # فقط وقتی حداقل یک دارایی 0.10% تغییر کرده باشد پیام می‌فرستیم
    significant = any(
        abs(change) >= 0.10
        for change in changes.values()
    )

    if significant:
        send_telegram("\n".join(lines))

    return prices, changes


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            prices, changes = do_market_update()

            body = json.dumps({
                "success": True,
                "prices": prices,
                "changes": changes,
            }).encode()

            self.send_response(200)

        except Exception as e:
            body = json.dumps({
                "success": False,
                "error": str(e),
            }).encode()

            self.send_response(500)

        self.send_header(
            "Content-Type",
            "application/json"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.end_headers()

        self.wfile.write(body)
