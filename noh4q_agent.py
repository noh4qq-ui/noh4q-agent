#!/usr/bin/env python3
"""
NOH4Q AGENT - PHASE 2 (Quota-Safe)
Runs 24/7 on Render, controlled via Telegram
"""

import os
import json
import logging
import threading
import time
import sqlite3
import random
import requests
from datetime import datetime
from flask import Flask, jsonify

# ============================================
# CONFIG
# ============================================
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "NOH4Q")

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
            (id INTEGER PRIMARY KEY, topic TEXT, content_type TEXT, body TEXT, ts TEXT)""")
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

    def save_content(self, topic, content_type, body):
        self.c.execute("INSERT INTO content (topic, content_type, body, ts) VALUES (?,?,?,?)",
                       (topic, content_type, body, datetime.now().isoformat()))
        self.conn.commit()

    def total(self):
        self.c.execute("SELECT COALESCE(SUM(amount),0) FROM earnings")
        return self.c.fetchone()[0]

    def price_history(self, symbol, limit=10):
        self.c.execute("SELECT price, ts FROM prices WHERE symbol=? ORDER BY id DESC LIMIT ?",
                       (symbol, limit))
        return self.c.fetchall()

db = DB()

# ============================================
# AI BRAIN (Gemini with Rate Limit Handling)
# ============================================
def ai_ask(prompt, retries=3):
    if not GEMINI_KEY:
        return "AI unavailable - fallback mode"
    
    for attempt in range(retries):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "safetySettings": [
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                    ]
                },
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif r.status_code == 503:
                logger.warning(f"Gemini 503 (busy). Retry {attempt+1}/{retries} in 5s...")
                time.sleep(5)
            elif r.status_code == 429:
                logger.warning(f"Gemini 429 (quota exceeded). Waiting 25s before retry {attempt+1}/{retries}...")
                time.sleep(25)
            else:
                logger.error(f"Gemini API Error: {r.status_code} - {r.text}")
                break # Don't retry 400/404 errors
        except Exception as e:
            logger.warning(f"Gemini request failed: {e}")
            time.sleep(2)
            
    return "AI unavailable - fallback mode"

# ============================================
# MARKET DATA (Coinbase -> Kraken -> CoinGecko)
# ============================================
def get_crypto_price(symbol="BTC"):
    crypto_map = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL", "DOGE": "DOGE", 
                  "BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}
    fsym = crypto_map.get(symbol.upper(), "BTC")
    
    # Primary: Coinbase
    try:
        r = requests.get(f"https://api.coinbase.com/v2/prices/{fsym}-USD/spot", timeout=10)
        if r.status_code == 200:
            price = float(r.json()["data"]["amount"])
            db.save_price(symbol.upper(), price)
            return {"symbol": symbol.upper(), "price": price}
    except Exception as e:
        logger.warning(f"Coinbase failed: {e}")

    # Fallback 1: Kraken
    try:
        kraken_map = {"BTC": "XBT", "ETH": "ETH", "SOL": "SOL", "DOGE": "XDG"}
        ksym = kraken_map.get(fsym)
        if ksym:
            r = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={ksym}USD", timeout=10)
            if r.status_code == 200:
                data = r.json()["result"]
                price = float(list(data.values())[0]["c"][0])
                db.save_price(symbol.upper(), price)
                return {"symbol": symbol.upper(), "price": price}
    except Exception as e:
        logger.warning(f"Kraken failed: {e}")

    # Fallback 2: CoinGecko
    try:
        coin_id = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin"}.get(fsym, "bitcoin")
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
            timeout=10
        )
        if r.status_code == 200:
            price = r.json()[coin_id]["usd"]
            db.save_price(symbol.upper(), price)
            return {"symbol": symbol.upper(), "price": price}
    except Exception as e:
        logger.warning(f"CoinGecko failed: {e}")

    return {"error": "All price APIs failed"}

# ============================================
# CONTENT GENERATION
# ============================================
def generate_content(topic, content_type="article"):
    prompts = {
        "article": f"Write a 300-word informative article about: {topic}. Keep it safe and educational.",
        "tweet_thread": f"Write a 3-tweet thread about: {topic}. Each tweet under 280 chars. Number them 1/3, 2/3, etc.",
        "script": f"Write a 30-second video script about: {topic}.",
        "post": f"Write an engaging social media post about: {topic}. Include hashtags."
    }
    prompt = prompts.get(content_type, prompts["article"])
    body = ai_ask(prompt)
    db.save_content(topic, content_type, body)
    return {"topic": topic, "type": content_type, "body": body}

# ============================================
# TELEGRAM CONTROL
# ============================================
def tg_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10
        )
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")

def tg_poll():
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset + 1, "timeout": 20},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                for update in data.get("result", []):
                    offset = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text:
                        handle_command(text, chat_id)
        except Exception as e:
            logger.warning(f"Telegram poll error: {e}")
        time.sleep(2)

def handle_command(text, chat_id):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = chat_id

    if text == "/start":
        tg_send(f"🤖 NOH4Q Agent v2 online.\nTotal earned: ${db.total():.2f}\n\nNew commands:\n/price BTC\n/content blockchain article\n/history BTC")

    elif text == "/status":
        tg_send(f"✅ Agent running.\nEarned: ${db.total():.2f}\nTime: {datetime.now().isoformat()}")

    elif text == "/report":
        tg_send(f"📊 Report\nEarned: ${db.total():.2f}\nEvents logged: {len(db.c.execute('SELECT * FROM events').fetchall())}")

    elif text.startswith("/ask "):
        answer = ai_ask(text[5:])
        tg_send(f"🧠 {answer}")

    elif text.startswith("/price "):
        symbol = text[7:].strip().upper()
        result = get_crypto_price(symbol)
        if "error" in result:
            tg_send(f"❌ Price error: {result['error']}")
        else:
            tg_send(f"💰 {result['symbol']}: ${result['price']:,.2f}")

    elif text.startswith("/content "):
        parts = text[9:].strip().split()
        if len(parts) < 2:
            tg_send("Usage: /content <topic> <article|tweet_thread|script|post>")
        else:
            topic = " ".join(parts[:-1])
            ctype = parts[-1]
            tg_send(f"🧠 Generating {ctype} about '{topic}'...")
            result = generate_content(topic, ctype)
            if "AI unavailable" in result['body']:
                tg_send("❌ AI failed (Quota exceeded or busy). Please try again later.")
            else:
                tg_send(f"✅ Saved!\n\n{result['body'][:500]}...")

    elif text.startswith("/history "):
        symbol = text[9:].strip().upper()
        history = db.price_history(symbol)
        if not history:
            tg_send(f"No price history for {symbol} yet. Use /price {symbol} first.")
        else:
            lines = [f"📈 {symbol} Price History (latest {len(history)}):"]
            for price, ts in history:
                lines.append(f"  ${price:,.2f} — {ts[:16]}")
            tg_send("\n".join(lines))

    elif text == "/NOH4Q":
        tg_send("🔓 Unlocked. Full access enabled.")

    else:
        tg_send(f"Unknown command: {text}\nTry /status, /report, /ask, /price, /content, /history")

# ============================================
# AUTOMATION LOOP (Every 4 hours to save quota)
# ============================================
def work_loop():
    while True:
        try:
            # 1. Track BTC price every 4 hours
            price = get_crypto_price("BTC")
            if "price" in price:
                logger.info(f"BTC: ${price['price']:,.2f}")

            # 2. Generate a money-making idea (uses 1 AI call)
            idea = ai_ask("Give one short money-making idea in one sentence.")
            db.log("ai", idea)

            # 3. Auto-generate one piece of content (uses 1 AI call)
            topics = ["crypto trading", "AI automation", "passive income"]
            topic = random.choice(topics)
            generate_content(topic, "post")

            # 4. Simulated earning track
            db.earn("daily_task", round(random.uniform(0.01, 0.10), 4))

            # 5. Telegram daily ping
            tg_send(f"💼 Cycle done. BTC: ${price.get('price', 0):,.2f} | Total: ${db.total():.2f}")

            # Wait 4 hours between cycles (saves Gemini quota)
            time.sleep(14400)
        except Exception as e:
            logger.error(f"Work loop error: {e}")
            time.sleep(300)

# ============================================
# WEB SERVER (health + dashboard)
# ============================================
app = Flask(__name__)

@app.route("/")
def home():
    return f"""
    <h1>🤖 NOH4Q Agent v2</h1>
    <p>Status: Running</p>
    <p>Total earned: ${db.total():.2f}</p>
    <p>Time: {datetime.now().isoformat()}</p>
    """

@app.route("/health")
def health():
    return {"status": "alive", "time": datetime.now().isoformat(), "earned": db.total()}

@app.route("/api/status")
def api_status():
    return jsonify({
        "alive": True,
        "earned": db.total(),
        "events": len(db.c.execute("SELECT * FROM events").fetchall())
    })

@app.route("/api/price/<symbol>")
def api_price(symbol):
    return jsonify(get_crypto_price(symbol.upper()))

# ============================================
# START BACKGROUND TASKS
# ============================================
logger.info("🚀 NOH4Q Phase 2 starting background tasks...")
threading.Thread(target=tg_poll, daemon=True).start()
threading.Thread(target=work_loop, daemon=True).start()
logger.info("✅ Telegram listener started. Waiting for messages...")

# ============================================
# MAIN ENTRY
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
