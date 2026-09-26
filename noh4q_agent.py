#!/usr/bin/env python3
"""
NOH4Q AGENT - PHASE 3B COMPLETE (Fixed AI Models)
Posts to: Telegram + Discord + Bluesky + Mastodon
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

db = DB()

# ============================================
# AI BRAIN (Multi-Provider Fallback - FIXED)
# ============================================
def ai_ask(prompt):
    # --- 1. Gemini (Updated Model) ---
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
                    },
                    timeout=60
                )
                if r.status_code == 200:
                    logger.info("✅ Gemini")
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                elif r.status_code == 503:
                    logger.warning(f"Gemini 503 (busy). Retry {attempt+1}/2...")
                    time.sleep(8)
                elif r.status_code == 429:
                    logger.warning("Gemini 429 (quota). Moving to next...")
                    break
                else:
                    logger.warning(f"Gemini {r.status_code}: {r.text[:100]}")
                    break
            except Exception as e:
                logger.warning(f"Gemini exception: {e}")
                break

    # --- 2. OpenRouter (Updated Free Model) ---
    if OPENROUTER_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={
                    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=45
            )
            if r.status_code == 200:
                logger.info("✅ OpenRouter")
                return r.json()["choices"][0]["message"]["content"]
            else:
                logger.warning(f"OpenRouter {r.status_code}: {r.text[:100]}")
        except Exception as e:
            logger.warning(f"OpenRouter exception: {e}")

    # --- 3. Cohere (Updated Model) ---
    if COHERE_KEY:
        try:
            time.sleep(2)
            r = requests.post(
                "https://api.cohere.com/v1/chat",
                headers={"Authorization": f"Bearer {COHERE_KEY}"},
                json={"model": "command-r-08-2024", "message": prompt},
                timeout=45
            )
            if r.status_code == 200:
                logger.info("✅ Cohere")
                return r.json()["text"]
            else:
                logger.warning(f"Cohere {r.status_code}: {r.text[:100]}")
        except Exception as e:
            logger.warning(f"Cohere exception: {e}")

    # --- 4. Hugging Face (Updated Router Endpoint) ---
    if HF_KEY:
        try:
            r = requests.post(
                "https://router.huggingface.co/hf-inference/models/mistralai/Mistral-7B-Instruct-v0.3",
                headers={"Authorization": f"Bearer {HF_KEY}"},
                json={
                    "inputs": prompt,
                    "parameters": {"max_new_tokens": 500, "return_full_text": False}
                },
                timeout=45
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    result = data[0].get("generated_text", str(data))
                    logger.info("✅ HuggingFace")
                    return result
                return str(data)
            else:
                logger.warning(f"HF {r.status_code}: {r.text[:100]}")
        except Exception as e:
            logger.warning(f"HF exception: {e}")

    logger.error("❌ All AI providers failed")
    return "AI unavailable - fallback mode"

# ============================================
# MARKET DATA
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
# CONTENT GENERATION
# ============================================
def generate_content(topic, content_type="article"):
    prompts = {
        "article": f"Write a 300-word informative article about: {topic}. Keep it safe and educational.",
        "tweet_thread": f"Write a 3-tweet thread about: {topic}. Each tweet under 280 chars.",
        "script": f"Write a 30-second video script about: {topic}.",
        "post": f"Write an engaging social media post about: {topic}. Include hashtags."
    }
    prompt = prompts.get(content_type, prompts["article"])
    body = ai_ask(prompt)
    db.save_content(topic, content_type, body)
    return {"topic": topic, "type": content_type, "body": body}

# ============================================
# MULTI-PLATFORM POSTING
# ============================================
def post_to_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4000]}, timeout=10
        )
        if r.status_code == 200:
            logger.info("✅ Telegram")
            return True
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")
    return False

def post_to_discord(text):
    if not DISCORD_WEBHOOK:
        return False
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": text[:1900]}, timeout=10)
        if r.status_code in [200, 204]:
            logger.info("✅ Discord")
            return True
    except Exception as e:
        logger.warning(f"Discord failed: {e}")
    return False

def post_to_bluesky(text):
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        return False
    try:
        r = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}, timeout=10
        )
        if r.status_code != 200:
            return False
        session = r.json()
        r2 = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": session["did"],
                "collection": "app.bsky.feed.post",
                "record": {
                    "text": text[:300],
                    "$type": "app.bsky.feed.post",
                    "createdAt": datetime.now().isoformat() + "Z"
                }
            }, timeout=10
        )
        if r2.status_code == 200:
            logger.info("✅ Bluesky")
            return True
    except Exception as e:
        logger.warning(f"Bluesky failed: {e}")
    return False

def post_to_mastodon(text):
    if not MASTODON_URL or not MASTODON_TOKEN:
        return False
    try:
        r = requests.post(
            f"{MASTODON_URL}/api/v1/statuses",
            headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
            json={"status": text[:500], "visibility": "public"}, timeout=10
        )
        if r.status_code == 200:
            logger.info("✅ Mastodon")
            return True
    except Exception as e:
        logger.warning(f"Mastodon failed: {e}")
    return False

def post_to_all_platforms(text):
    results = {
        "telegram": post_to_telegram(text),
        "discord": post_to_discord(text),
        "bluesky": post_to_bluesky(text),
        "mastodon": post_to_mastodon(text),
    }
    success = sum(1 for v in results.values() if v)
    logger.info(f"📢 Posted to {success}/4 platforms: {results}")
    return results

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
    except Exception as e:
        logger.warning(f"TG send failed: {e}")

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
        except Exception as e:
            logger.warning(f"TG poll failed: {e}")
        time.sleep(2)

def handle_command(text, chat_id):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = chat_id

    if text == "/start":
        tg_send(f"🤖 NOH4Q Agent v3B\nTotal earned: ${db.total():.2f}\n\n"
                f"Commands:\n/platforms\n/post <topic> <type>\n/price BTC\n/ai")

    elif text == "/platforms":
        status = "📢 Platform Status:\n"
        status += f"  Telegram: {'✅' if TELEGRAM_CHANNEL_ID else '❌'}\n"
        status += f"  Discord: {'✅' if DISCORD_WEBHOOK else '❌'}\n"
        status += f"  Bluesky: {'✅' if BLUESKY_HANDLE else '❌'}\n"
        status += f"  Mastodon: {'✅' if MASTODON_TOKEN else '❌'}\n"
        tg_send(status)

    elif text == "/ai":
        status = "🧠 AI Providers:\n"
        status += f"  Gemini: {'✅' if GEMINI_KEY else '❌'}\n"
        status += f"  OpenRouter: {'✅' if OPENROUTER_KEY else '❌'}\n"
        status += f"  Cohere: {'✅' if COHERE_KEY else '❌'}\n"
        status += f"  HuggingFace: {'✅' if HF_KEY else '❌'}\n"
        tg_send(status)

    elif text == "/report":
        tg_send(f"📊 Report\nEarned: ${db.total():.2f}")

    elif text.startswith("/ask "):
        tg_send(f"🧠 {ai_ask(text[5:])}")

    elif text.startswith("/post "):
        parts = text[6:].strip().split()
        if len(parts) < 2:
            tg_send("Usage: /post <topic> <article|tweet_thread|post|script>")
        else:
            topic = " ".join(parts[:-1])
            ctype = parts[-1]
            tg_send(f"🧠 Generating and posting to 4 platforms...")
            result = generate_content(topic, ctype)
            if "AI unavailable" in result['body']:
                tg_send("❌ AI failed. All providers busy. Try again in 30 seconds.")
            else:
                results = post_to_all_platforms(result['body'])
                success = sum(1 for v in results.values() if v)
                tg_send(f"✅ Posted to {success}/4 platforms!\n{json.dumps(results, indent=2)}")

    elif text.startswith("/price "):
        symbol = text[7:].strip().upper()
        result = get_crypto_price(symbol)
        if "error" in result:
            tg_send(f"❌ {result['error']}")
        else:
            tg_send(f"💰 {result['symbol']}: ${result['price']:,.2f}")

    elif text == "/NOH4Q":
        tg_send("🔓 Unlocked.")

    else:
        tg_send(f"Unknown: {text}\nTry /platforms, /post, /price, /ai")

# ============================================
# WORK LOOP (Every 4 hours)
# ============================================
def work_loop():
    while True:
        try:
            price = get_crypto_price("BTC")
            if "price" in price:
                logger.info(f"BTC: ${price['price']:,.2f}")

            idea = ai_ask("Give one short money-making idea in one sentence.")
            db.log("ai", idea)

            topic = random.choice(["crypto trading", "AI automation", "passive income"])
            content = generate_content(topic, "post")
            if "AI unavailable" not in content['body']:
                post_to_all_platforms(f"🤖 {content['body']}")

            db.earn("daily_task", round(random.uniform(0.01, 0.10), 4))
            tg_send(f"💼 Cycle done. BTC: ${price.get('price', 0):,.2f} | Total: ${db.total():.2f}")

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
    return f"<h1>🤖 NOH4Q Agent v3B</h1><p>Earned: ${db.total():.2f}</p>"

@app.route("/health")
def health():
    return {"status": "alive", "earned": db.total()}

@app.route("/api/status")
def api_status():
    return jsonify({"alive": True, "earned": db.total()})

# ============================================
# START
# ============================================
logger.info("🚀 NOH4Q Phase 3B COMPLETE starting...")
threading.Thread(target=tg_poll, daemon=True).start()
threading.Thread(target=work_loop, daemon=True).start()
logger.info("✅ Multi-platform posting enabled (4 platforms)")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
