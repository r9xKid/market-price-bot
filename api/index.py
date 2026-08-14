from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone


SYMBOLS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "wti": "CL=F",
    "brent": "BZ=F",
}


def get_yahoo_price(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?range=1d&interval=2m"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode())

    result = data["chart"]["result"][0]
    return float(result["meta"]["regularMarketPrice"])


def get_usd_toman():
    urls = [
        "https://english.tgju.org/profile/price_dollar_rl",
        "https://www.tgju.org/profile/price_dollar_rl",
    ]

    for url in urls:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            with urllib.request.urlopen(request, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # English TGJU:
            # Last: 1,605,400
            match = re.search(
                r"(?:Last|نرخ فعلی)\s*[:：]?\s*([0-9,]+)",
                html,
                re.IGNORECASE
            )

            if match:
                rial = int(match.group(1).replace(",", ""))
                return rial / 10

        except Exception:
            continue

    raise Exception("Unable to get USD/IRR from TGJU")


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

    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw else []


def get_previous(asset):
    rows = supabase_request(
        "GET",
        f"prices?asset=eq.{asset}"
        f"&select=price"
        f"&order=updated_at.desc"
        f"&limit=1"
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

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


def do_market_update():

    # -------------------------
    # جهانی
    # -------------------------

    gold_oz = get_yahoo_price("GC=F")
    silver_oz = get_yahoo_price("SI=F")
    wti = get_yahoo_price("CL=F")
    brent = get_yahoo_price("BZ=F")

    # -------------------------
    # دلار آزاد
    # -------------------------

    usd_toman = get_usd_toman()

    # یک اونس تروا = 31.1034768 گرم
    TROY_OUNCE_GRAMS = 31.1034768

    # قیمت یک گرم طلای 24 عیار
    gold_24g = (
        gold_oz * usd_toman / TROY_OUNCE_GRAMS
    )

    # قیمت یک گرم طلای 18 عیار
    gold_18g = gold_24g * 0.75

    # قیمت یک گرم نقره
    silver_g = (
        silver_oz * usd_toman / TROY_OUNCE_GRAMS
    )

    prices = {
        "gold_24g": gold_24g,
        "gold_18g": gold_18g,
        "silver_g": silver_g,
        "usd_toman": usd_toman,
        "gold_oz": gold_oz,
        "silver_oz": silver_oz,
        "wti": wti,
        "brent": brent,
    }

    # -------------------------
    # تغییرات
    # -------------------------

    changes = {}

    for asset, price in prices.items():

        previous = get_previous(asset)

        if previous and previous != 0:
            change = ((price - previous) / previous) * 100
        else:
            change = 0

        changes[asset] = change

        save_price(asset, price)

    # -------------------------
    # Telegram message
    # -------------------------

    names = {
        "gold_24g": "🥇 طلای ۲۴ عیار / گرم",
        "gold_18g": "🟡 طلای ۱۸ عیار / گرم",
        "silver_g": "🥈 نقره / گرم",
        "usd_toman": "💵 دلار آزاد",
        "wti": "🛢 نفت WTI",
        "brent": "🛢 نفت Brent",
    }

    lines = [
        "📊 نوسان بازار",
        "",
        f"🥇 طلای ۲۴ عیار",
        f"{gold_24g:,.0f} تومان  "
        f"{'▲' if changes['gold_24g'] >= 0 else '▼'} "
        f"{abs(changes['gold_24g']):.2f}%",
        "",
        f"🟡 طلای ۱۸ عیار",
        f"{gold_18g:,.0f} تومان  "
        f"{'▲' if changes['gold_18g'] >= 0 else '▼'} "
        f"{abs(changes['gold_18g']):.2f}%",
        "",
        f"🥈 نقره / گرم",
        f"{silver_g:,.0f} تومان  "
        f"{'▲' if changes['silver_g'] >= 0 else '▼'} "
        f"{abs(changes['silver_g']):.2f}%",
        "",
        f"💵 دلار آزاد",
        f"{usd_toman:,.0f} تومان  "
        f"{'▲' if changes['usd_toman'] >= 0 else '▼'} "
        f"{abs(changes['usd_toman']):.2f}%",
        "",
        f"🛢 WTI",
        f"${wti:,.2f}  "
        f"{'▲' if changes['wti'] >= 0 else '▼'} "
        f"{abs(changes['wti']):.2f}%",
        "",
        f"🛢 Brent",
        f"${brent:,.2f}  "
        f"{'▲' if changes['brent'] >= 0 else '▼'} "
        f"{abs(changes['brent']):.2f}%",
        "",
        "⏱ " + datetime.now().strftime("%H:%M"),
    ]

    # اگر هرکدام حداقل 0.10% تغییر کرده باشد
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

            body = json.dumps(
                {
                    "success": True,
                    "prices": prices,
                    "changes": changes,
                },
                ensure_ascii=False
            ).encode("utf-8")

            self.send_response(200)

        except Exception as e:

            body = json.dumps(
                {
                    "success": False,
                    "error": str(e),
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
