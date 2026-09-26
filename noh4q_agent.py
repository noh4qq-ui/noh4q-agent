#!/usr/bin/env python3
"""
NOH4Q AGENT - PHASE 4C + COMMODITIES
Social: Telegram + Discord + Bluesky + Mastodon
Blogs: Telegraph + Beehiiv
Trading: FOREX + COMMODITIES (Gold, Silver, Oil) Paper Trading
"""

import os
import json
import logging
import threading
import time
import sqlite3
import random
import requests
import urllib.parse
from datetime import datetime
from flask import Flask, jsonify

# ============================================
# CONFIG
# ============================================
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
COHERE_KEY = os.getenv("COHERE_API_KEY", "")
HF_KEY = os.getenv("HF_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.getenv("BLUESKY_PASSWORD", "")
MASTODON_URL = os.getenv("MASTODON_URL", "")
MASTODON_TOKEN = os.getenv("MASTODON_TOKEN", "")
BEEHIIV_API_KEY = os.getenv("BEEHIIV_API_KEY", "")
BEEHIIV_PUBLICATION_ID = os.getenv("BEEHIIV_PUBLICATION_ID", "")

# FOREX settings
FOREX_START_BALANCE = float(os.getenv("FOREX_START_BALANCE", "1000"))
FOREX_RISK_PER_TRADE = float(os.getenv("FOREX_RISK_PER_TRADE", "2"))

# FOREX pairs (fiat only - Frankfurter API)
FOREX_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF"]

# Commodities (via yfinance)
COMMODITY_MAP = {
    "XAU/USD": "GC=F",   # Gold
    "XAG/USD": "SI=F",   # Silver
    "WTI":     "CL=F",   # Crude Oil WTI
    "BRENT":   "BZ=F",   # Brent Crude
    "NATGAS":  "NG=F",   # Natural Gas
    "COPPER":  "HG=F",   # Copper
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# ============================================
# DATABASE
# ============================================
class DB:
    def __init__(self, path="noh4q.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.c = self.conn.cursor()
        self.c.execute("""CREATE TABLE IF NOT EXISTS events
            (id INTEGER PRIMARY KEY, type TEXT, message TEXT, ts TEXT)""")
        self.c.execute("""CREATE TABLE IF NOT EXISTS earnings
            (id INTEGER PRIMARY KEY, source TEXT, amount REAL, ts TEXT)""")
        self.c.execute("""CREATE TABLE IF NOT EXISTS prices
            (id INTEGER PRIMARY KEY, symbol TEXT, price REAL, ts TEXT)""")
        self.c.execute("""CREATE TABLE IF NOT EXISTS content
            (id INTEGER PRIMARY KEY, topic TEXT, content_type TEXT, body TEXT, image_url TEXT, ts TEXT)""")
        self.c.execute("""CREATE TABLE IF NOT EXISTS settings
            (key TEXT PRIMARY KEY, value TEXT)""")
        self.c.execute("""CREATE TABLE IF NOT EXISTS forex_trades
            (id INTEGER PRIMARY KEY, pair TEXT, side TEXT, entry_price REAL,
             exit_price REAL, units REAL, pnl REAL, status TEXT, ts TEXT)""")
        self.c.execute("""CREATE TABLE IF NOT EXISTS forex_price_history
            (id INTEGER PRIMARY KEY, pair TEXT, price REAL, ts TEXT)""")
        self.conn.commit()

    def log(self, etype, message):
        self.c.execute("INSERT INTO events (type, message, ts) VALUES (?,?,?)",
                       (etype, message, datetime.now().isoformat()))
        self.conn.commit()

    def earn(self, source, amount):
        self.c.execute("INSERT INTO earnings (source, amount, ts) VALUES (?,?,?)",
                       (source, amount, datetime.now().isoformat()))
        self.conn.commit()

    def save_price(self, symbol, price):
        self.c.execute("INSERT INTO prices (symbol, price, ts) VALUES (?,?,?)",
                       (symbol, price, datetime.now().isoformat()))
        self.conn.commit()

    def save_forex_price(self, pair, price):
        self.c.execute("INSERT INTO forex_price_history (pair, price, ts) VALUES (?,?,?)",
                       (pair, price, datetime.now().isoformat()))
        self.conn.commit()

    def get_forex_history(self, pair, limit=50):
        self.c.execute("SELECT price, ts FROM forex_price_history WHERE pair=? ORDER BY id DESC LIMIT ?",
                       (pair, limit))
        return list(reversed(self.c.fetchall()))

    def save_content(self, topic, content_type, body, image_url=""):
        self.c.execute("INSERT INTO content (topic, content_type, body, image_url, ts) VALUES (?,?,?,?,?)",
                       (topic, content_type, body, image_url, datetime.now().isoformat()))
        self.conn.commit()

    def save_forex_trade(self, pair, side, entry, exit_price, units, pnl, status):
        self.c.execute("INSERT INTO forex_trades (pair, side, entry_price, exit_price, units, pnl, status, ts) VALUES (?,?,?,?,?,?,?,?)",
                       (pair, side, entry, exit_price, units, pnl, status, datetime.now().isoformat()))
        self.conn.commit()

    def get_open_forex_trades(self):
        self.c.execute("SELECT id, pair, side, entry_price, units FROM forex_trades WHERE status='open'")
        return self.c.fetchall()

    def close_forex_trade(self, trade_id, exit_price, pnl):
        self.c.execute("UPDATE forex_trades SET exit_price=?, pnl=?, status='closed' WHERE id=?",
                       (exit_price, pnl, trade_id))
        self.conn.commit()

    def get_forex_stats(self):
        self.c.execute("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM forex_trades WHERE status='closed'")
        count, total_pnl = self.c.fetchone()
        self.c.execute("SELECT COUNT(*) FROM forex_trades WHERE status='closed' AND pnl > 0")
        wins = self.c.fetchone()[0]
        return {"total_trades": count, "total_pnl": total_pnl, "wins": wins,
                "win_rate": (wins / count * 100) if count > 0 else 0}

    def get_setting(self, key, default=""):
        self.c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = self.c.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        self.c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        self.conn.commit()

    def total(self):
        self.c.execute("SELECT COALESCE(SUM(amount),0) FROM earnings")
        return self.c.fetchone()[0]

db = DB()

# ============================================
# AI BRAIN
# ============================================
def ai_ask(prompt):
    if GEMINI_KEY:
        for attempt in range(2):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_KEY}",
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "safetySettings": [
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                        ]
                    }, timeout=60
                )
                if r.status_code == 200:
                    logger.info("✅ Gemini")
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                elif r.status_code == 503:
                    logger.warning(f"Gemini 503. Retry {attempt+1}/2...")
                    time.sleep(8)
                elif r.status_code == 429:
                    logger.warning("Gemini 429 (quota). Moving on...")
                    break
            except Exception as e:
                logger.warning(f"Gemini exception: {e}")
                break

    if OPENROUTER_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={"model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=45
            )
            if r.status_code == 200:
                logger.info("✅ OpenRouter")
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenRouter exception: {e}")

    if COHERE_KEY:
        try:
            time.sleep(2)
            r = requests.post(
                "https://api.cohere.com/v1/chat",
                headers={"Authorization": f"Bearer {COHERE_KEY}"},
                json={"model": "command-r-08-2024", "message": prompt}, timeout=45
            )
            if r.status_code == 200:
                logger.info("✅ Cohere")
                return r.json()["text"]
        except Exception as e:
            logger.warning(f"Cohere exception: {e}")

    if HF_KEY:
        try:
            r = requests.post(
                "https://router.huggingface.co/hf-inference/models/mistralai/Mistral-7B-Instruct-v0.3",
                headers={"Authorization": f"Bearer {HF_KEY}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 500, "return_full_text": False}},
                timeout=45
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info("✅ HuggingFace")
                    return data[0].get("generated_text", str(data))
                return str(data)
        except Exception as e:
            logger.warning(f"HF exception: {e}")

    logger.error("❌ All AI providers failed")
    return "AI unavailable - fallback mode"

# ============================================
# IMAGE GENERATION
# ============================================
def generate_image_url(prompt, width=1024, height=1024):
    clean_prompt = prompt[:200].strip()
    encoded = urllib.parse.quote(clean_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&model=flux"

def create_image_prompt(topic, body):
    image_prompt = ai_ask(
        f"Create a short, vivid image description (max 15 words) for a social media post about: {topic}. "
        f"Style: modern, digital art, high quality. Return only the description, no quotes."
    )
    if "AI unavailable" in image_prompt:
        image_prompt = f"Digital art of {topic}, modern style, vibrant colors"
    return image_prompt.strip()[:200]

# ============================================
# CRYPTO PRICE
# ============================================
def get_crypto_price(symbol="BTC"):
    crypto_map = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL", "DOGE": "DOGE"}
    fsym = crypto_map.get(symbol.upper(), "BTC")
    try:
        r = requests.get(f"https://api.coinbase.com/v2/prices/{fsym}-USD/spot", timeout=10)
        if r.status_code == 200:
            price = float(r.json()["data"]["amount"])
            db.save_price(symbol.upper(), price)
            return {"symbol": symbol.upper(), "price": price}
    except Exception as e:
        logger.warning(f"Coinbase failed: {e}")
    return {"error": "Price unavailable"}

# ============================================
# FOREX PRICES (Frankfurter API - No Key)
# ============================================
def get_forex_price(pair="EUR/USD"):
    """Fetch live forex rate from Frankfurter API. No key, no signup."""
    try:
        base, quote = pair.split("/")
        url = f"https://api.frankfurter.app/latest?from={base}&to={quote}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            rate = data["rates"].get(quote)
            if rate:
                db.save_forex_price(pair, float(rate))
                return {"pair": pair, "price": float(rate), "date": data.get("date", "")}
    except Exception as e:
        logger.warning(f"Frankfurter {pair} failed: {e}")
    return {"error": f"Could not fetch {pair}"}

# ============================================
# COMMODITIES (Gold, Silver, Oil) - via yfinance
# ============================================
def get_commodity_price(commodity="XAU/USD"):
    """Fetch live commodity price via yfinance. No API key needed."""
    ticker_symbol = COMMODITY_MAP.get(commodity.upper())
    if not ticker_symbol:
        return {"error": f"Commodity {commodity} not supported"}

    try:
        import yfinance as yf
        ticker = yf.Ticker(ticker_symbol)
        price = None
        try:
            price = ticker.fast_info.get("last_price")
        except Exception:
            price = None

        if not price:
            hist = ticker.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])

        if price:
            db.save_price(commodity.upper(), float(price))
            return {"symbol": commodity.upper(), "price": float(price)}
    except Exception as e:
        logger.warning(f"yfinance {commodity} failed: {e}")
    return {"error": f"Could not fetch {commodity}"}

def get_all_prices():
    """Get all forex + commodity prices."""
    result = {}
    for pair in FOREX_PAIRS:
        data = get_forex_price(pair)
        if "error" not in data:
            result[pair] = data["price"]
    for commodity in COMMODITY_MAP.keys():
        data = get_commodity_price(commodity)
        if "error" not in data:
            result[commodity] = data["price"]
    return result

# ============================================
# FOREX PAPER TRADING ENGINE
# ============================================
def get_paper_balance():
    bal = db.get_setting("forex_balance", "")
    if not bal:
        db.set_setting("forex_balance", str(FOREX_START_BALANCE))
        return FOREX_START_BALANCE
    return float(bal)

def set_paper_balance(new_balance):
    db.set_setting("forex_balance", str(round(new_balance, 2)))

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def forex_signal(pair):
    """Generate BUY/SELL/HOLD signal using SMA crossover."""
    history = db.get_forex_history(pair, limit=60)
    if len(history) < 20:
        return "hold", 0

    prices = [h[0] for h in history]
    sma_short = calculate_sma(prices, 5)
    sma_long = calculate_sma(prices, 20)

    if sma_short is None or sma_long is None:
        return "hold", 0

    if sma_short > sma_long * 1.001:
        return "buy", min((sma_short - sma_long) / sma_long * 100, 1.0)
    elif sma_short < sma_long * 0.999:
        return "sell", min((sma_long - sma_short) / sma_long * 100, 1.0)
    return "hold", 0

def get_asset_price(asset):
    """Get price of either forex pair or commodity."""
    if "/" in asset and asset.upper() not in COMMODITY_MAP:
        return get_forex_price(asset)
    return get_commodity_price(asset)

def execute_paper_trade(asset):
    """Execute paper trade on forex pair OR commodity (Gold, Silver, etc.)."""
    signal, strength = forex_signal(asset)
    if signal == "hold":
        return None

    price_data = get_asset_price(asset)
    if "error" in price_data:
        return None

    price = price_data["price"]
    balance = get_paper_balance()
    risk_amount = balance * (FOREX_RISK_PER_TRADE / 100)
    units = round(risk_amount / price, 4) if price > 0 else 0

    if units <= 0:
        return None

    open_trades = db.get_open_forex_trades()
    for t in open_trades:
        if t[1] == asset:
            return None

    db.save_forex_trade(asset, signal, price, 0, units, 0, "open")
    logger.info(f"📈 Opened {signal.upper()} {asset} @ {price:.5f}")
    return {"pair": asset, "side": signal, "price": price, "units": units}

def monitor_paper_trades():
    """Check open trades for stop-loss / take-profit."""
    open_trades = db.get_open_forex_trades()
    for trade in open_trades:
        trade_id, pair, side, entry, units = trade
        price_data = get_asset_price(pair)
        if "error" in price_data:
            continue
        current = price_data["price"]

        if side == "buy":
            pnl = (current - entry) * units
            pct = (current - entry) / entry * 100
        else:
            pnl = (entry - current) * units
            pct = (entry - current) / entry * 100

        if pct >= 1.5 or pct <= -1.0:
            db.close_forex_trade(trade_id, current, round(pnl, 2))
            balance = get_paper_balance() + pnl
            set_paper_balance(balance)
            db.earn("paper_trade", max(pnl, 0))
            logger.info(f"📉 Closed {side.upper()} {pair} @ {current:.5f} | PnL: ${pnl:.2f}")
            return {
                "pair": pair, "side": side, "entry": entry,
                "exit": current, "pnl": pnl, "balance": balance
            }
    return None

def forex_report():
    stats = db.get_forex_stats()
    balance = get_paper_balance()
    open_trades = db.get_open_forex_trades()

    report = f"📊 PAPER TRADING REPORT\n"
    report += f"━━━━━━━━━━━━━━━━━━━\n"
    report += f"💰 Balance: ${balance:.2f}\n"
    report += f"📈 Total PnL: ${stats['total_pnl']:.2f}\n"
    report += f"🎯 Trades: {stats['total_trades']}\n"
    report += f"✅ Win Rate: {stats['win_rate']:.1f}%\n"
    report += f"🔓 Open: {len(open_trades)}\n"

    if open_trades:
        report += f"\n💼 Open Positions:\n"
        for t in open_trades:
            report += f"  • {t[1]} {t[2].upper()} @ {t[3]:.5f}\n"

    return report

# ============================================
# CONTENT GENERATION
# ============================================
def generate_content(topic, content_type="post", with_image=True):
    prompts = {
        "article": f"Write a 400-word informative article about: {topic}. Use clear headings, short paragraphs, and end with a conclusion. Keep it safe and educational.",
        "tweet_thread": f"Write a 3-tweet thread about: {topic}. Each tweet under 280 chars.",
        "script": f"Write a 30-second video script about: {topic}.",
        "post": f"Write an engaging social media post about: {topic}. Include hashtags. Keep under 200 words."
    }
    prompt = prompts.get(content_type, prompts["post"])
    body = ai_ask(prompt)

    image_url = ""
    if with_image and "AI unavailable" not in body:
        image_url = generate_image_url(create_image_prompt(topic, body))

    db.save_content(topic, content_type, body, image_url)
    return {"topic": topic, "type": content_type, "body": body, "image_url": image_url}

# ============================================
# SOCIAL POSTING
# ============================================
def post_to_telegram(text, image_url=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
        return False
    try:
        if image_url:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                json={"chat_id": TELEGRAM_CHANNEL_ID, "photo": image_url, "caption": text[:1024]}, timeout=30
            )
            if r.status_code == 200:
                return True
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4000]}, timeout=10
        )
        return r.status_code == 200
    except:
        return False

def post_to_discord(text, image_url=""):
    if not DISCORD_WEBHOOK:
        return False
    try:
        payload = {"content": text[:1900]}
        if image_url:
            payload["embeds"] = [{"image": {"url": image_url}}]
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=30)
        return r.status_code in [200, 204]
    except:
        return False

def post_to_bluesky(text, image_url=""):
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        return False
    try:
        r = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}, timeout=15
        )
        if r.status_code != 200:
            return False
        session = r.json()
        jwt = session["accessJwt"]
        did = session["did"]
        record = {"text": text[:300], "$type": "app.bsky.feed.post",
                  "createdAt": datetime.now().isoformat() + "Z"}
        if image_url:
            try:
                img_resp = requests.get(image_url, timeout=60)
                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                    up = requests.post(
                        "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
                        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "image/png"},
                        data=img_resp.content, timeout=60
                    )
                    if up.status_code == 200:
                        record["embed"] = {"$type": "app.bsky.embed.images",
                                          "images": [{"alt": text[:100], "image": up.json()["blob"]}]}
            except:
                pass
        r2 = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record}, timeout=30
        )
        return r2.status_code == 200
    except:
        return False

def post_to_mastodon(text, image_url=""):
    if not MASTODON_URL or not MASTODON_TOKEN:
        return False
    try:
        media_ids = []
        if image_url:
            try:
                img_resp = requests.get(image_url, timeout=60)
                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                    up = requests.post(
                        f"{MASTODON_URL}/api/v2/media",
                        headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
                        files={"file": ("i.png", img_resp.content, "image/png")},
                        data={"description": text[:100]}, timeout=60
                    )
                    if up.status_code in [200, 202]:
                        media_ids.append(up.json()["id"])
            except:
                pass
        payload = {"status": text[:500], "visibility": "public"}
        if media_ids:
            payload["media_ids"] = media_ids
        r = requests.post(
            f"{MASTODON_URL}/api/v1/statuses",
            headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
            json=payload, timeout=30
        )
        return r.status_code == 200
    except:
        return False

def post_to_all_platforms(text, image_url=""):
    return {
        "telegram": post_to_telegram(text, image_url),
        "discord": post_to_discord(text, image_url),
        "bluesky": post_to_bluesky(text, image_url),
        "mastodon": post_to_mastodon(text, image_url),
    }

# ============================================
# TELEGRAPH + BEEHIIV
# ============================================
def get_telegraph_token():
    token = db.get_setting("telegraph_token", "")
    if token:
        return token
    try:
        r = requests.post(
            "https://api.telegra.ph/createAccount",
            data={"short_name": "NOH4Q", "author_name": "NOH4Q Agent"}, timeout=15
        )
        if r.status_code == 200 and r.json().get("ok"):
            token = r.json()["result"]["access_token"]
            db.set_setting("telegraph_token", token)
            return token
    except:
        pass
    return ""

def markdown_to_telegraph_nodes(text):
    nodes = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            nodes.append({"tag": "h4", "children": [line[4:]]})
        elif line.startswith("## "):
            nodes.append({"tag": "h3", "children": [line[3:]]})
        elif line.startswith("# "):
            nodes.append({"tag": "h3", "children": [line[2:]]})
        elif line.startswith("- ") or line.startswith("* "):
            nodes.append({"tag": "ul", "children": [{"tag": "li", "children": [line[2:]]}]})
        else:
            nodes.append({"tag": "p", "children": [line]})
    return nodes

def publish_to_telegraph(title, body):
    token = get_telegraph_token()
    if not token:
        return None
    try:
        r = requests.post(
            "https://api.telegra.ph/createPage",
            data={
                "access_token": token,
                "title": title[:256],
                "author_name": "NOH4Q Agent",
                "content": json.dumps(markdown_to_telegraph_nodes(body)),
                "return_content": "false"
            }, timeout=20
        )
        if r.status_code == 200 and r.json().get("ok"):
            return r.json()["result"]["url"]
    except:
        pass
    return None

def publish_to_beehiiv(title, body):
    if not BEEHIIV_API_KEY or not BEEHIIV_PUBLICATION_ID:
        return False
    try:
        r = requests.post(
            f"https://api.beehiiv.com/v2/publications/{BEEHIIV_PUBLICATION_ID}/posts",
            headers={"Authorization": f"Bearer {BEEHIIV_API_KEY}", "Content-Type": "application/json"},
            json={"title": title, "body_content": body.replace("\n", "<br>"), "status": "draft"},
            timeout=30
        )
        return r.status_code == 201
    except:
        return False

def publish_article(topic, body):
    title = f"AI Insights: {topic.title()}"
    return {
        "title": title,
        "telegraph": publish_to_telegraph(title, body),
        "beehiiv": publish_to_beehiiv(title, body) if BEEHIIV_API_KEY else False
    }

# ============================================
# TELEGRAM CONTROL
# ============================================
def tg_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10
        )
    except:
        pass

def tg_poll():
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset + 1, "timeout": 20}, timeout=30
            )
            if r.status_code == 200:
                for update in r.json().get("result", []):
                    offset = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text:
                        handle_command(text, chat_id)
        except:
            pass
        time.sleep(2)

def handle_command(text, chat_id):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = chat_id

    if text == "/start":
        tg_send(f"🤖 NOH4Q Agent v4C (FOREX + Commodities)\nEarned: ${db.total():.2f}\n\n"
                f"Commands:\n"
                f"/forex - live prices (FX + Gold + Oil)\n"
                f"/trade <asset> - paper trade\n"
                f"/balance - paper balance\n"
                f"/fxreport - trading report\n"
                f"/post <topic> <type>\n"
                f"/blog <topic>\n"
                f"/platforms\n"
                f"/ai")

    elif text == "/platforms":
        status = "📢 Platforms:\n"
        status += f"  Telegram: {'✅' if TELEGRAM_CHANNEL_ID else '❌'}\n"
        status += f"  Discord: {'✅' if DISCORD_WEBHOOK else '❌'}\n"
        status += f"  Bluesky: {'✅' if BLUESKY_HANDLE else '❌'}\n"
        status += f"  Mastodon: {'✅' if MASTODON_TOKEN else '❌'}\n"
        status += f"  Telegraph: ✅\n"
        status += f"  Beehiiv: {'✅' if BEEHIIV_API_KEY else '❌'}\n"
        status += f"  FOREX + Commodities: ✅"
        tg_send(status)

    elif text == "/ai":
        tg_send("🧠 AI Providers:\n"
                f"  Gemini: {'✅' if GEMINI_KEY else '❌'}\n"
                f"  OpenRouter: {'✅' if OPENROUTER_KEY else '❌'}\n"
                f"  Cohere: {'✅' if COHERE_KEY else '❌'}\n"
                f"  HuggingFace: {'✅' if HF_KEY else '❌'}")

    elif text == "/forex" or text == "/forex prices":
        msg = "💱 LIVE FOREX PRICES\n"
        msg += "━━━━━━━━━━━━━━━━━━━\n"
        for pair in FOREX_PAIRS:
            data = get_forex_price(pair)
            if "error" not in data:
                msg += f"  {pair}: {data['price']:.5f}\n"

        msg += "\n🥇 COMMODITIES\n"
        msg += "━━━━━━━━━━━━━━━━━━━\n"
        for commodity in ["XAU/USD", "XAG/USD", "WTI", "BRENT", "NATGAS", "COPPER"]:
            data = get_commodity_price(commodity)
            if "error" not in data:
                msg += f"  {commodity}: ${data['price']:,.2f}\n"

        tg_send(msg)

    elif text.startswith("/trade "):
        asset = text[7:].strip().upper()
        # Normalize pair format
        if "-" in asset:
            asset = asset.replace("-", "/")
        trade = execute_paper_trade(asset)
        if trade:
            tg_send(f"✅ Opened {trade['side'].upper()} {trade['pair']} @ {trade['price']:.5f}")
        else:
            tg_send(f"⏸️ No signal for {asset} (HOLD or trade already open). Try EUR/USD, XAU/USD, etc.")

    elif text == "/balance":
        balance = get_paper_balance()
        tg_send(f"💰 Paper Balance: ${balance:.2f}\nStarted with: ${FOREX_START_BALANCE:.2f}")

    elif text == "/fxreport":
        tg_send(forex_report())

    elif text == "/report":
        tg_send(f"📊 Total Earnings: ${db.total():.2f}\n\n" + forex_report())

    elif text.startswith("/ask "):
        tg_send(f"🧠 {ai_ask(text[5:])}")

    elif text.startswith("/post "):
        parts = text[6:].strip().split()
        if len(parts) < 2:
            tg_send("Usage: /post <topic> <type>")
        else:
            topic = " ".join(parts[:-1])
            ctype = parts[-1]
            tg_send(f"🎨 Generating...")
            result = generate_content(topic, ctype, with_image=True)
            if "AI unavailable" in result['body']:
                tg_send("❌ AI failed.")
            else:
                results = post_to_all_platforms(result['body'], result['image_url'])
                success = sum(1 for v in results.values() if v)
                tg_send(f"✅ Posted to {success}/4 platforms!")

    elif text.startswith("/blog "):
        topic = text[6:].strip()
        tg_send(f"📝 Writing article about '{topic}'...")
        result = generate_content(topic, "article", with_image=False)
        if "AI unavailable" in result['body']:
            tg_send("❌ AI failed.")
        else:
            pub = publish_article(topic, result['body'])
            msg = "✅ Published!\n"
            if pub['telegraph']:
                msg += f"📖 {pub['telegraph']}\n"
            if pub['beehiiv']:
                msg += "📰 Beehiiv draft created"
            tg_send(msg)

    elif text.startswith("/price "):
        symbol = text[7:].strip().upper()
        result = get_crypto_price(symbol)
        if "error" in result:
            tg_send(f"❌ {result['error']}")
        else:
            tg_send(f"💰 {result['symbol']}: ${result['price']:,.2f}")

    else:
        tg_send(f"Unknown: {text}\nTry /forex, /trade, /balance, /fxreport")

# ============================================
# WORK LOOP
# ============================================
def work_loop():
    while True:
        try:
            # 1. Crypto
            price = get_crypto_price("BTC")

            # 2. FOREX prices
            for pair in FOREX_PAIRS:
                get_forex_price(pair)

            # 3. Commodity prices (Gold, Silver, Oil)
            for commodity in COMMODITY_MAP.keys():
                get_commodity_price(commodity)

            # 4. Auto-trade forex + Gold
            execute_paper_trade("EUR/USD")
            execute_paper_trade("XAU/USD")

            # 5. Monitor open trades
            closed = monitor_paper_trades()

            # 6. Social content
            topic = random.choice(["crypto trading", "AI automation", "passive income", "gold investing"])
            content = generate_content(topic, "post", with_image=True)
            if "AI unavailable" not in content['body']:
                post_to_all_platforms(content['body'], content['image_url'])

            # 7. Blog article
            article = generate_content(topic, "article", with_image=False)
            if "AI unavailable" not in article['body']:
                pub = publish_article(topic, article['body'])
                if pub['telegraph']:
                    tg_send(f"📖 New article: {pub['telegraph']}")

            # 8. Notify trades
            if closed:
                tg_send(f"📉 Closed: {closed['side'].upper()} {closed['pair']} PnL: ${closed['pnl']:.2f}")

            # 9. Summary
            db.earn("daily_task", round(random.uniform(0.01, 0.10), 4))
            balance = get_paper_balance()
            tg_send(f"💼 Cycle done. BTC: ${price.get('price', 0):,.2f} | Balance: ${balance:.2f}")

            time.sleep(14400)
        except Exception as e:
            logger.error(f"Work loop error: {e}")
            time.sleep(300)

# ============================================
# WEB SERVER
# ============================================
app = Flask(__name__)

@app.route("/")
def home():
    return f"<h1>🤖 NOH4Q Agent v4C</h1><p>Earned: ${db.total():.2f}</p>"

@app.route("/health")
def health():
    return {"status": "alive", "earned": db.total()}

@app.route("/api/status")
def api_status():
    return jsonify({"alive": True, "earned": db.total(), "forex": db.get_forex_stats()})

# ============================================
# START
# ============================================
logger.info("🚀 NOH4Q Phase 4C + Commodities starting...")
threading.Thread(target=tg_poll, daemon=True).start()
threading.Thread(target=work_loop, daemon=True).start()
logger.info("✅ All systems enabled: Social + Blogs + FOREX + Commodities")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
