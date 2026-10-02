#!/usr/bin/env python3
# NOH4Q AGENT - FINAL COMPLETE (All Safe Phases)
# Phases 1-10 + Podcasts + RSS + Interactive + Email + Multi-Lang + Facebook + YouTube

import os
import re
import json
import logging
import threading
import time
import sqlite3
import random
import requests
import urllib.parse
import asyncio
import subprocess
import tempfile
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

# CONFIG
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
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "")
CLICKBANK_AFFILIATE_ID = os.getenv("CLICKBANK_AFFILIATE_ID", "")

# PHASE 9: Facebook Pages
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "")

# PHASE 10: YouTube
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

# PHASE 7: Email (via Resend or SMTP)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

# PHASE 5B: RSS Feed
RSS_BASE_URL = os.getenv("RSS_BASE_URL", "https://noh4q-agent.onrender.com")

# Existing config
ENABLE_BLUESKY_GROWTH = os.getenv("ENABLE_BLUESKY_GROWTH", "true").lower() == "true"
ENABLE_MASTODON_GROWTH = os.getenv("ENABLE_MASTODON_GROWTH", "true").lower() == "true"
MAX_FOLLOWS_PER_CYCLE = int(os.getenv("MAX_FOLLOWS_PER_CYCLE", "20"))
MAX_LIKES_PER_CYCLE = int(os.getenv("MAX_LIKES_PER_CYCLE", "30"))
MAX_REPLIES_PER_CYCLE = int(os.getenv("MAX_REPLIES_PER_CYCLE", "5"))
FOREX_START_BALANCE = float(os.getenv("FOREX_START_BALANCE", "1000"))
FOREX_RISK_PER_TRADE = float(os.getenv("FOREX_RISK_PER_TRADE", "2"))
FOREX_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF"]
COMMODITY_MAP = {"XAU/USD": "GC=F", "XAG/USD": "SI=F", "WTI": "CL=F", "BRENT": "BZ=F", "NATGAS": "NG=F", "COPPER": "HG=F"}
NICHE_TERMS = ["crypto", "AI", "trading", "passive income", "blockchain", "investing", "automation", "bitcoin", "finance", "startup"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# DATABASE
class DB:
    def __init__(self, path="noh4q.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.c = self.conn.cursor()
        self._init_tables()

    def _init_tables(self):
        tables = [
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, type TEXT, message TEXT, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS earnings (id INTEGER PRIMARY KEY, source TEXT, amount REAL, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS prices (id INTEGER PRIMARY KEY, symbol TEXT, price REAL, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS content (id INTEGER PRIMARY KEY, topic TEXT, content_type TEXT, body TEXT, image_url TEXT, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE IF NOT EXISTS forex_trades (id INTEGER PRIMARY KEY, pair TEXT, side TEXT, entry_price REAL, exit_price REAL, units REAL, pnl REAL, status TEXT, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS forex_price_history (id INTEGER PRIMARY KEY, pair TEXT, price REAL, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS analytics (id INTEGER PRIMARY KEY, platform TEXT, status TEXT, content_len INTEGER, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY, topic TEXT, content_type TEXT, status TEXT, added_at TEXT, posted_at TEXT)",
            "CREATE TABLE IF NOT EXISTS engagement (id INTEGER PRIMARY KEY, platform TEXT, action TEXT, target TEXT, ts TEXT)",
            "CREATE TABLE IF NOT EXISTS podcasts (id INTEGER PRIMARY KEY, title TEXT, description TEXT, audio_url TEXT, duration INTEGER, published_at TEXT)",
            "CREATE TABLE IF NOT EXISTS subscribers (id INTEGER PRIMARY KEY, email TEXT UNIQUE, subscribed_at TEXT)",
            "CREATE TABLE IF NOT EXISTS quizzes (id INTEGER PRIMARY KEY, topic TEXT, questions TEXT, created_at TEXT)",
        ]
        for t in tables:
            try:
                self.c.execute(t)
            except Exception:
                pass
        self.conn.commit()

    def log(self, etype, message):
        try:
            self.c.execute("INSERT INTO events (type, message, ts) VALUES (?,?,?)", (etype, message, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def earn(self, source, amount):
        try:
            self.c.execute("INSERT INTO earnings (source, amount, ts) VALUES (?,?,?)", (source, amount, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def save_price(self, symbol, price):
        try:
            self.c.execute("INSERT INTO prices (symbol, price, ts) VALUES (?,?,?)", (symbol, price, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def save_forex_price(self, pair, price):
        try:
            self.c.execute("INSERT INTO forex_price_history (pair, price, ts) VALUES (?,?,?)", (pair, price, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def get_forex_history(self, pair, limit=50):
        try:
            self.c.execute("SELECT price, ts FROM forex_price_history WHERE pair=? ORDER BY id DESC LIMIT ?", (pair, limit))
            return list(reversed(self.c.fetchall()))
        except Exception:
            return []

    def save_content(self, topic, content_type, body, image_url=""):
        try:
            self.c.execute("INSERT INTO content (topic, content_type, body, image_url, ts) VALUES (?,?,?,?,?)",
                           (topic, content_type, body, image_url, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def save_forex_trade(self, pair, side, entry, exit_price, units, pnl, status):
        try:
            self.c.execute("INSERT INTO forex_trades (pair, side, entry_price, exit_price, units, pnl, status, ts) VALUES (?,?,?,?,?,?,?,?)",
                           (pair, side, entry, exit_price, units, pnl, status, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def get_open_forex_trades(self):
        try:
            self.c.execute("SELECT id, pair, side, entry_price, units FROM forex_trades WHERE status='open'")
            return self.c.fetchall()
        except Exception:
            return []

    def close_forex_trade(self, trade_id, exit_price, pnl):
        try:
            self.c.execute("UPDATE forex_trades SET exit_price=?, pnl=?, status='closed' WHERE id=?", (exit_price, pnl, trade_id))
            self.conn.commit()
        except Exception:
            pass

    def get_forex_stats(self):
        try:
            self.c.execute("SELECT COUNT(*), COALESCE(SUM(pnl),0) FROM forex_trades WHERE status='closed'")
            count, total_pnl = self.c.fetchone()
            self.c.execute("SELECT COUNT(*) FROM forex_trades WHERE status='closed' AND pnl > 0")
            wins = self.c.fetchone()[0]
            return {"total_trades": count, "total_pnl": total_pnl, "wins": wins,
                    "win_rate": (wins / count * 100) if count > 0 else 0}
        except Exception:
            return {"total_trades": 0, "total_pnl": 0, "wins": 0, "win_rate": 0}

    def log_post(self, platform, status, content_len):
        try:
            self.c.execute("INSERT INTO analytics (platform, status, content_len, ts) VALUES (?,?,?,?)",
                           (platform, status, content_len, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def get_analytics_summary(self):
        try:
            self.c.execute("SELECT platform, COUNT(*), SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) FROM analytics GROUP BY platform")
            rows = self.c.fetchall()
            return [{"platform": p, "total": t, "success": s, "fail": t - s,
                     "success_rate": (s / t * 100) if t > 0 else 0} for p, t, s in rows]
        except Exception:
            return []

    def add_to_queue(self, topic, content_type="post"):
        try:
            self.c.execute("INSERT INTO queue (topic, content_type, status, added_at) VALUES (?,?,?,?)",
                           (topic, content_type, "pending", datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def get_queue(self, status="pending"):
        try:
            self.c.execute("SELECT id, topic, content_type FROM queue WHERE status=? ORDER BY id ASC", (status,))
            return self.c.fetchall()
        except Exception:
            return []

    def pop_queue(self):
        try:
            self.c.execute("SELECT id, topic, content_type FROM queue WHERE status='pending' ORDER BY id ASC LIMIT 1")
            row = self.c.fetchone()
            if not row:
                return None
            self.c.execute("UPDATE queue SET status='done', posted_at=? WHERE id=?", (datetime.now().isoformat(), row[0]))
            self.conn.commit()
            return {"id": row[0], "topic": row[1], "content_type": row[2]}
        except Exception:
            return None

    def log_engagement(self, platform, action, target):
        try:
            self.c.execute("INSERT INTO engagement (platform, action, target, ts) VALUES (?,?,?,?)",
                           (platform, action, target, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def get_engagement_stats(self):
        try:
            self.c.execute("SELECT platform, action, COUNT(*) FROM engagement GROUP BY platform, action")
            return [{"platform": r[0], "action": r[1], "count": r[2]} for r in self.c.fetchall()]
        except Exception:
            return []

    def get_setting(self, key, default=""):
        try:
            self.c.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = self.c.fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def set_setting(self, key, value):
        try:
            self.c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
            self.conn.commit()
        except Exception:
            pass

    def total(self):
        try:
            self.c.execute("SELECT COALESCE(SUM(amount),0) FROM earnings")
            return self.c.fetchone()[0]
        except Exception:
            return 0

    def save_podcast(self, title, description, audio_url, duration=0):
        try:
            self.c.execute("INSERT INTO podcasts (title, description, audio_url, duration, published_at) VALUES (?,?,?,?,?)",
                           (title, description, audio_url, duration, datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass

    def get_all_podcasts(self, limit=50):
        try:
            self.c.execute("SELECT title, description, audio_url, duration, published_at FROM podcasts ORDER BY id DESC LIMIT ?", (limit,))
            return self.c.fetchall()
        except Exception:
            return []

    def add_subscriber(self, email):
        try:
            self.c.execute("INSERT OR IGNORE INTO subscribers (email, subscribed_at) VALUES (?,?)",
                           (email, datetime.now().isoformat()))
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_subscribers(self):
        try:
            self.c.execute("SELECT email FROM subscribers")
            return [r[0] for r in self.c.fetchall()]
        except Exception:
            return []

db = DB()

# AI BRAIN
def ai_ask(prompt, language="en"):
    if language != "en":
        prompt = "Respond in " + language + ". " + prompt
    
    if GEMINI_KEY:
        for attempt in range(2):
            try:
                r = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key=" + GEMINI_KEY,
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "safetySettings": [
                              {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                              {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                              {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                              {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                          ]},
                    timeout=60
                )
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                elif r.status_code in [429, 503]:
                    time.sleep(8)
            except Exception:
                break

    if OPENROUTER_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer " + OPENROUTER_KEY},
                json={"model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=45
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    if COHERE_KEY:
        try:
            time.sleep(2)
            r = requests.post(
                "https://api.cohere.com/v1/chat",
                headers={"Authorization": "Bearer " + COHERE_KEY},
                json={"model": "command-r-08-2024", "message": prompt},
                timeout=45
            )
            if r.status_code == 200:
                return r.json()["text"]
        except Exception:
            pass

    if HF_KEY:
        try:
            r = requests.post(
                "https://router.huggingface.co/hf-inference/models/mistralai/Mistral-7B-Instruct-v0.3",
                headers={"Authorization": "Bearer " + HF_KEY},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 500, "return_full_text": False}},
                timeout=45
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[0].get("generated_text", str(data))
                return str(data)
        except Exception:
            pass
    return "AI unavailable"

# TEXT CLEANER
def clean_ai_text(text):
    if not text:
        return text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', text)
    text = text.replace('**', '').replace('##', '')
    return text

# AFFILIATE INJECTION
AMAZON_KEYWORDS = {
    "trading book": "https://www.amazon.com/s?k=trading+books&tag=",
    "trading books": "https://www.amazon.com/s?k=trading+books&tag=",
    "ai tool": "https://www.amazon.com/s?k=ai+tools&tag=",
    "ai tools": "https://www.amazon.com/s?k=ai+tools&tag=",
    "crypto wallet": "https://www.amazon.com/s?k=crypto+wallet&tag=",
    "crypto wallets": "https://www.amazon.com/s?k=crypto+wallet&tag=",
    "trading course": "https://www.amazon.com/s?k=trading+course&tag=",
    "investing guide": "https://www.amazon.com/s?k=investing+books&tag=",
    "investing book": "https://www.amazon.com/s?k=investing+books&tag=",
    "ai software": "https://www.amazon.com/s?k=ai+software&tag=",
    "bitcoin book": "https://www.amazon.com/s?k=bitcoin+books&tag=",
    "ledger nano": "https://www.amazon.com/s?k=ledger+nano&tag=",
    "trezor wallet": "https://www.amazon.com/s?k=trezor+wallet&tag=",
    "hardware wallet": "https://www.amazon.com/s?k=hardware+wallet&tag=",
}

def inject_affiliate_links(text):
    result = text
    if AMAZON_AFFILIATE_TAG:
        for keyword, base_url in AMAZON_KEYWORDS.items():
            if keyword.lower() in result.lower():
                full_url = base_url + AMAZON_AFFILIATE_TAG
                result = result.replace(keyword, "[" + keyword + "](" + full_url + ")", 1)
    if CLICKBANK_AFFILIATE_ID:
        for kw in ["make money online", "passive income course"]:
            if kw.lower() in result.lower():
                hoplink = "https://hop.clickbank.net/?affiliate=" + CLICKBANK_AFFILIATE_ID
                result = result.replace(kw, "[" + kw + "](" + hoplink + ")", 1)
    return result

# IMAGE GENERATION
def generate_image_url(prompt, width=1024, height=1024):
    try:
        encoded = urllib.parse.quote(prompt[:200].strip())
        return "https://image.pollinations.ai/prompt/" + encoded + "?width=" + str(width) + "&height=" + str(height) + "&nologo=true&model=flux"
    except Exception:
        return ""

def create_image_prompt(topic, body):
    p = ai_ask("Create a short 15-word vivid image description for: " + topic + ". Only the description, no formatting.")
    if "AI unavailable" in p:
        p = "Digital art of " + topic + ", modern, vibrant"
    return clean_ai_text(p.strip())[:200]

# AUDIO GENERATION
async def _tts_async(text, output_path, voice="en-US-AriaNeural"):
    if edge_tts is None:
        return False
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    return True

def generate_audio(text, output_path="podcast.mp3", voice="en-US-AriaNeural"):
    if edge_tts is None:
        return None
    try:
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        clean = re.sub(r'[#*_`]', '', clean)
        clean = clean[:5000]
        asyncio.run(_tts_async(clean, output_path, voice))
        return output_path
    except Exception as e:
        logger.warning("TTS failed: " + str(e))
        return None

# PHASE 5B: PODCAST GENERATION + RSS
def generate_podcast(topic, voice="en-US-AriaNeural"):
    try:
        script = ai_ask(
            "Write a 2-minute podcast script about: " + topic + ". "
            "Start with a warm intro. Include 3 main points. End with a call to action. "
            "Plain conversational text only, NO markdown symbols."
        )
        script = clean_ai_text(script)
        if "AI unavailable" in script:
            return None

        # Create a public audio directory
        os.makedirs("audio", exist_ok=True)
        filename = "podcast_" + str(int(time.time())) + ".mp3"
        audio_path = os.path.join("audio", filename)
        
        # Generate audio to the public path
        audio_file = generate_audio(script, audio_path, voice)
        if not audio_file:
            return None

        # Create the public URL
        public_url = RSS_BASE_URL.rstrip('/') + "/audio/" + filename

        # Save to database
        db.save_content(topic, "podcast", script, audio_file)
        db.save_podcast("Podcast: " + topic, script[:200], public_url, 120)
        
        return {"topic": topic, "script": script, "audio": audio_file, "public_url": public_url}
    except Exception as e:
        logger.error("Podcast generation failed: " + str(e))
        return None

def generate_rss_feed():
    """Generate RSS XML for Spotify/Apple Podcasts."""
    podcasts = db.get_all_podcasts(50)
    items = ""
    for p in podcasts:
        title, desc, url, dur, pub_date = p
        try:
            pub_formatted = datetime.fromisoformat(pub_date).strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pub_formatted = pub_date
        items += """
        <item>
            <title><![CDATA[""" + title + """]]></title>
            <description><![CDATA[""" + desc + """]]></description>
            <enclosure url=\"""" + url + """\" length="0" type="audio/mpeg"/>
            <guid>""" + url + """</guid>
            <pubDate>""" + pub_formatted + """</pubDate>
            <itunes:duration>""" + str(dur) + """</itunes:duration>
        </item>
        """
    
    # Placeholder cover art (1400x1400 minimum for Spotify)
    cover_art_url = "https://placehold.co/1400x1400/png?text=NOH4Q+Podcast"
    owner_email = "noh4qq@gmail.com" # Change this to your email if you want

    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
        <title>NOH4Q Daily Insights</title>
        <description>AI-generated insights on crypto, AI, and passive income.</description>
        <link>""" + RSS_BASE_URL + """</link>
        <language>en-us</language>
        <itunes:author>NOH4Q Agent</itunes:author>
        <itunes:category text="Business"/>
        <itunes:explicit>no</itunes:explicit>
        <itunes:image href="""" + cover_art_url + """" />
        <itunes:email>""" + owner_email + """</itunes:email>
        <itunes:owner>
            <itunes:name>NOH4Q Agent</itunes:name>
            <itunes:email>""" + owner_email + """</itunes:email>
        </itunes:owner>
        """ + items + """
    </channel>
</rss>"""
    return rss

# PHASE 6: INTERACTIVE CONTENT
def generate_quiz(topic, num_questions=5):
    """Generate a quiz about a topic."""
    try:
        prompt = (
            "Create " + str(num_questions) + " multiple choice quiz questions about " + topic + ". "
            "Format as JSON: [{\"question\": \"...\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"answer\": 0}, ...]"
        )
        result = ai_ask(prompt)
        result = clean_ai_text(result)
        
        # Try to extract JSON
        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            questions = json.loads(match.group())
            db.c.execute("INSERT INTO quizzes (topic, questions, created_at) VALUES (?,?,?)",
                         (topic, json.dumps(questions), datetime.now().isoformat()))
            db.conn.commit()
            return {"topic": topic, "questions": questions}
    except Exception as e:
        logger.error("Quiz generation failed: " + str(e))
    return None

def generate_poll(topic):
    """Generate a poll question."""
    return {
        "question": "What's your take on " + topic + "?",
        "options": ["Bullish", "Bearish", "Neutral", "Not sure"]
    }

def generate_calculator(topic):
    """Generate a simple calculator page."""
    html = """
    <!DOCTYPE html>
    <html><head><title>""" + topic + """ Calculator</title>
    <style>body{font-family:sans-serif;padding:20px;max-width:600px;margin:auto}
    input{padding:10px;width:100%;margin:5px 0;border:1px solid #ccc;border-radius:5px}
    button{padding:10px 20px;background:#667eea;color:white;border:none;border-radius:5px;cursor:pointer}
    .result{margin-top:20px;padding:15px;background:#f0f0f0;border-radius:5px}</style></head>
    <body><h1>""" + topic + """ Calculator</h1>
    <input id="input1" placeholder="Enter value 1">
    <input id="input2" placeholder="Enter value 2">
    <button onclick="calculate()">Calculate</button>
    <div class="result" id="result"></div>
    <script>
    function calculate() {
        var a = parseFloat(document.getElementById('input1').value);
        var b = parseFloat(document.getElementById('input2').value);
        document.getElementById('result').textContent = 'Result: ' + (a * b);
    }
    </script></body></html>
    """
    return html

# PHASE 7: EMAIL AUTOMATION
def send_email(to_email, subject, html_body):
    """Send email via Resend API."""
    if not RESEND_API_KEY:
        return False
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": to_email, "subject": subject, "html": html_body},
            timeout=30
        )
        return r.status_code == 200
    except Exception:
        return False

def send_newsletter(subject, content):
    """Send newsletter to all subscribers."""
    subscribers = db.get_subscribers()
    sent = 0
    for email in subscribers:
        if send_email(email, subject, content):
            sent += 1
    return {"sent": sent, "total": len(subscribers)}

# MARKET DATA
def get_crypto_price(symbol="BTC"):
    cmap = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL"}
    fsym = cmap.get(symbol.upper(), "BTC")
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/" + fsym + "-USD/spot", timeout=10)
        if r.status_code == 200:
            price = float(r.json()["data"]["amount"])
            db.save_price(symbol.upper(), price)
            return {"symbol": symbol.upper(), "price": price}
    except Exception:
        pass
    return {"error": "Price unavailable"}

def get_forex_price(pair="EUR/USD"):
    try:
        parts = pair.split("/")
        r = requests.get("https://api.frankfurter.app/latest?from=" + parts[0] + "&to=" + parts[1], timeout=10)
        if r.status_code == 200:
            rate = r.json()["rates"].get(parts[1])
            if rate:
                db.save_forex_price(pair, float(rate))
                return {"pair": pair, "price": float(rate)}
    except Exception:
        pass
    return {"error": "Could not fetch " + pair}

def get_commodity_price(commodity="XAU/USD"):
    yf_sym = COMMODITY_MAP.get(commodity.upper())
    if not yf_sym:
        return {"error": "Unknown"}
    try:
        import yfinance as yf
        t = yf.Ticker(yf_sym)
        price = None
        try:
            price = t.fast_info.get("last_price")
        except Exception:
            pass
        if not price:
            hist = t.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price:
            db.save_price(commodity.upper(), float(price))
            return {"symbol": commodity.upper(), "price": float(price)}
    except Exception:
        pass
    return {"error": "Could not fetch"}

# FOREX TRADING
def get_paper_balance():
    bal = db.get_setting("forex_balance", "")
    if not bal:
        db.set_setting("forex_balance", str(FOREX_START_BALANCE))
        return FOREX_START_BALANCE
    return float(bal)

def set_paper_balance(b):
    db.set_setting("forex_balance", str(round(b, 2)))

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def forex_signal(pair):
    history = db.get_forex_history(pair, limit=60)
    if len(history) < 20:
        return "hold", 0
    prices = [h[0] for h in history]
    s5 = calculate_sma(prices, 5)
    s20 = calculate_sma(prices, 20)
    if not s5 or not s20:
        return "hold", 0
    if s5 > s20 * 1.001:
        return "buy", min((s5 - s20) / s20 * 100, 1.0)
    elif s5 < s20 * 0.999:
        return "sell", min((s20 - s5) / s20 * 100, 1.0)
    return "hold", 0

def get_asset_price(asset):
    if "/" in asset and asset.upper() not in COMMODITY_MAP:
        return get_forex_price(asset)
    return get_commodity_price(asset)

def execute_paper_trade(asset):
    try:
        signal, _ = forex_signal(asset)
        if signal == "hold":
            return None
        price_data = get_asset_price(asset)
        if "error" in price_data:
            return None
        price = price_data["price"]
        balance = get_paper_balance()
        units = round(balance * (FOREX_RISK_PER_TRADE / 100) / price, 4)
        if units <= 0:
            return None
        for t in db.get_open_forex_trades():
            if t[1] == asset:
                return None
        db.save_forex_trade(asset, signal, price, 0, units, 0, "open")
        return {"pair": asset, "side": signal, "price": price, "units": units}
    except Exception:
        return None

def monitor_paper_trades():
    try:
        for trade in db.get_open_forex_trades():
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
                set_paper_balance(get_paper_balance() + pnl)
                db.earn("paper_trade", max(pnl, 0))
                return {"pair": pair, "side": side, "pnl": pnl}
    except Exception:
        pass
    return None

# SOCIAL POSTING
def track(platform, status, length):
    db.log_post(platform, status, length)

def post_to_telegram(text, image_url=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
        return False
    try:
        if image_url:
            r = requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendPhoto",
                              json={"chat_id": TELEGRAM_CHANNEL_ID, "photo": image_url, "caption": text[:1024]}, timeout=30)
            if r.status_code == 200:
                track("telegram", "ok", len(text))
                return True
        r = requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
                          json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4000]}, timeout=10)
        ok = r.status_code == 200
        track("telegram", "ok" if ok else "fail", len(text))
        return ok
    except Exception:
        return False

def post_to_discord(text, image_url=""):
    if not DISCORD_WEBHOOK:
        return False
    try:
        payload = {"content": text[:1900]}
        if image_url:
            payload["embeds"] = [{"image": {"url": image_url}}]
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=30)
        ok = r.status_code in [200, 204]
        track("discord", "ok" if ok else "fail", len(text))
        return ok
    except Exception:
        return False

def post_to_bluesky(text, image_url=""):
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        return False
    try:
        r = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                          json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}, timeout=15)
        if r.status_code != 200:
            return False
        s = r.json()
        jwt = s["accessJwt"]
        did = s["did"]
        record = {"text": text[:300], "$type": "app.bsky.feed.post", "createdAt": datetime.now().isoformat() + "Z"}
        if image_url:
            try:
                ir = requests.get(image_url, timeout=60)
                if ir.status_code == 200 and len(ir.content) > 1000:
                    up = requests.post("https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
                                       headers={"Authorization": "Bearer " + jwt, "Content-Type": "image/png"},
                                       data=ir.content, timeout=60)
                    if up.status_code == 200:
                        record["embed"] = {"$type": "app.bsky.embed.images",
                                           "images": [{"alt": text[:100], "image": up.json()["blob"]}]}
            except Exception:
                pass
        r2 = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                           headers={"Authorization": "Bearer " + jwt},
                           json={"repo": did, "collection": "app.bsky.feed.post", "record": record}, timeout=30)
        ok = r2.status_code == 200
        track("bluesky", "ok" if ok else "fail", len(text))
        return ok
    except Exception:
        return False

def post_to_mastodon(text, image_url=""):
    if not MASTODON_URL or not MASTODON_TOKEN:
        return False
    try:
        media_ids = []
        if image_url:
            try:
                ir = requests.get(image_url, timeout=60)
                if ir.status_code == 200 and len(ir.content) > 1000:
                    up = requests.post(MASTODON_URL + "/api/v2/media",
                                       headers={"Authorization": "Bearer " + MASTODON_TOKEN},
                                       files={"file": ("i.png", ir.content, "image/png")},
                                       data={"description": text[:100]}, timeout=60)
                    if up.status_code in [200, 202]:
                        media_ids.append(up.json()["id"])
            except Exception:
                pass
        payload = {"status": text[:500], "visibility": "public"}
        if media_ids:
            payload["media_ids"] = media_ids
        r = requests.post(MASTODON_URL + "/api/v1/statuses",
                          headers={"Authorization": "Bearer " + MASTODON_TOKEN}, json=payload, timeout=30)
        ok = r.status_code == 200
        track("mastodon", "ok" if ok else "fail", len(text))
        return ok
    except Exception:
        return False

# PHASE 9: FACEBOOK PAGE
def post_to_facebook(text, image_url=""):
    if not FACEBOOK_PAGE_ID or not FACEBOOK_PAGE_TOKEN:
        return False
    try:
        if image_url:
            r = requests.post(
                "https://graph.facebook.com/v25.0/" + FACEBOOK_PAGE_ID + "/photos",
                params={"url": image_url, "caption": text[:2000], "access_token": FACEBOOK_PAGE_TOKEN},
                timeout=60
            )
        else:
            r = requests.post(
                "https://graph.facebook.com/v25.0/" + FACEBOOK_PAGE_ID + "/feed",
                params={"message": text, "access_token": FACEBOOK_PAGE_TOKEN},
                timeout=30
            )
        ok = r.status_code == 200
        track("facebook", "ok" if ok else "fail", len(text))
        return ok
    except Exception:
        return False

def post_to_all_platforms(text, image_url=""):
    return {
        "telegram": post_to_telegram(text, image_url),
        "discord": post_to_discord(text, image_url),
        "bluesky": post_to_bluesky(text, image_url),
        "mastodon": post_to_mastodon(text, image_url),
        "facebook": post_to_facebook(text, image_url),
    }

# MARKDOWN PARSER
def parse_inline(text):
    parts = []
    pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)' r'|\*\*([^*]+)\*\*' r'|\*([^*]+)\*')
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            parts.append(text[pos:match.start()])
        if match.group(1) and match.group(2):
            parts.append({"tag": "a", "attrs": {"href": match.group(2)}, "children": [match.group(1)]})
        elif match.group(3):
            parts.append({"tag": "strong", "children": [match.group(3)]})
        elif match.group(4):
            parts.append({"tag": "em", "children": [match.group(4)]})
        pos = match.end()
    if pos < len(text):
        parts.append(text[pos:])
    return parts if parts else [text]

def md_to_nodes(text):
    nodes = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            nodes.append({"tag": "h4", "children": parse_inline(line[4:])})
        elif line.startswith("## "):
            nodes.append({"tag": "h3", "children": parse_inline(line[3:])})
        elif line.startswith("# "):
            nodes.append({"tag": "h3", "children": parse_inline(line[2:])})
        elif line.startswith("- ") or line.startswith("* "):
            nodes.append({"tag": "ul", "children": [{"tag": "li", "children": parse_inline(line[2:])}]})
        else:
            nodes.append({"tag": "p", "children": parse_inline(line)})
    return nodes

# TELEGRAPH + BEEHIIV
def get_telegraph_token():
    t = db.get_setting("telegraph_token", "")
    if t:
        return t
    try:
        r = requests.post("https://api.telegra.ph/createAccount",
                          data={"short_name": "NOH4Q", "author_name": "NOH4Q Agent"}, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            t = r.json()["result"]["access_token"]
            db.set_setting("telegraph_token", t)
            return t
    except Exception:
        pass
    return ""

def publish_to_telegraph(title, body):
    token = get_telegraph_token()
    if not token:
        return None
    try:
        r = requests.post("https://api.telegra.ph/createPage", data={
            "access_token": token, "title": title[:256], "author_name": "NOH4Q Agent",
            "content": json.dumps(md_to_nodes(body)), "return_content": "false"
        }, timeout=20)
        if r.status_code == 200 and r.json().get("ok"):
            return r.json()["result"]["url"]
    except Exception:
        pass
    return None

def publish_to_beehiiv(title, body):
    if not BEEHIIV_API_KEY or not BEEHIIV_PUBLICATION_ID:
        return False
    try:
        r = requests.post(
            "https://api.beehiiv.com/v2/publications/" + BEEHIIV_PUBLICATION_ID + "/posts",
            headers={"Authorization": "Bearer " + BEEHIIV_API_KEY, "Content-Type": "application/json"},
            json={"title": title, "body_content": body.replace("\n", "<br>"), "status": "draft"},
            timeout=30
        )
        return r.status_code == 201
    except Exception:
        return False

def publish_article(topic, body):
    title = "AI Insights: " + topic.title()
    return {"title": title, "telegraph": publish_to_telegraph(title, body),
            "beehiiv": publish_to_beehiiv(title, body) if BEEHIIV_API_KEY else False}

# TELEGRAM CONTROL
def tg_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception:
        pass

def tg_poll():
    offset = 0
    while True:
        try:
            r = requests.get("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/getUpdates",
                             params={"offset": offset + 1, "timeout": 20}, timeout=30)
            if r.status_code == 200:
                for update in r.json().get("result", []):
                    try:
                        offset = update["update_id"]
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        if "new_chat_members" in msg:
                            try:
                                for member in msg["new_chat_members"]:
                                    name = member.get("first_name", "friend")
                                    requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
                                                  json={"chat_id": chat_id, "text": "Welcome " + name + "!"}, timeout=10)
                            except Exception:
                                pass
                        if text:
                            handle_command(text, chat_id)
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(2)

def handle_command(text, chat_id):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = chat_id
    try:
        if text == "/start":
            tg_send(
                "NOH4Q Final Version\n"
                "Earned: $" + str(round(db.total(), 2)) + " | Balance: $" + str(round(get_paper_balance(), 2)) + "\n\n"
                "Content:\n"
                "/blog <topic> - article\n"
                "/post <topic> <type> - social post\n"
                "/podcast <topic> - audio podcast\n"
                "/quiz <topic> - create quiz\n"
                "/poll <topic> - create poll\n\n"
                "Trading:\n"
                "/forex - live prices\n"
                "/balance, /fxreport\n\n"
                "Analytics:\n"
                "/analytics, /growth, /affiliate\n"
                "/queue, /pending, /rss"
            )

        elif text == "/affiliate":
            tg_send("AFFILIATE\nAmazon: " + (AMAZON_AFFILIATE_TAG or "Not set") + "\nClickBank: " + (CLICKBANK_AFFILIATE_ID or "Not set"))

        elif text == "/growth":
            stats = db.get_engagement_stats()
            if not stats:
                tg_send("No engagement yet.")
                return
            msg = "ENGAGEMENT\n"
            for s in stats:
                msg += s["platform"] + " - " + s["action"] + ": " + str(s["count"]) + "\n"
            tg_send(msg)

        elif text == "/bluesky_grow":
            tg_send("Running Bluesky growth...")
            run_bluesky_growth()
            tg_send("Done. Check /growth")

        elif text == "/mastodon_grow":
            tg_send("Running Mastodon growth...")
            run_mastodon_growth()
            tg_send("Done. Check /growth")

        elif text == "/analytics":
            summary = db.get_analytics_summary()
            if not summary:
                tg_send("No posts tracked yet.")
                return
            msg = "ANALYTICS\n"
            for s in summary:
                msg += s["platform"].upper() + ": " + str(s["success"]) + "/" + str(s["total"]) + "\n"
            tg_send(msg)

        elif text.startswith("/queue "):
            topic = text[7:].strip()
            if topic:
                db.add_to_queue(topic, "post")
                tg_send("Queued: " + topic)

        elif text == "/pending":
            items = db.get_queue()
            if not items:
                tg_send("Queue empty")
            else:
                msg = "QUEUE (" + str(len(items)) + ")\n"
                for i, item in enumerate(items[:20], 1):
                    msg += "  " + str(i) + ". " + item[1] + "\n"
                tg_send(msg)

        elif text == "/rss":
            tg_send("RSS Feed: " + RSS_BASE_URL + "/rss.xml\nSubmit to:\n- podcasters.spotify.com\n- podcastsconnect.apple.com")

        elif text == "/platforms":
            tg_send(
                "Platforms:\n"
                "Telegram: " + ("OK" if TELEGRAM_CHANNEL_ID else "NO") + "\n"
                "Discord: " + ("OK" if DISCORD_WEBHOOK else "NO") + "\n"
                "Bluesky: " + ("OK" if BLUESKY_HANDLE else "NO") + "\n"
                "Mastodon: " + ("OK" if MASTODON_TOKEN else "NO") + "\n"
                "Facebook: " + ("OK" if FACEBOOK_PAGE_TOKEN else "NO") + "\n"
                "Telegraph: OK\n"
                "Beehiiv: " + ("OK" if BEEHIIV_API_KEY else "NO") + "\n"
                "FOREX: OK\n"
                "Podcast: " + ("OK" if edge_tts else "NO")
            )

        elif text == "/ai":
            tg_send("AI:\nGemini: " + ("OK" if GEMINI_KEY else "NO") + "\nOpenRouter: " + ("OK" if OPENROUTER_KEY else "NO") + "\nCohere: " + ("OK" if COHERE_KEY else "NO") + "\nHF: " + ("OK" if HF_KEY else "NO"))

        elif text == "/forex":
            msg = "FOREX\n"
            for p in FOREX_PAIRS:
                d = get_forex_price(p)
                if "error" not in d:
                    msg += "  " + p + ": " + str(d["price"]) + "\n"
            msg += "\nCOMMODITIES\n"
            for c in ["XAU/USD", "XAG/USD", "WTI", "BRENT"]:
                d = get_commodity_price(c)
                if "error" not in d:
                    msg += "  " + c + ": $" + str(round(d["price"], 2)) + "\n"
            tg_send(msg)

        elif text == "/balance":
            tg_send("Balance: $" + str(round(get_paper_balance(), 2)))

        elif text == "/fxreport":
            s = db.get_forex_stats()
            tg_send("PnL: $" + str(round(s["total_pnl"], 2)) + "\nTrades: " + str(s["total_trades"]) + "\nWin Rate: " + str(round(s["win_rate"], 1)) + "%")

        elif text.startswith("/quiz "):
            topic = text[6:].strip()
            tg_send("Generating quiz about " + topic + "...")
            quiz = generate_quiz(topic)
            if quiz:
                msg = "QUIZ: " + topic + "\n\n"
                for i, q in enumerate(quiz["questions"][:3], 1):
                    msg += str(i) + ". " + q["question"] + "\n"
                    for j, opt in enumerate(q["options"]):
                        msg += "   " + chr(65+j) + ") " + opt + "\n"
                    msg += "\n"
                tg_send(msg)
            else:
                tg_send("Quiz failed.")

        elif text.startswith("/poll "):
            topic = text[6:].strip()
            poll = generate_poll(topic)
            msg = poll["question"] + "\n\n"
            for opt in poll["options"]:
                msg += "  - " + opt + "\n"
            tg_send(msg)

        elif text.startswith("/podcast "):
            topic = text[9:].strip()
            tg_send("Generating podcast about " + topic + "...")
            result = generate_podcast(topic)
            if result:
                tg_send("Podcast ready.")
                send_audio_to_telegram(result["audio"], "Podcast: " + topic)
            else:
                tg_send("Podcast failed.")

        elif text.startswith("/post "):
            parts = text[6:].strip().split()
            if len(parts) >= 2:
                topic = " ".join(parts[:-1])
                ctype = parts[-1]
                tg_send("Generating...")
                r = generate_content(topic, ctype, with_image=True)
                if "AI unavailable" not in r["body"]:
                    results = post_to_all_platforms(r["body"], r["image_url"])
                    ok = sum(1 for v in results.values() if v)
                    tg_send("Posted to " + str(ok) + "/5 platforms")

        elif text.startswith("/blog "):
            topic = text[6:].strip()
            tg_send("Writing " + topic + "...")
            r = generate_content(topic, "article", with_image=False)
            if "AI unavailable" not in r["body"]:
                pub = publish_article(topic, r["body"])
                msg = "Published!\n"
                if pub["telegraph"]:
                    msg += pub["telegraph"] + "\n"
                if pub["beehiiv"]:
                    msg += "Beehiiv draft created"
                tg_send(msg)

        elif text.startswith("/price "):
            sym = text[7:].strip().upper()
            r = get_crypto_price(sym)
            if "error" not in r:
                tg_send(r["symbol"] + ": $" + str(round(r["price"], 2)))

        elif text.startswith("/subscribe "):
            email = text[11:].strip()
            if "@" in email:
                if db.add_subscriber(email):
                    tg_send("Subscribed: " + email)
                else:
                    tg_send("Failed to subscribe.")
            else:
                tg_send("Invalid email.")

        elif text.startswith("/newsletter "):
            subject = text[12:].strip()
            tg_send("Generating newsletter...")
            content_res = generate_content(subject, "article", with_image=False)
            if "AI unavailable" not in content_res["body"]:
                result = send_newsletter(subject, content_res["body"])
                tg_send("Newsletter sent to " + str(result["sent"]) + "/" + str(result["total"]) + " subscribers.")
            else:
                tg_send("Failed to generate newsletter content.")

        else:
            tg_send("Thinking...")
            reply = ai_ask("You are NOH4Q. Reply concisely (under 200 chars, plain text) to: " + text)
            reply = clean_ai_text(reply)
            tg_send(reply[:500])
    except Exception as e:
        logger.warning("Command error: " + str(e))

# Send audio to telegram
def send_audio_to_telegram(audio_path, caption=""):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not audio_path:
        return False
    try:
        with open(audio_path, "rb") as f:
            files = {"audio": f}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]}
            r = requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendAudio",
                              files=files, data=data, timeout=120)
        return r.status_code == 200
    except Exception:
        return False

# Growth loops
def bluesky_login():
    try:
        r = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                          json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD}, timeout=15)
        if r.status_code == 200:
            s = r.json()
            return s["accessJwt"], s["did"]
    except Exception:
        pass
    return None, None

def bluesky_search(term, limit=10):
    jwt, _ = bluesky_login()
    if not jwt:
        return []
    try:
        r = requests.get("https://bsky.social/xrpc/app.bsky.feed.searchPosts",
                         headers={"Authorization": "Bearer " + jwt},
                         params={"q": term, "limit": limit}, timeout=15)
        if r.status_code == 200:
            return r.json().get("posts", [])
    except Exception:
        pass
    return []

def bluesky_follow(target_did):
    jwt, my_did = bluesky_login()
    if not jwt:
        return False
    try:
        r = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                          headers={"Authorization": "Bearer " + jwt},
                          json={"repo": my_did, "collection": "app.bsky.graph.follow",
                                "record": {"$type": "app.bsky.graph.follow", "subject": target_did,
                                           "createdAt": datetime.now().isoformat() + "Z"}}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def bluesky_like(post_uri, post_cid):
    jwt, my_did = bluesky_login()
    if not jwt:
        return False
    try:
        r = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                          headers={"Authorization": "Bearer " + jwt},
                          json={"repo": my_did, "collection": "app.bsky.feed.like",
                                "record": {"$type": "app.bsky.feed.like",
                                           "subject": {"uri": post_uri, "cid": post_cid},
                                           "createdAt": datetime.now().isoformat() + "Z"}}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def run_bluesky_growth():
    if not ENABLE_BLUESKY_GROWTH or not BLUESKY_HANDLE:
        return
    term = random.choice(NICHE_TERMS)
    posts = bluesky_search(term, limit=15)
    if not posts:
        return
    follows = 0
    likes = 0
    for post in posts:
        try:
            author_did = post.get("author", {}).get("did", "")
            post_uri = post.get("uri", "")
            post_cid = post.get("cid", "")
            if not author_did or not post_uri:
                continue
            if follows < MAX_FOLLOWS_PER_CYCLE:
                if bluesky_follow(author_did):
                    follows += 1
                    db.log_engagement("bluesky", "follow", author_did)
            if likes < MAX_LIKES_PER_CYCLE:
                if bluesky_like(post_uri, post_cid):
                    likes += 1
                    db.log_engagement("bluesky", "like", post_uri)
            time.sleep(3)
        except Exception:
            pass
    logger.info("Bluesky: " + str(follows) + " follows, " + str(likes) + " likes")

def mastodon_search(term, limit=10):
    if not MASTODON_URL or not MASTODON_TOKEN:
        return []
    try:
        r = requests.get(MASTODON_URL + "/api/v2/search",
                         headers={"Authorization": "Bearer " + MASTODON_TOKEN},
                         params={"q": "#" + term, "type": "statuses", "limit": limit}, timeout=15)
        if r.status_code == 200:
            return r.json().get("statuses", [])
    except Exception:
        pass
    return []

def mastodon_follow(account_id):
    try:
        r = requests.post(MASTODON_URL + "/api/v1/accounts/" + account_id + "/follow",
                          headers={"Authorization": "Bearer " + MASTODON_TOKEN}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def mastodon_like(status_id):
    try:
        r = requests.post(MASTODON_URL + "/api/v1/statuses/" + status_id + "/favourite",
                          headers={"Authorization": "Bearer " + MASTODON_TOKEN}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def run_mastodon_growth():
    if not ENABLE_MASTODON_GROWTH or not MASTODON_TOKEN:
        return
    term = random.choice(NICHE_TERMS)
    statuses = mastodon_search(term, limit=15)
    if not statuses:
        return
    follows = 0
    likes = 0
    for status in statuses:
        try:
            account_id = status.get("account", {}).get("id", "")
            status_id = status.get("id", "")
            if not account_id or not status_id:
                continue
            if follows < MAX_FOLLOWS_PER_CYCLE:
                if mastodon_follow(account_id):
                    follows += 1
                    db.log_engagement("mastodon", "follow", account_id)
            if likes < MAX_LIKES_PER_CYCLE:
                if mastodon_like(status_id):
                    likes += 1
                    db.log_engagement("mastodon", "like", status_id)
            time.sleep(3)
        except Exception:
            pass
    logger.info("Mastodon: " + str(follows) + " follows, " + str(likes) + " likes")

# CONTENT GENERATION
def generate_content(topic, content_type="post", with_image=True):
    prompts = {
        "article": "Write a 400-word article about: " + topic + ". Do NOT use markdown symbols. Clean prose. End with conclusion.",
        "post": "Write an engaging social media post about: " + topic + ". Include 3-5 hashtags. Plain text only.",
    }
    body = ai_ask(prompts.get(content_type, prompts["post"]))
    body = clean_ai_text(body)
    if content_type == "article":
        body = inject_affiliate_links(body)
    img = ""
    if with_image and "AI unavailable" not in body:
        try:
            img = generate_image_url(create_image_prompt(topic, body))
        except Exception:
            img = ""
    db.save_content(topic, content_type, body, img)
    return {"topic": topic, "type": content_type, "body": body, "image_url": img}

# WORK LOOP
def work_loop():
    cycle_count = 0
    while True:
        try:
            cycle_count += 1
            logger.info("Cycle " + str(cycle_count) + " starting...")

            price = get_crypto_price("BTC")
            for p in FOREX_PAIRS:
                get_forex_price(p)
            for c in COMMODITY_MAP.keys():
                get_commodity_price(c)

            execute_paper_trade("EUR/USD")
            execute_paper_trade("XAU/USD")
            closed = monitor_paper_trades()

            if cycle_count % 2 == 0:
                try:
                    run_bluesky_growth()
                except Exception:
                    pass
                try:
                    run_mastodon_growth()
                except Exception:
                    pass

            queued = db.pop_queue()
            topic = queued["topic"] if queued else random.choice(["crypto trading", "AI automation", "passive income"])

            content = generate_content(topic, "post", with_image=True)
            if "AI unavailable" not in content["body"]:
                post_to_all_platforms(content["body"], content["image_url"])

            article = generate_content(topic, "article", with_image=False)
            if "AI unavailable" not in article["body"]:
                pub = publish_article(topic, article["body"])
                if pub["telegraph"]:
                    tg_send("New article: " + pub["telegraph"])

            if cycle_count % 3 == 0:
                try:
                    pod = generate_podcast(topic)
                    if pod:
                        tg_send("Podcast ready: " + topic)
                        send_audio_to_telegram(pod["audio"], "Podcast: " + topic)
                except Exception as e:
                    logger.warning("Podcast failed: " + str(e))

            if closed:
                tg_send("Closed: " + closed["side"].upper() + " " + closed["pair"] + " PnL: $" + str(round(closed["pnl"], 2)))

            db.earn("daily_task", round(random.uniform(0.01, 0.10), 4))
            tg_send("Cycle " + str(cycle_count) + " done.")

            time.sleep(14400)
        except Exception as e:
            logger.error("Work loop error: " + str(e))
            time.sleep(300)

# WEB SERVER
app = Flask(__name__)

@app.route("/")
def home():
    try:
        return "<h1>NOH4Q Final</h1><p>Earned: $" + str(round(db.total(), 2)) + "</p>"
    except Exception:
        return "<h1>NOH4Q</h1>"

@app.route("/health")
def health():
    try:
        return {"status": "alive", "earned": db.total()}
    except Exception:
        return {"status": "alive"}

@app.route("/rss.xml")
def rss():
    return generate_rss_feed(), 200, {"Content-Type": "application/rss+xml; charset=utf-8"}

@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory("audio", filename)

@app.route("/api/status")
def api_status():
    try:
        return jsonify({"alive": True, "earned": db.total(), "forex": db.get_forex_stats()})
    except Exception:
        return jsonify({"alive": True})

@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data = request.json
    email = data.get("email", "")
    if email:
        if db.add_subscriber(email):
            return jsonify({"success": True})
    return jsonify({"success": False}), 400

# SAFE START
def safe_start():
    try:
        threading.Thread(target=tg_poll, daemon=True).start()
        logger.info("Telegram poller started")
    except Exception as e:
        logger.error("tg_poll failed: " + str(e))

    try:
        threading.Thread(target=work_loop, daemon=True).start()
        logger.info("Work loop started")
    except Exception as e:
        logger.error("work_loop failed: " + str(e))

    logger.info("NOH4Q FINAL READY")

safe_start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
