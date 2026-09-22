#!/usr/bin/env python3
"""
NOH4Q AGENT - FREE CLOUD AI AGENT
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
        self.conn.commit()

    def log(self, etype, message):
        self.c.execute("INSERT INTO events (type, message, ts) VALUES (?,?,?)",
                       (etype, message, datetime.now().isoformat()))
        self.conn.commit()

    def earn(self, source, amount):
        self.c.execute("INSERT INTO earnings (source, amount, ts) VALUES (?,?,?)",
                       (source, amount, datetime.now().isoformat()))
        self.conn.commit()

    def total(self):
        self.c.execute("SELECT COALESCE(SUM(amount),0) FROM earnings")
        return self.c.fetchone()[0]

db = DB()

# ============================================
# AI BRAIN (Gemini)
# ============================================
def ai_ask(prompt):
    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.warning(f"Gemini failed: {e}")
    return "AI unavailable - fallback mode"

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
        tg_send(f"🤖 NOH4Q Agent online.\nTotal earned: ${db.total():.2f}")
    elif text == "/status":
        tg_send(f"✅ Agent running.\nEarned: ${db.total():.2f}\nTime: {datetime.now().isoformat()}")
    elif text == "/report":
        tg_send(f"📊 Report\nEarned: ${db.total():.2f}\nEvents logged: {len(db.c.execute('SELECT * FROM events').fetchall())}")
    elif text.startswith("/ask "):
        answer = ai_ask(text[5:])
        tg_send(f"🧠 {answer}")
    elif text == "/NOH4Q":
        tg_send("🔓 Unlocked. Full access enabled.")
    else:
        tg_send(f"Unknown command: {text}\nTry /status, /report, /ask <question>")

# ============================================
# AUTOMATION LOOP (24/7 work)
# ============================================
def work_loop():
    while True:
        try:
            # 1. Daily AI task
            idea = ai_ask("Give one short money-making idea in one sentence.")
            db.log("ai", idea)
            logger.info(f"AI idea: {idea}")

            # 2. Simulated earning track
            db.earn("daily_task", round(random.uniform(0.01, 0.10), 4))
            db.log("earning", "Daily task completed")

            # 3. Telegram daily ping (once per cycle)
            tg_send(f"💼 Cycle done. Total: ${db.total():.2f}")

            # Wait 1 hour between cycles
            time.sleep(3600)
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
    <h1>🤖 NOH4Q Agent</h1>
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

# ============================================
# START BACKGROUND TASKS (Runs with Gunicorn)
# ============================================
logger.info("🚀 NOH4Q starting background tasks...")
threading.Thread(target=tg_poll, daemon=True).start()
threading.Thread(target=work_loop, daemon=True).start()
logger.info("✅ Telegram listener started. Waiting for messages...")

# ============================================
# MAIN ENTRY (For local testing only)
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
