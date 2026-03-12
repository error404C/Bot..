 """
iVAS Setup Bot — Telegram Version
===================================
This bot runs on Render/Railway as a WEB SERVICE.
It gives you a login link, you login to iVAS through it,
and it sends you config.json directly on Telegram.

HOW TO USE:
1. Deploy this as a Web Service on Render
2. Message the bot /setup on Telegram
3. Bot sends you a login link
4. Open the link, login to iVAS, go to SMS page
5. Click "Capture Session"
6. Bot sends you config.json on Telegram automatically
7. Forward config.json to your main bot
"""
import asyncio
import logging
import json
import os
import threading
from datetime import datetime
from flask import Flask, request, jsonify, Response
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError

# ══════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════
SETUP_BOT_TOKEN = "8291963800:AAErU7MDzn-hPrL_1D69TDgMdp949XrzeOY"  # Same bot token
ADMIN_ID        = "7578254597"
PORT            = int(os.getenv("PORT", 5000))
# Your Render URL — update this after first deploy
RENDER_URL      = os.getenv("RENDER_URL", "https://your-app.onrender.com")
# ══════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app  = Flask(__name__)
bot  = Bot(token=SETUP_BOT_TOKEN)

# Store captured sessions in memory
sessions = {}

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>iVAS Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; padding: 15px; }}
        h1 {{ color: #e94560; margin-bottom: 10px; font-size: 20px; }}
        .card {{ background: #16213e; border-radius: 10px; padding: 15px; margin: 10px 0; }}
        .step {{ border-left: 3px solid #e94560; padding: 8px 12px; margin: 6px 0; font-size: 14px; }}
        button {{ background: #e94560; color: white; border: none; padding: 14px; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%; margin: 6px 0; font-weight: bold; }}
        button.blue {{ background: #0f3460; }}
        button:active {{ opacity: 0.8; }}
        #status {{ padding: 12px; border-radius: 8px; margin: 8px 0; font-size: 14px; text-align: center; }}
        .ok {{ background: #064e3b; color: #4ade80; }}
        .waiting {{ background: #1c1c00; color: #facc15; }}
        .error {{ background: #450a0a; color: #f87171; }}
        iframe {{ width: 100%; height: 450px; border: 2px solid #e94560; border-radius: 8px; margin: 8px 0; }}
        #log {{ background: #0d0d1a; padding: 8px; border-radius: 6px; font-family: monospace; font-size: 11px; max-height: 120px; overflow-y: auto; margin-top: 8px; }}
    </style>
</head>
<body>
    <h1>🔧 iVAS Session Capture</h1>
    <div class="card">
        <div class="step">1️⃣ Login to iVAS in the frame below</div>
        <div class="step">2️⃣ Click "Go to SMS Page"</div>
        <div class="step">3️⃣ Click "Capture & Send to Telegram"</div>
    </div>

    <iframe id="frame" src="https://www.ivasms.com/login"></iframe>

    <button class="blue" onclick="gotoSMS()">📨 Go to SMS Page</button>
    <button onclick="capture()">🎯 Capture & Send to Telegram</button>

    <div id="status" class="waiting">⏳ Login to iVAS above, then capture</div>
    <div id="log"></div>

<script>
var SESSION_ID = "{session_id}";
var ajaxCalls = [];

function addLog(msg) {{
    var el = document.getElementById('log');
    el.innerHTML += '<div>' + new Date().toLocaleTimeString() + ' — ' + msg + '</div>';
    el.scrollTop = el.scrollHeight;
}}

function gotoSMS() {{
    document.getElementById('frame').src = 'https://www.ivasms.com/portal/live/my_sms';
    addLog('Navigating to SMS page...');
}}

// Intercept XHR to catch AJAX calls
var origOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {{
    if (url && url.toString().includes('ivasms')) {{
        addLog('XHR: ' + method + ' ' + url);
        ajaxCalls.push({{method: method, url: url.toString()}});
    }}
    return origOpen.apply(this, arguments);
}};

// Intercept fetch
var origFetch = window.fetch;
window.fetch = function(url, opts) {{
    opts = opts || {{}};
    var urlStr = (typeof url === 'string') ? url : url.toString();
    if (urlStr.includes('ivasms')) {{
        addLog('Fetch: ' + (opts.method||'GET') + ' ' + urlStr);
        ajaxCalls.push({{method: opts.method||'GET', url: urlStr}});
    }}
    return origFetch.apply(this, arguments);
}};

function getCookies() {{
    var cookies = {{}};
    document.cookie.split(';').forEach(function(c) {{
        var parts = c.trim().split('=');
        if (parts.length >= 2) {{
            cookies[parts[0].trim()] = parts.slice(1).join('=');
        }}
    }});
    return cookies;
}}

function capture() {{
    var cookies = getCookies();
    var data = {{
        session_id: SESSION_ID,
        cookies: cookies,
        ajax_calls: ajaxCalls,
        timestamp: new Date().toISOString()
    }};

    addLog('Cookies: ' + JSON.stringify(Object.keys(cookies)));
    addLog('AJAX calls: ' + ajaxCalls.length);

    document.getElementById('status').className = 'waiting';
    document.getElementById('status').textContent = '⏳ Sending to Telegram...';

    fetch('/capture', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(data)
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(resp) {{
        if (resp.success) {{
            document.getElementById('status').className = 'ok';
            document.getElementById('status').textContent = '✅ ' + resp.message;
            addLog('✅ Done! Check your Telegram.');
        }} else {{
            document.getElementById('status').className = 'error';
            document.getElementById('status').textContent = '❌ ' + resp.message;
        }}
    }})
    .catch(function(e) {{
        document.getElementById('status').className = 'error';
        document.getElementById('status').textContent = '❌ Error: ' + e;
    }});
}}

// Monitor iframe
setInterval(function() {{
    try {{
        var url = document.getElementById('frame').contentWindow.location.href;
        if (url.includes('/portal')) {{
            document.getElementById('status').className = 'ok';
            document.getElementById('status').textContent = '✅ Logged in! Now go to SMS page then capture.';
        }}
    }} catch(e) {{}}
}}, 1500);

addLog('Ready. Login to iVAS in the frame above.');
</script>
</body>
</html>
"""


# ── Flask Routes ──────────────────────────────

@app.route("/")
def index():
    return jsonify({"status": "iVAS Setup Bot is running", "usage": "Message /setup to the Telegram bot"})


@app.route("/setup/<session_id>")
def setup_page(session_id):
    html = HTML_PAGE.replace("{session_id}", session_id)
    return Response(html, mimetype="text/html")


@app.route("/capture", methods=["POST"])
def capture():
    try:
        data       = request.get_json()
        session_id = data.get("session_id", "unknown")
        cookies    = data.get("cookies", {})
        ajax_calls = data.get("ajax_calls", [])

        log.info("Capture received — session: %s | cookies: %s | ajax: %d",
                 session_id, list(cookies.keys()), len(ajax_calls))

        if not cookies:
            return jsonify({"success": False, "message": "No cookies found. Make sure you are fully logged in to iVAS first."})

        # Build config.json content
        config = {
            "cookies":    cookies,
            "ajax_calls": ajax_calls,
            "captured_at": data.get("timestamp", datetime.now().isoformat()),
        }

        config_json = json.dumps(config, indent=2)

        # Send to Telegram asynchronously
        threading.Thread(
            target=send_config_to_telegram,
            args=(session_id, config_json, cookies, ajax_calls)
        ).start()

        return jsonify({
            "success": True,
            "message": f"✅ Captured {len(cookies)} cookies! Sending config.json to your Telegram now..."
        })

    except Exception as e:
        log.error("Capture error: %s", e)
        return jsonify({"success": False, "message": str(e)})


def send_config_to_telegram(session_id, config_json, cookies, ajax_calls):
    """Send config.json file to Telegram admin."""
    async def _send():
        try:
            # Send summary message
            ajax_info = "\n".join([f"  [{c.get('method','?')}] `{c.get('url','?')}`" for c in ajax_calls[:5]])
            msg = (
                "✅ *iVAS Session Captured!*\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"🍪 *Cookies:* {list(cookies.keys())}\n"
                f"🔗 *AJAX calls:* {len(ajax_calls)}\n"
                f"{ajax_info if ajax_info else '  None captured'}\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📎 *config.json file below — save it and upload to your main bot folder on Render/GitHub*"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")

            # Send config.json as a file
            import io
            file_bytes = io.BytesIO(config_json.encode())
            file_bytes.name = "config.json"
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=file_bytes,
                filename="config.json",
                caption="📁 Your config.json — upload this to your main bot on Render/GitHub"
            )
            log.info("✅ config.json sent to Telegram successfully")

        except Exception as e:
            log.error("Telegram send error: %s", e)

    asyncio.run(_send())


# ── Telegram Bot Commands ─────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *iVAS Setup Bot*\n\n"
        "Use /setup to get your iVAS session capture link.\n"
        "This will give you a `config.json` file for your main OTP bot.",
        parse_mode="Markdown"
    )


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    # Only allow admin
    if user_id != str(ADMIN_ID):
        await update.message.reply_text("❌ Unauthorized.")
        return

    import secrets
    session_id = secrets.token_hex(8)
    sessions[session_id] = {"user_id": user_id, "created": datetime.now().isoformat()}

    link = f"{RENDER_URL}/setup/{session_id}"

    await update.message.reply_text(
        "🔧 *iVAS Session Capture*\n\n"
        f"👉 Open this link:\n{link}\n\n"
        "📋 *Steps:*\n"
        "1. Login to iVAS in the page\n"
        "2. Click 'Go to SMS Page'\n"
        "3. Click 'Capture & Send to Telegram'\n"
        "4. I'll send you `config.json` automatically ✅",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Commands:*\n\n"
        "/setup — Get iVAS capture link\n"
        "/start — Welcome message\n"
        "/help — This message",
        parse_mode="Markdown"
    )


# ── Main ──────────────────────────────────────

def run_flask():
    app.run(host="0.0.0.0", port=PORT)


async def run_telegram():
    application = Application.builder().token(SETUP_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("setup", cmd_setup))
    application.add_handler(CommandHandler("help", cmd_help))
    log.info("Telegram bot started.")
    await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    log.info("=== iVAS Setup Bot starting ===")
    log.info("Flask on port %d | Render URL: %s", PORT, RENDER_URL)

    # Run Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run Telegram bot in main thread
    asyncio.run(run_telegram())
