#!/usr/bin/env python3
"""
NOH4Q AGENT - PHASE 4B (Telegraph + Beehiiv Blog Integration)
Posts to: Telegram + Discord + Bluesky + Mastodon
With AI-generated images and Blog publishing (Telegraph + Beehiiv)
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

    def save_content(self, topic, content_type, body, image_url=""):
        self.c.execute("INSERT INTO content (topic, content_type, body, image_url, ts) VALUES (?,?,?,?,?)",
                       (topic, content_type, body, image_url, datetime.now().isoformat()))
        self.conn.commit()

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
# IMAGE GENERATION (Pollinations AI)
# ============================================
def generate_image_url(prompt, width=1024, height=1024):
    clean_prompt = prompt[:200].strip()
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&model=flux"
    logger.info(f"🎨 Image URL: {url[:80]}...")
    return url

def create_image_prompt(topic, body):
    image_prompt = ai_ask(
        f"Create a short, vivid image description (max 15 words) for a social media post about: {topic}. "
        f"Style: modern, digital art, high quality. Return only the description, no quotes."
    )
    if "AI unavailable" in image_prompt:
        image_prompt = f"Digital art of {topic}, modern style, vibrant colors"
    logger.info(f"🎨 Image prompt: {image_prompt[:80]}")
    return image_prompt.strip()[:200]

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
        image_prompt = create_image_prompt(topic, body)
        image_url = generate_image_url(image_prompt)

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
                logger.info("✅ Telegram (with image)")
                return True
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4000]}, timeout=10
        )
        if r.status_code == 200:
            logger.info("✅ Telegram (text)")
            return True
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")
    return False

def post_to_discord(text, image_url=""):
    if not DISCORD_WEBHOOK:
        return False
    try:
        payload = {"content": text[:1900]}
        if image_url:
            payload["embeds"] = [{"image": {"url": image_url}}]
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=30)
        if r.status_code in [200, 204]:
            logger.info("✅ Discord")
            return True
    except Exception as e:
        logger.warning(f"Discord failed: {e}")
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
                    upload_resp = requests.post(
                        "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
                        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "image/png"},
                        data=img_resp.content, timeout=60
                    )
                    if upload_resp.status_code == 200:
                        blob = upload_resp.json()["blob"]
                        record["embed"] = {"$type": "app.bsky.embed.images",
                                          "images": [{"alt": text[:100], "image": blob}]}
            except Exception as e:
                logger.warning(f"Bluesky image error: {e}")
        r2 = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record}, timeout=30
        )
        if r2.status_code == 200:
            logger.info("✅ Bluesky")
            return True
    except Exception as e:
        logger.warning(f"Bluesky failed: {e}")
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
                    upload_resp = requests.post(
                        f"{MASTODON_URL}/api/v2/media",
                        headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
                        files={"file": ("image.png", img_resp.content, "image/png")},
                        data={"description": text[:100]}, timeout=60
                    )
                    if upload_resp.status_code in [200, 202]:
                        media_ids.append(upload_resp.json()["id"])
            except Exception as e:
                logger.warning(f"Mastodon image error: {e}")
        payload = {"status": text[:500], "visibility": "public"}
        if media_ids:
            payload["media_ids"] = media_ids
        r = requests.post(
            f"{MASTODON_URL}/api/v1/statuses",
            headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
            json=payload, timeout=30
        )
        if r.status_code == 200:
            logger.info("✅ Mastodon")
            return True
    except Exception as e:
        logger.warning(f"Mastodon failed: {e}")
    return False

def post_to_all_platforms(text, image_url=""):
    results = {
        "telegram": post_to_telegram(text, image_url),
        "discord": post_to_discord(text, image_url),
        "bluesky": post_to_bluesky(text, image_url),
        "mastodon": post_to_mastodon(text, image_url),
    }
    success = sum(1 for v in results.values() if v)
    logger.info(f"📢 Posted to {success}/4 platforms")
    return results

# ============================================
# TELEGRAPH BLOG (No signup, no verification)
# ============================================
def get_telegraph_token():
    """Get or create a Telegraph access token (cached in DB)."""
    token = db.get_setting("telegraph_token", "")
    if token:
        return token
    try:
        r = requests.post(
            "https://api.telegra.ph/createAccount",
            data={
                "short_name": "NOH4Q",
                "author_name": "NOH4Q Agent"
            },
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                token = data["result"]["access_token"]
                db.set_setting("telegraph_token", token)
                logger.info("✅ Telegraph account created")
                return token
    except Exception as e:
        logger.warning(f"Telegraph token failed: {e}")
    return ""

def markdown_to_telegraph_nodes(text):
    """Convert simple text into Telegraph Node format."""
    nodes = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Headings
        if line.startswith("### "):
            nodes.append({"tag": "h4", "children": [line[4:]]})
        elif line.startswith("## "):
            nodes.append({"tag": "h3", "children": [line[3:]]})
        elif line.startswith("# "):
            nodes.append({"tag": "h3", "children": [line[2:]]})
        # Bullet lists
        elif line.startswith("- ") or line.startswith("* "):
            nodes.append({"tag": "ul", "children": [
                {"tag": "li", "children": [line[2:]]}
            ]})
        # Regular paragraph
        else:
            nodes.append({"tag": "p", "children": [line]})
    return nodes

def publish_to_telegraph(title, article_body):
    """Publish an article to Telegraph and return the URL."""
    token = get_telegraph_token()
    if not token:
        return None
    try:
        nodes = markdown_to_telegraph_nodes(article_body)
        r = requests.post(
            "https://api.telegra.ph/createPage",
            data={
                "access_token": token,
                "title": title[:256],
                "author_name": "NOH4Q Agent",
                "content": json.dumps(nodes),
                "return_content": "false"
            },
            timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                url = data["result"]["url"]
                logger.info(f"✅ Telegraph: {url}")
                return url
        logger.warning(f"Telegraph publish failed: {r.text[:150]}")
    except Exception as e:
        logger.warning(f"Telegraph error: {e}")
    return None

# ============================================
# BEEHIIV BLOG (Requires Stripe ID verification)
# ============================================
def publish_to_beehiiv(title, article_body):
    if not BEEHIIV_API_KEY or not BEEHIIV_PUBLICATION_ID:
        logger.info("⏭️ Beehiiv skipped (no API key)")
        return False
    url = f"https://api.beehiiv.com/v2/publications/{BEEHIIV_PUBLICATION_ID}/posts"
    headers = {
        "Authorization": f"Bearer {BEEHIIV_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "title": title,
        "body_content": article_body.replace("\n", "<br>"),
        "status": "draft"
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 201:
            logger.info("✅ Beehiiv (draft)")
            return True
        else:
            logger.warning(f"Beehiiv failed: {r.text[:150]}")
    except Exception as e:
        logger.warning(f"Beehiiv error: {e}")
    return False

# ============================================
# PUBLISH TO BOTH BLOGS
# ============================================
def publish_article(topic, body):
    """Publish to both Telegraph and Beehiiv. Returns URLs."""
    title = f"AI Insights: {topic.title()}"
    results = {"title": title, "telegraph": None, "beehiiv": False}

    # Telegraph (always try)
    url = publish_to_telegraph(title, body)
    if url:
        results["telegraph"] = url

    # Beehiiv (if keys available)
    if BEEHIIV_API_KEY and BEEHIIV_PUBLICATION_ID:
        results["beehiiv"] = publish_to_beehiiv(title, body)

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
        tg_send(f"🤖 NOH4Q Agent v4B (Telegraph + Beehiiv)\nEarned: ${db.total():.2f}\n\n"
                f"Commands:\n"
                f"/post <topic> <type>\n"
                f"/blog <topic> - publish to Telegraph + Beehiiv\n"
                f"/platforms\n"
                f"/price BTC\n"
                f"/ai")

    elif text == "/platforms":
        status = "📢 Platforms:\n"
        status += f"  Telegram: {'✅' if TELEGRAM_CHANNEL_ID else '❌'}\n"
        status += f"  Discord: {'✅' if DISCORD_WEBHOOK else '❌'}\n"
        status += f"  Bluesky: {'✅' if BLUESKY_HANDLE else '❌'}\n"
        status += f"  Mastodon: {'✅' if MASTODON_TOKEN else '❌'}\n"
        status += f"  Telegraph: ✅ (always on)\n"
        status += f"  Beehiiv: {'✅' if BEEHIIV_API_KEY else '❌ (no key)'}\n"
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
            tg_send(f"🎨 Generating '{topic}'...")
            result = generate_content(topic, ctype, with_image=True)
            if "AI unavailable" in result['body']:
                tg_send("❌ AI failed.")
            else:
                results = post_to_all_platforms(result['body'], result['image_url'])
                success = sum(1 for v in results.values() if v)
                tg_send(f"✅ Posted to {success}/4 platforms!")

    elif text.startswith("/blog "):
        topic = text[6:].strip()
        if not topic:
            tg_send("Usage: /blog <topic>")
        else:
            tg_send(f"📝 Writing article about '{topic}'...")
            result = generate_content(topic, "article", with_image=False)
            if "AI unavailable" in result['body']:
                tg_send("❌ AI failed.")
            else:
                pub = publish_article(topic, result['body'])
                msg = f"✅ Published!\n\n"
                if pub['telegraph']:
                    msg += f"📖 Telegraph: {pub['telegraph']}\n"
                if pub['beehiiv']:
                    msg += f"📰 Beehiiv: draft created\n"
                elif not BEEHIIV_API_KEY:
                    msg += f"📰 Beehiiv: skipped (no key)\n"
                tg_send(msg)

    elif text.startswith("/price "):
        symbol = text[7:].strip().upper()
        result = get_crypto_price(symbol)
        if "error" in result:
            tg_send(f"❌ {result['error']}")
        else:
            tg_send(f"💰 {result['symbol']}: ${result['price']:,.2f}")

    else:
        tg_send(f"Unknown: {text}\nTry /post, /blog, /platforms, /ai, /price")

# ============================================
# WORK LOOP
# ============================================
def work_loop():
    while True:
        try:
            price = get_crypto_price("BTC")
            if "price" in price:
                logger.info(f"BTC: ${price['price']:,.2f}")

            # Generate social post with image
            topic = random.choice(["crypto trading", "AI automation", "passive income", "blockchain"])
            content = generate_content(topic, "post", with_image=True)
            if "AI unavailable" not in content['body']:
                post_to_all_platforms(content['body'], content['image_url'])

            # Generate article and publish to blogs
            article = generate_content(topic, "article", with_image=False)
            if "AI unavailable" not in article['body']:
                pub = publish_article(topic, article['body'])
                if pub['telegraph']:
                    tg_send(f"📖 New Telegraph article: {pub['telegraph']}")

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
    return f"<h1>🤖 NOH4Q Agent v4B</h1><p>Earned: ${db.total():.2f}</p>"

@app.route("/health")
def health():
    return {"status": "alive", "earned": db.total()}

@app.route("/api/status")
def api_status():
    return jsonify({"alive": True, "earned": db.total()})

# ============================================
# START
# ============================================
logger.info("🚀 NOH4Q Phase 4B (Telegraph + Beehiiv) starting...")
threading.Thread(target=tg_poll, daemon=True).start()
threading.Thread(target=work_loop, daemon=True).start()
logger.info("✅ Telegraph + Beehiiv + 4 social platforms enabled")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
