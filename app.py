import logging
import asyncio
import re
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError

# ══════════════════════════════════════════════
#   CONFIG
# ══════════════════════════════════════════════
IVAS_EMAIL    = "larrymullenjr3@gmail.com"
IVAS_PASSWORD = "larry123@"
BOT_TOKEN     = "8291963800:AAErU7MDzn-hPrL_1D69TDgMdp949XrzeOY"
ADMIN_ID      = "7578254597"
GROUP_CHAT_ID = "-1003656538385"
POLL_INTERVAL = 30
# ══════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = "https://www.ivasms.com"
SMS_URL  = f"{BASE_URL}/portal/live/my_sms"


# ──────────────────────────────────────────────
#  EXTRACT OTP CODE FROM MESSAGE TEXT
# ──────────────────────────────────────────────
def extract_otp(message: str) -> str:
    """Try to extract the numeric OTP code from the message text."""
    # Match 4–8 digit numbers (most OTPs are in this range)
    matches = re.findall(r'\b\d{4,8}\b', message)
    if matches:
        # Return the longest match (most likely the OTP)
        return max(matches, key=len)
    return "N/A"


# ──────────────────────────────────────────────
#  iVAS SMS CLIENT
# ──────────────────────────────────────────────
class IvasSmsClient:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        self.logged_in = False

    def _get_csrf(self, html: str):
        soup = BeautifulSoup(html, "html.parser")
        for name in ["_token", "csrf_token", "csrfmiddlewaretoken"]:
            tag = soup.find("input", {"name": name})
            if tag and tag.get("value"):
                return tag.get("value")
        meta = soup.find("meta", {"name": "csrf-token"})
        if meta and meta.get("content"):
            return meta.get("content")
        return None

    def login(self) -> bool:
        try:
            log.info("Loading login page...")
            resp = self.scraper.get(f"{BASE_URL}/login", timeout=30)
            resp.raise_for_status()

            csrf = self._get_csrf(resp.text)
            log.info("CSRF token: %s", "found" if csrf else "not found")

            payload = {"email": IVAS_EMAIL, "password": IVAS_PASSWORD}
            if csrf:
                payload["_token"] = csrf

            log.info("Submitting login form...")
            login_resp = self.scraper.post(
                f"{BASE_URL}/login",
                data=payload,
                headers={"Referer": f"{BASE_URL}/login"},
                timeout=30,
                allow_redirects=True,
            )

            body_lower = login_resp.text.lower()

            if any(w in body_lower for w in ["invalid", "incorrect", "wrong", "credentials", "these credentials"]):
                log.error("Login failed: wrong credentials.")
                self.logged_in = False
                return False

            if "/login" not in login_resp.url:
                log.info("Login successful! Landed on: %s", login_resp.url)
                self.logged_in = True
                return True

            log.warning("Still on /login but no error found. Proceeding cautiously.")
            self.logged_in = True
            return True

        except Exception as e:
            log.error("Login exception: %s", e)
            self.logged_in = False
            return False

    def check_sms_page(self) -> bool:
        try:
            resp = self.scraper.get(SMS_URL, timeout=30)
            if resp.status_code == 200 and "/login" not in resp.url:
                log.info("SMS page accessible.")
                return True
            log.warning("SMS page not accessible. Status: %s, URL: %s", resp.status_code, resp.url)
            return False
        except Exception as e:
            log.error("SMS page check error: %s", e)
            return False

    def get_otp_messages(self) -> list:
        if not self.logged_in:
            log.warning("Not logged in — re-logging in...")
            if not self.login():
                return []

        try:
            resp = self.scraper.get(SMS_URL, timeout=30)

            if resp.status_code in (401, 403) or "/login" in resp.url:
                log.warning("Session expired — re-logging in...")
                self.logged_in = False
                if not self.login():
                    return []
                resp = self.scraper.get(SMS_URL, timeout=30)

            if resp.status_code != 200:
                log.error("SMS page returned status %s", resp.status_code)
                return []

            return self._parse_html(resp.text)

        except Exception as e:
            log.error("OTP fetch error: %s", e)
            return []

    def _parse_html(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        messages = []

        tables = soup.find_all("table")
        log.info("Found %d table(s) on SMS page.", len(tables))

        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 2 and cols[1]:
                    messages.append({
                        "phone_number": cols[0] if len(cols) > 0 else "",
                        "otp_message":  cols[1] if len(cols) > 1 else "",
                        "range":        cols[2] if len(cols) > 2 else "",
                        "date":         cols[3] if len(cols) > 3 else "",
                    })

        log.info("Parsed %d OTP(s) from SMS page.", len(messages))
        return messages


# ──────────────────────────────────────────────
#  TELEGRAM BOT
# ──────────────────────────────────────────────
class OtpForwarderBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.ivas = IvasSmsClient()
        self.seen = set()

    async def send_to_admin(self, text: str):
        try:
            await self.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
        except TelegramError as e:
            log.error("Admin message error: %s", e)

    async def send_to_group(self, text: str):
        try:
            await self.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode="Markdown")
        except TelegramError as e:
            log.error("Group message error: %s", e)

    def _fingerprint(self, msg: dict) -> str:
        return f"{msg.get('phone_number', '')}|{msg.get('otp_message', '')}"

    def _format_otp(self, msg: dict) -> str:
        message = msg.get("otp_message", "N/A")
        otp     = extract_otp(message)
        return (
            "🆕 *NEW OTP DETECTED*\n"
            "==================\n"
            "OTP received 📩\n\n"
            f"*Message:* `{message}`\n\n"
            f"*OTP:* `{otp}`"
        )

    async def send_startup_status(self, ivas_ok: bool, sms_ok: bool):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            "🤖 *iVAS OTP Bot — Startup Report*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔐 *iVAS SMS Status:* {'✅' if ivas_ok else '❌'}\n"
            f"📨 *SMS Page Status:* {'✅' if sms_ok else '❌'}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 *Time:* `{now}`"
        )
        await self.send_to_admin(msg)

    async def check_and_forward(self):
        messages = self.ivas.get_otp_messages()
        new = 0
        for msg in messages:
            fp = self._fingerprint(msg)
            if fp not in self.seen and msg.get("otp_message"):
                self.seen.add(fp)
                await self.send_to_group(self._format_otp(msg))
                new += 1
                await asyncio.sleep(0.5)
        if new:
            log.info("Forwarded %d new OTP(s) to group.", new)
        else:
            log.info("No new OTPs this cycle.")

    async def run(self):
        log.info("Starting iVAS SMS OTP Bot...")

        ivas_ok = self.ivas.login()
        sms_ok  = self.ivas.check_sms_page() if ivas_ok else False

        await self.send_startup_status(ivas_ok, sms_ok)

        if not ivas_ok:
            log.error("Login failed — bot stopped. Admin notified.")
            await self.send_to_admin(
                "🚫 *Bot has stopped.*\n"
                "Login to iVAS SMS failed\\.\n"
                "Please check your email and password\\."
            )
            return

        log.info("Bot running — polling every %ds.", POLL_INTERVAL)

        while True:
            try:
                await self.check_and_forward()
            except Exception as e:
                log.error("Unexpected error: %s", e)
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(OtpForwarderBot().run())
