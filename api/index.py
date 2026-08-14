from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone


# =========================================================
# TGJU
# =========================================================

def get_tgju_data():
    urls = [
        "https://call1.tgju.org/ajax.json",
        "https://call2.tgju.org/ajax.json",
        "https://call3.tgju.org/ajax.json",
        "https://call4.tgju.org/ajax.json",
        "https://call5.tgju.org/ajax.json",
    ]

    last_error = None

    for url in urls:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": "https://www.tgju.org/",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=10
            ) as response:
                raw = response.read().decode(
                    "utf-8",
                    errors="ignore"
                )

            data = json.loads(raw)

            if isinstance(data, dict) and "current" in data:
                return data

        except Exception as e:
            last_error = e

    raise Exception(
        f"Unable to get TGJU data: {last_error}"
    )


def get_tgju_prices():
    data = get_tgju_data()

    current = data.get("current", {})

    def get_price(key):
        item = current.get(key)

        if item is None:
            raise Exception(
                f"TGJU key not found: {key}"
            )

        if isinstance(item, dict):
            value = (
                item.get("p")
                or item.get("price")
                or item.get("last")
                or item.get("value")
            )
        else:
            value = item

        if value is None:
            raise Exception(
                f"TGJU price not found: {key}"
            )

        return float(
            str(value)
            .replace(",", "")
            .replace("٬", "")
            .replace(" ", "")
        )

    # TGJU prices are Rial.
    # Convert to Toman.

    usd_toman = (
        get_price("price_dollar_rl") / 10
    )

    gold_18g = (
        get_price("tgju_gold_irg18") / 10
    )

    silver_g = (
        get_price("silver_999") / 10
    )

    return {
        "usd_toman": usd_toman,
        "gold_18g": gold_18g,
        "silver_g": silver_g,
    }


# =========================================================
# Yahoo Finance
# =========================================================

def get_yahoo_price(symbol):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol)
        + "?range=1d&interval=2m"
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10
    ) as response:
        data = json.loads(
            response.read().decode("utf-8")
        )

    result = data["chart"]["result"][0]

    price = result["meta"].get(
        "regularMarketPrice"
    )

    if price is None:
        raise Exception(
            f"No Yahoo price for {symbol}"
        )

    return float(price)


# =========================================================
# Supabase
# =========================================================

def supabase_request(
    method,
    path,
    data=None
):
    base = os.environ[
        "SUPABASE_URL"
    ].rstrip("/")

    key = os.environ[
        "SUPABASE_KEY"
    ]

    body = None

    if data is not None:
        body = json.dumps(
            data
        ).encode("utf-8")

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

    with urllib.request.urlopen(
        request,
        timeout=10
    ) as response:

        raw = response.read().decode(
            "utf-8"
        )

        if not raw:
            return []

        return json.loads(raw)


def get_previous(asset):
    asset_encoded = urllib.parse.quote(
        asset,
        safe=""
    )

    rows = supabase_request(
        "GET",
        "prices?"
        f"asset=eq.{asset_encoded}"
        "&select=price"
        "&order=updated_at.desc"
        "&limit=1"
    )

    if not rows:
        return None

    return float(
        rows[0]["price"]
    )


def save_price(
    asset,
    price
):
    supabase_request(
        "POST",
        "prices",
        {
            "asset": asset,
            "price": price,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        },
    )


# =========================================================
# Telegram
# =========================================================

def send_telegram(message):
    token = os.environ[
        "TELEGRAM_BOT_TOKEN"
    ]

    chat_id = os.environ[
        "TELEGRAM_CHANNEL_ID"
    ]

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=10
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


# =========================================================
# Market Update
# =========================================================

def do_market_update():

    # -----------------------------------------
    # TGJU
    # -----------------------------------------

    tgju = get_tgju_prices()

    gold_18g = tgju[
        "gold_18g"
    ]

    silver_g = tgju[
        "silver_g"
    ]

    usd_toman = tgju[
        "usd_toman"
    ]

    # -----------------------------------------
    # Global Oil
    # -----------------------------------------

    wti = get_yahoo_price(
        "CL=F"
    )

    brent = get_yahoo_price(
        "BZ=F"
    )

    # -----------------------------------------
    # All prices
    # -----------------------------------------

    prices = {
        "gold_18g": gold_18g,
        "silver_g": silver_g,
        "usd_toman": usd_toman,
        "wti": wti,
        "brent": brent,
    }

    # -----------------------------------------
    # Calculate changes
    # -----------------------------------------

    changes = {}

    for asset, price in prices.items():

        previous = get_previous(
            asset
        )

        if (
            previous is not None
            and previous != 0
        ):
            change = (
                (price - previous)
                / previous
            ) * 100
        else:
            change = 0

        changes[asset] = change

        save_price(
            asset,
            price
        )

    # -----------------------------------------
    # Direction
    # -----------------------------------------

    def arrow(value):
        if value > 0:
            return "▲"

        if value < 0:
            return "▼"

        return "—"

    # -----------------------------------------
    # Telegram message
    # -----------------------------------------

    message = (
        "📊 نوسان بازار\n"
        "\n"

        "🥇 طلای ۱۸ عیار\n"
        f"{gold_18g:,.0f} تومان "
        f"{arrow(changes['gold_18g'])} "
        f"{abs(changes['gold_18g']):.2f}%\n"
        "\n"

        "🥈 نقره ۹۹۹\n"
        f"{silver_g:,.0f} تومان "
        f"{arrow(changes['silver_g'])} "
        f"{abs(changes['silver_g']):.2f}%\n"
        "\n"

        "💵 دلار آزاد\n"
        f"{usd_toman:,.0f} تومان "
        f"{arrow(changes['usd_toman'])} "
        f"{abs(changes['usd_toman']):.2f}%\n"
        "\n"

        "🛢 WTI\n"
        f"${wti:,.2f} "
        f"{arrow(changes['wti'])} "
        f"{abs(changes['wti']):.2f}%\n"
        "\n"

        "🛢 Brent\n"
        f"${brent:,.2f} "
        f"{arrow(changes['brent'])} "
        f"{abs(changes['brent']):.2f}%\n"
        "\n"

        f"⏱ {datetime.now().strftime('%H:%M')}"
    )

    # -----------------------------------------
    # Send only when movement >= 0.10%
    # -----------------------------------------

    significant = any(
        abs(change) >= 0.10
        for change in changes.values()
    )

    if significant:
        send_telegram(
            message
        )

    return prices, changes


# =========================================================
# Vercel Handler
# =========================================================

class handler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        try:

            prices, changes = (
                do_market_update()
            )

            body = json.dumps(
                {
                    "success": True,
                    "prices": prices,
                    "changes": changes,
                },
                ensure_ascii=False,
            ).encode("utf-8")

            self.send_response(200)

        except Exception as e:

            body = json.dumps(
                {
                    "success": False,
                    "error": str(e),
                },
                ensure_ascii=False,
            ).encode("utf-8")

            self.send_response(500)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(body)
