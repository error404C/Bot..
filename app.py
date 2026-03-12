"""
iVAS Setup Bot — Telegram Version (Fixed for Python 3.14)
"""
import logging
import json
import os
import io
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, Response
import requests as req

# ══════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════
BOT_TOKEN  = "8291963800:AAErU7MDzn-hPrL_1D69TDgMdp949XrzeOY"
ADMIN_ID   = "7578254597"
PORT       = int(os.getenv("PORT", 10000))
RENDER_URL = os.getenv("RENDER_URL", "https://your-app.onrender.com")
# ══════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app      = Flask(__name__)
sessions = {}

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def tg_send(chat_id, text):
    """Send Telegram message using plain requests — no async needed."""
    try:
        req.post(f"{TG_API}/sendMessage", json={
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        log.error("tg_send error: %s", e)


def tg_send_file(chat_id, filename, content, caption):
    """Send file to Telegram."""
    try:
        req.post(f"{TG_API}/sendDocument", files={
            "document": (filename, io.BytesIO(content.encode()), "application/json")
        }, data={
            "chat_id": chat_id,
            "caption": caption
        }, timeout=15)
    except Exception as e:
        log.error("tg_send_file error: %s", e)


# ── HTML Page ─────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>iVAS Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; padding: 15px; }
        h1 { color: #e94560; margin-bottom: 10px; font-size: 20px; }
        .card { background: #16213e; border-radius: 10px; padding: 15px; margin: 10px 0; }
        .step { border-left: 3px solid #e94560; padding: 8px 12px; margin: 6px 0; font-size: 14px; }
        button { background: #e94560; color: white; border: none; padding: 14px; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%; margin: 6px 0; font-weight: bold; }
        button.blue { background: #0f3460; }
        #status { padding: 12px; border-radius: 8px; margin: 8px 0; font-size: 14px; text-align: center; }
        .ok { background: #064e3b; color: #4ade80; }
        .waiting { background: #1c1c00; color: #facc15; }
        .error { background: #450a0a; color: #f87171; }
        iframe { width: 100%; height: 450px; border: 2px solid #e94560; border-radius: 8px; margin: 8px 0; }
        #log { background: #0d0d1a; padding: 8px; border-radius: 6px; font-family: monospace; font-size: 11px; max-height: 120px; overflow-y: auto; margin-top: 8px; }
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

    <div id="status" class="waiting">⏳ Login to iVAS above then capture</div>
    <div id="log"></div>

<script>
var SESSION_ID = "SESSION_ID_PLACEHOLDER";
var ajaxCalls = [];

function addLog(msg) {
    var el = document.getElementById('log');
    el.innerHTML += '<div>' + new Date().toLocaleTimeString() + ' — ' + msg + '</div>';
    el.scrollTop = el.scrollHeight;
}

function gotoSMS() {
    document.getElementById('frame').src = 'https://www.ivasms.com/portal/live/my_sms';
    addLog('Going to SMS page...');
}

var origOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    if (url && url.toString().includes('ivasms')) {
        addLog('XHR: ' + method + ' ' + url);
        ajaxCalls.push({method: method, url: url.toString()});
    }
    return origOpen.apply(this, arguments);
};

var origFetch = window.fetch;
window.fetch = function(url, opts) {
    opts = opts || {};
    var urlStr = (typeof url === 'string') ? url : url.toString();
    if (urlStr.includes('ivasms')) {
        addLog('Fetch: ' + (opts.method||'GET') + ' ' + urlStr);
        ajaxCalls.push({method: opts.method||'GET', url: urlStr});
    }
    return origFetch.apply(this, arguments);
};

function getCookies() {
    var cookies = {};
    document.cookie.split(';').forEach(function(c) {
        var parts = c.trim().split('=');
        if (parts.length >= 2) {
            cookies[parts[0].trim()] = parts.slice(1).join('=');
        }
    });
    return cookies;
}

function capture() {
    var cookies = getCookies();
    addLog('Cookies found: ' + JSON.stringify(Object.keys(cookies)));
    addLog('AJAX calls: ' + ajaxCalls.length);

    document.getElementById('status').className = 'waiting';
    document.getElementById('status').textContent = '⏳ Sending to Telegram...';

    fetch('/capture', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            session_id: SESSION_ID,
            cookies: cookies,
            ajax_calls: ajaxCalls,
            timestamp: new Date().toISOString()
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(resp) {
        if (resp.success) {
            document.getElementById('status').className = 'ok';
            document.getElementById('status').textContent = '✅ ' + resp.message;
        } else {
            document.getElementById('status').className = 'error';
            document.getElementById('status').textContent = '❌ ' + resp.message;
        }
    })
    .catch(function(e) {
        document.getElementById('status').className = 'error';
        document.getElementById('status').textContent = '❌ ' + e;
    });
}

setInterval(function() {
    try {
        var url = document.getElementById('frame').contentWindow.location.href;
        if (url.includes('/portal')) {
            document.getElementById('status').className = 'ok';
            document.getElementById('status').textContent = '✅ Logged in! Go to SMS page then capture.';
        }
    } catch(e) {}
}, 1500);

addLog('Ready. Login to iVAS in the frame.');
</script>
</body>
</html>
"""


# ── Flask Routes ──────────────────────────────

@app.route("/")
def index():
    return jsonify({"status": "iVAS Setup Bot running", "usage": "Send /setup to the Telegram bot"})


@app.route("/setup/<session_id>")
def setup_page(session_id):
    html = HTML_PAGE.replace("SESSION_ID_PLACEHOLDER", session_id)
    return Response(html, mimetype="text/html")


@app.route("/capture", methods=["POST"])
def capture():
    try:
        data       = request.get_json()
        session_id = data.get("session_id", "unknown")
        cookies    = data.get("cookies", {})
        ajax_calls = data.get("ajax_calls", [])

        log.info("Captured — cookies: %s | ajax: %d", list(cookies.keys()), len(ajax_calls))

        if not cookies:
            return jsonify({"success": False, "message": "No cookies found. Make sure you are fully logged in first."})

        config = {
            "cookies":     cookies,
            "ajax_calls":  ajax_calls,
            "captured_at": data.get("timestamp", datetime.now().isoformat()),
        }
        config_json = json.dumps(config, indent=2)

        # Send summary to Telegram
        ajax_info = "\n".join([f"  [{c.get('method','?')}] {c.get('url','?')}" for c in ajax_calls[:5]])
        tg_send(ADMIN_ID,
            "✅ *iVAS Session Captured!*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🍪 *Cookies:* `{list(cookies.keys())}`\n"
            f"🔗 *AJAX calls:* {len(ajax_calls)}\n"
            f"`{ajax_info if ajax_info else 'None'}`\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📎 Sending config.json now..."
        )

        # Send config.json file
        tg_send_file(
            ADMIN_ID,
            "config.json",
            config_json,
            "📁 Your config.json — upload this to your main bot repo on GitHub then redeploy on Render"
        )

        log.info("✅ config.json sent to Telegram")
        return jsonify({"success": True, "message": "config.json sent to your Telegram! Check it now."})

    except Exception as e:
        log.error("Capture error: %s", e)
        return jsonify({"success": False, "message": str(e)})


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle Telegram webhook updates."""
    try:
        data    = request.get_json()
        message = data.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text    = message.get("text", "")
        user_id = str(message.get("from", {}).get("id", ""))

        if not text:
            return jsonify({"ok": True})

        if text == "/start":
            tg_send(chat_id,
                "👋 *iVAS Setup Bot*\n\n"
                "Send /setup to get your iVAS session capture link.\n"
                "This captures cookies and sends you config.json."
            )

        elif text == "/setup":
            if user_id != str(ADMIN_ID):
                tg_send(chat_id, "❌ Unauthorized.")
            else:
                session_id = secrets.token_hex(8)
                sessions[session_id] = {"user_id": user_id}
                link = f"{RENDER_URL}/setup/{session_id}"
                tg_send(chat_id,
                    "🔧 *iVAS Session Capture*\n\n"
                    f"👉 Open this link:\n{link}\n\n"
                    "📋 *Steps:*\n"
                    "1\\. Login to iVAS in the page\n"
                    "2\\. Click 'Go to SMS Page'\n"
                    "3\\. Click 'Capture & Send to Telegram'\n"
                    "4\\. I'll send you config\\.json ✅"
                )

        elif text == "/help":
            tg_send(chat_id, "📖 *Commands:*\n\n/setup — Get capture link\n/start — Welcome\n/help — This message")

        return jsonify({"ok": True})

    except Exception as e:
        log.error("Webhook error: %s", e)
        return jsonify({"ok": True})


@app.route("/set_webhook")
def set_webhook():
    """Call this once to register webhook with Telegram."""
    webhook_url = f"{RENDER_URL}/webhook"
    resp = req.post(f"{TG_API}/setWebhook", json={"url": webhook_url})
    return jsonify(resp.json())


if __name__ == "__main__":
    log.info("=== iVAS Setup Bot starting ===")
    log.info("Port: %d | Render URL: %s", PORT, RENDER_URL)
    log.info("After deploy, open: %s/set_webhook", RENDER_URL)
    app.run(host="0.0.0.0", port=PORT)
