from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone


# ==========================================
# Yahoo Finance
# ==========================================

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
        data = json.loads(response.read().decode("utf-8"))

    result = data["chart"]["result"][0]
    price = result["meta"].get("regularMarketPrice")

    if price is None:
        raise Exception(f"No price for {symbol}")

    return float(price)


# ==========================================
# TGJU Live Data
# ==========================================

def get_tgju_data():

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
        timeout=10
    ) as response:

        raw = response.read().decode(
            "utf-8",
            errors="ignore"
        )

    return json.loads(raw)


def find_value(obj, wanted_keys):

    if isinstance(obj, dict):

        for key in wanted_keys:

            if key in obj:
                value = obj[key]

                if isinstance(value, dict):

                    for subkey in [
                        "p",
                        "price",
                        "last",
                        "value",
                        "close"
                    ]:

                        if subkey in value:
                            return value[subkey]

                return value

        for value in obj.values():

            result = find_value(
                value,
                wanted_keys
            )

            if result is not None:
                return result

    elif isinstance(obj, list):

        for item in obj:

            result = find_value(
                item,
                wanted_keys
            )

            if result is not None:
                return result

    return None


def number(value):

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value)

    text = (
        text
        .replace(",", "")
        .replace("٬", "")
        .replace(" ", "")
    )

    return float(text)


def get_tgju_prices():

    data = get_tgju_data()

    # دلار آزاد
    usd = find_value(
        data,
        [
            "price_dollar_rl",
            "dollar_rl",
            "usd_irr"
        ]
    )

    # طلای 18 عیار
    gold18 = find_value(
        data,
        [
            "tgju_gold_irg18",
            "gold_18k",
            "gold_18"
        ]
    )

    # طلای 24 عیار
    gold24 = find_value(
        data,
        [
            "tgju_gold_irg24",
            "gold_24k",
            "gold_24"
        ]
    )

    # نقره
    silver = find_value(
        data,
        [
            "tgju_silver_irg",
            "silver_999",
            "silver"
        ]
    )

    if usd is None:
        raise Exception(
            "TGJU USD price not found"
        )

    if gold18 is None:
        raise Exception(
            "TGJU 18K gold price not found"
        )

    if gold24 is None:
        raise Exception(
            "TGJU 24K gold price not found"
        )

    if silver is None:
        raise Exception(
            "TGJU silver price not found"
        )

    # TGJU قیمت‌ها را به ریال می‌دهد
    # ما در کانال تومان می‌خواهیم

    usd_toman = number(usd) / 10
    gold18_toman = number(gold18) / 10
    gold24_toman = number(gold24) / 10
    silver_toman = number(silver) / 10

    return {
        "usd_toman": usd_toman,
        "gold_18g": gold18_toman,
        "gold_24g": gold24_toman,
        "silver_g": silver_toman
    }


# ==========================================
# Supabase
# ==========================================

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
            "Prefer": "return=representation"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=10
    ) as response:

        raw = response.read().decode()

        return (
            json.loads(raw)
            if raw
            else []
        )


def get_previous(asset):

    asset_encoded = urllib.parse.quote(
        asset,
        safe=""
    )

    rows = supabase_request(
        "GET",
        f"prices?"
        f"asset=eq.{asset_encoded}"
        f"&select=price"
        f"&order=updated_at.desc"
        f"&limit=1"
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
            ).isoformat()
        }
    )


# ==========================================
# Telegram
# ==========================================

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

    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message
        }
    ).encode()

    request = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(
        request,
        timeout=10
    ) as response:

        return json.loads(
            response.read().decode()
        )


# ==========================================
# Main
# ==========================================

def do_market_update():

    # ------------------------------
    # TGJU
    # ------------------------------

    tgju = get_tgju_prices()

    usd_toman = tgju[
        "usd_toman"
    ]

    gold_18g = tgju[
        "gold_18g"
    ]

    gold_24g = tgju[
        "gold_24g"
    ]

    silver_g = tgju[
        "silver_g"
    ]

    # ------------------------------
    # جهانی
    # ------------------------------

    wti = get_yahoo_price(
        "CL=F"
    )

    brent = get_yahoo_price(
        "BZ=F"
    )

    prices = {

        "gold_18g":
            gold_18g,

        "gold_24g":
            gold_24g,

        "silver_g":
            silver_g,

        "usd_toman":
            usd_toman,

        "wti":
            wti,

        "brent":
            brent
    }

    # ------------------------------
    # Changes
    # ------------------------------

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

    # ------------------------------
    # Message
    # ------------------------------

    def arrow(value):

        if value > 0:
            return "▲"

        if value < 0:
            return "▼"

        return "—"

    message = (
        "📊 بازار لحظه‌ای\n"
        "\n"

        f"🥇 طلای ۱۸ عیار\n"
        f"{gold_18g:,.0f} تومان "
        f"{arrow(changes['gold_18g'])} "
        f"{abs(changes['gold_18g']):.2f}%\n"
        "\n"

        f"🥇 طلای ۲۴ عیار\n"
        f"{gold_24g:,.0f} تومان "
        f"{arrow(changes['gold_24g'])} "
        f"{abs(changes['gold_24g']):.2f}%\n"
        "\n"

        f"🥈 نقره ۹۹۹\n"
        f"{silver_g:,.0f} تومان "
        f"{arrow(changes['silver_g'])} "
        f"{abs(changes['silver_g']):.2f}%\n"
        "\n"

        f"💵 دلار آزاد\n"
        f"{usd_toman:,.0f} تومان "
        f"{arrow(changes['usd_toman'])} "
        f"{abs(changes['usd_toman']):.2f}%\n"
        "\n"

        f"🛢 نفت WTI\n"
        f"${wti:,.2f} "
        f"{arrow(changes['wti'])} "
        f"{abs(changes['wti']):.2f}%\n"
        "\n"

        f"🛢 نفت Brent\n"
        f"${brent:,.2f} "
        f"{arrow(changes['brent'])} "
        f"{abs(changes['brent']):.2f}%\n"
        "\n"

        f"⏱ {datetime.now().strftime('%H:%M')}"
    )

    # ارسال فقط در صورت نوسان 0.10 درصد یا بیشتر

    significant = any(
        abs(x) >= 0.10
        for x in changes.values()
    )

    if significant:

        send_telegram(
            message
        )

    return prices, changes


# ==========================================
# Vercel
# ==========================================

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
                    "changes": changes
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
