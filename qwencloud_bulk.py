"""
QwenCloud Auto Signup - CloakBrowser + Pinkgreen Email + Turso DB
Buat 1000 akun otomatis, simpan ke Turso libsql
"""
import os, re, time, random, requests, shutil
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PINKGREEN_API_KEY = os.getenv("PINKGREEN_API_KEY")
PINKGREEN_BASE    = os.getenv("PINKGREEN_BASE_URL", "https://pinkgreen.me")
PINKGREEN_DOMAIN  = os.getenv("PINKGREEN_DOMAIN", "ascentia.site")
PINKGREEN_HEADERS = {"X-API-Key": PINKGREEN_API_KEY, "Content-Type": "application/json"}

TURSO_URL     = os.getenv("TURSO_URL")
TURSO_TOKEN   = os.getenv("TURSO_TOKEN")
TURSO_HEADERS = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

TOTAL_ACCOUNTS = int(os.getenv("TOTAL_ACCOUNTS", "1000"))
HEADLESS       = os.getenv("HEADLESS", "true").lower() == "true"

# ── Turso DB via HTTP API ─────────────────────────────────────────────────────
def turso_execute(sql, args=None):
    stmt = {"sql": sql}
    if args:
        stmt["named_args"] = []
        stmt["args"] = [{"type": "text", "value": str(a)} for a in args]
    r = requests.post(f"{TURSO_URL}/v2/pipeline", headers=TURSO_HEADERS, json={
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"}
        ]
    }, timeout=30)
    r.raise_for_status()
    results = r.json()["results"]
    result = results[0]
    if result["type"] == "error":
        raise Exception(f"Turso error: {result['error']}")
    return result["response"]["result"]

def db_init():
    turso_execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            api_key TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[DB] Table ready.")

def db_save(email, api_key):
    turso_execute(
        "INSERT INTO accounts (email, api_key) VALUES (?, ?)",
        [email, api_key]
    )
    print(f"[DB] Saved: {email} | {api_key}")

# ── Pinkgreen Email ───────────────────────────────────────────────────────────
def make_email():
    name = f"user{random.randint(100,999)}{int(time.time())%100}"
    r = requests.post(f"{PINKGREEN_BASE}/api/emails/generate",
                      headers=PINKGREEN_HEADERS,
                      json={"name": name, "domain": PINKGREEN_DOMAIN, "expiryTime": 0},
                      timeout=30)
    if r.status_code == 200:
        d = r.json()
        email = d.get("email") or d.get("address")
        eid = d.get("id")
        print(f"[EMAIL] {email}")
        return eid, email
    print(f"[EMAIL] Gagal: {r.status_code}")
    return None, None

def wait_otp(email_id, max_wait=180):
    start = time.time()
    skip = ["333333","666666","600000","000000","ffffff","189554",
            "115455","925380","000342","000425","000406","000207",
            "000422","000490","000404","000312"]
    while time.time() - start < max_wait:
        r = requests.get(f"{PINKGREEN_BASE}/api/emails/{email_id}",
                         headers=PINKGREEN_HEADERS, timeout=30)
        msgs = r.json().get("messages", [])
        for m in msgs:
            subj = m.get("subject", "").lower()
            if "verify" in subj or "verification" in subj or "code" in subj:
                mr = requests.get(f"{PINKGREEN_BASE}/api/emails/{email_id}/{m['id']}",
                                  headers=PINKGREEN_HEADERS, timeout=30)
                html = mr.json()["message"].get("html", "")
                for candidate in re.findall(r">(\d{6})<", html):
                    if candidate not in skip:
                        print(f"[OTP] {candidate}")
                        return candidate
        time.sleep(5)
    return None

def cleanup_email(email_id):
    try:
        requests.delete(f"{PINKGREEN_BASE}/api/emails/{email_id}",
                        headers=PINKGREEN_HEADERS, timeout=10)
    except:
        pass

# ── Browser Automation ────────────────────────────────────────────────────────
def human_sleep(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))

def run_signup(email_addr, email_id, profile_dir):
    from cloakbrowser import launch_persistent_context

    ctx = None
    try:
        ctx = launch_persistent_context(
            profile_dir,
            headless=HEADLESS,
            humanize=True,
            human_preset="careful"
        )
        page = ctx.new_page()

        # Buka API Keys page (redirect ke login)
        new_page_ref = [None]
        def on_new_page(p):
            new_page_ref[0] = p
        ctx.on("page", on_new_page)

        page.goto("https://home.qwencloud.com/api-keys", timeout=60000)
        page.wait_for_load_state("networkidle")
        human_sleep(2, 3)

        if new_page_ref[0]:
            page = new_page_ref[0]
            page.wait_for_load_state("networkidle")
            human_sleep(2, 3)

        # Klik Sign Up
        signup_link = page.locator('a:has-text("Sign Up")')
        if signup_link.count() > 0:
            signup_link.click()
            page.wait_for_load_state("networkidle")
            human_sleep(2, 3)
        else:
            cur = page.url
            reg_url = cur.replace("sso/login", "sso/register")
            page.goto(reg_url, timeout=60000)
            page.wait_for_load_state("networkidle")
            human_sleep(2, 3)

        # Isi email
        page.fill('input[type="email"], input:not([type="hidden"])', email_addr)
        human_sleep(1, 2)

        # Klik Next
        page.click('button:has-text("Next")', timeout=10000)
        print("[WAIT] Menunggu OTP 15 detik...")
        time.sleep(15)

        # Poll OTP
        otp = wait_otp(email_id)
        if not otp:
            print("[FAIL] OTP tidak diterima")
            ctx.close()
            return None

        # Isi OTP
        otp_inputs = page.locator('input:visible').all()
        empty_inputs = []
        for inp in otp_inputs:
            try:
                val = inp.input_value()
                if not val:
                    empty_inputs.append(inp)
            except:
                empty_inputs.append(inp)

        if len(empty_inputs) >= 6:
            empty_inputs[0].click()
            human_sleep(0.3, 0.5)
            for digit in otp[:6]:
                page.keyboard.press(digit)
                human_sleep(0.1, 0.2)

        human_sleep(1, 2)

        # Validate
        for sel in ['button:has-text("Validate")', 'button:has-text("Verify")']:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=10000)
                break
        human_sleep(3, 5)

        # Pilih Indonesia
        try:
            combo = page.locator('input[role="combobox"]')
            combo.click()
            human_sleep(0.5, 1)
            combo.type("Indonesia", delay=80)
            human_sleep(1, 2)
            page.locator('div[role="option"]:has-text("Indonesia")').first.click()
        except:
            pass
        human_sleep(1, 2)

        # Centang terms
        try:
            cb = page.locator('input[type="checkbox"]')
            if cb.count() > 0 and not cb.is_checked():
                cb.check()
        except:
            pass
        human_sleep(1, 2)

        # Continue
        for sel in ['button:has-text("Continue")', 'button[type="submit"]']:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=10000)
                break
        human_sleep(5, 8)
        page.wait_for_load_state("networkidle")

        # Add API Key
        human_sleep(3, 5)
        page.click('button:has-text("Add API key")', timeout=10000)
        human_sleep(1, 2)

        # Isi description via JS
        page.evaluate("""() => {
            var inputs = document.querySelectorAll('input[maxlength="50"]');
            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            for (var i = 0; i < inputs.length; i++) {
                nativeSetter.call(inputs[i], 'auto-key');
                inputs[i].dispatchEvent(new Event('input', {bubbles: true}));
                inputs[i].dispatchEvent(new Event('change', {bubbles: true}));
                break;
            }
        }""")
        human_sleep(1, 2)

        # Generate Key
        page.click('button:has-text("Generate Key")', timeout=10000)
        human_sleep(2, 3)

        # Ambil API Key
        api_key_input = page.locator('input[value^="sk-"]')
        api_key = api_key_input.input_value()

        # Copy via JS
        page.evaluate("""() => {
            var btns = document.querySelectorAll('span[role="button"]');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].title === 'Copy to clipboard') {
                    btns[i].click();
                    break;
                }
            }
        }""")

        # Close dialog
        try:
            page.keyboard.press("Escape")
        except:
            pass

        ctx.close()
        return api_key

    except Exception as e:
        print(f"[ERROR] Browser: {e}")
        try:
            ctx.close()
        except:
            pass
        return None

# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print(f"QWENCLOUD BULK SIGNUP - {TOTAL_ACCOUNTS} accounts")
    print("=" * 50)

    # Init DB
    db_init()

    success = 0
    failed = 0

    for i in range(1, TOTAL_ACCOUNTS + 1):
        print(f"\n{'='*50}")
        print(f"[RUN {i}/{TOTAL_ACCOUNTS}] Starting...")
        print(f"{'='*50}")

        email_id = None
        profile_dir = f"./profiles/run_{int(time.time())}_{random.randint(1000,9999)}"

        try:
            # Buat email
            email_id, email_addr = make_email()
            if not email_id:
                print(f"[RUN {i}] SKIP - gagal buat email")
                failed += 1
                continue

            # Jalankan signup
            api_key = run_signup(email_addr, email_id, profile_dir)

            if api_key:
                # Simpan ke Turso
                db_save(email_addr, api_key)

                # Simpan ke file lokal juga
                with open("api_keys.txt", "a") as f:
                    f.write(f"{email_addr}|{api_key}\n")

                print(f"[RUN {i}] SUCCESS - {email_addr} | {api_key}")
                success += 1
            else:
                print(f"[RUN {i}] FAIL - tidak dapat API key")
                failed += 1

        except Exception as e:
            import traceback
            print(f"[RUN {i}] ERROR - {e}")
            traceback.print_exc()
            failed += 1

        finally:
            # Cleanup email
            if email_id:
                cleanup_email(email_id)

            # Hapus profile browser
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)

            print(f"[STATS] Success: {success} | Failed: {failed} | Total: {i}")

        # Delay antar run
        if i < TOTAL_ACCOUNTS:
            delay = random.uniform(5, 15)
            print(f"[WAIT] Delay {delay:.1f}s sebelum run berikutnya...")
            time.sleep(delay)

    print(f"\n{'='*50}")
    print(f"SELESAI! Success: {success} | Failed: {failed}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
