"""
QwenCloud Auto Signup - Windows Version
- No proxy
- Sequential (1 akun per waktu)
- Simpan ke api_keys.txt + Turso DB
- Compatible Windows (no SIGALRM, no fcntl)

Requirements:
    pip install cloakbrowser playwright requests python-dotenv libsql-client
    playwright install chromium
"""
import os, re, time, random, requests, shutil
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PINKGREEN_API_KEY = os.getenv("PINKGREEN_API_KEY", "mk_-jzruhSjJxxtVCJKbs81dx_OtvMaPJ2V")
PINKGREEN_BASE    = os.getenv("PINKGREEN_BASE_URL", "https://pinkgreen.me")
PINKGREEN_DOMAIN  = os.getenv("PINKGREEN_DOMAIN", "ascentia.site")
PINKGREEN_HEADERS = {"X-API-Key": PINKGREEN_API_KEY, "Content-Type": "application/json"}

TURSO_URL     = os.getenv("TURSO_URL")
TURSO_TOKEN   = os.getenv("TURSO_TOKEN")
TURSO_HEADERS = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

TOTAL_ACCOUNTS = int(os.getenv("TOTAL_ACCOUNTS", "1000"))
HEADLESS       = os.getenv("HEADLESS", "true").lower() == "true"
DEBUG_DIR      = os.getenv("DEBUG_DIR", "./debug")
KEYS_FILE      = "api_keys.txt"
os.makedirs(DEBUG_DIR, exist_ok=True)

# ── Debug helpers ─────────────────────────────────────────────────────────────
def debug_dump(page, tag, run_idx=None, email=None):
    ts = time.strftime("%Y%m%d_%H%M%S")
    prefix = f"{ts}"
    if run_idx is not None:
        prefix += f"_run{run_idx}"
    if email:
        prefix += f"_{email.split('@')[0]}"
    prefix += f"_{tag}"
    base = os.path.join(DEBUG_DIR, prefix)
    info = {"url": None, "title": None}
    try:
        info["url"] = page.url
    except Exception:
        pass
    try:
        info["title"] = page.title()
    except Exception:
        pass
    try:
        page.screenshot(path=f"{base}.png", full_page=True)
    except Exception as e:
        print(f"[DEBUG] screenshot fail: {e}")
    try:
        html = page.content()
        with open(f"{base}.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"[DEBUG] html dump fail: {e}")
    print(f"[DEBUG] tag={tag} url={info['url']} title={info['title']!r} -> {base}.{{png,html}}")
    return info

# ── Turso DB ──────────────────────────────────────────────────────────────────
def turso_execute(sql, args=None):
    if not TURSO_URL or not TURSO_TOKEN:
        return None
    stmt = {"sql": sql}
    if args:
        stmt["args"] = [{"type": "text", "value": str(a)} for a in args]
    try:
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
            print(f"[DB] Error: {result['error']}")
            return None
        return result["response"]["result"]
    except Exception as e:
        print(f"[DB] turso_execute fail: {e}")
        return None

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
    name = f"user{int(time.time())}{random.randint(10000,99999)}"
    try:
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
        print(f"[EMAIL] Gagal: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
    return None, None

def wait_otp(email_id, max_wait=90):
    start = time.time()
    skip = ["333333","666666","600000","000000","ffffff","189554",
            "115455","925380","000342","000425","000406","000207",
            "000422","000490","000404","000312"]
    attempt = 0
    seen_ids = set()
    while time.time() - start < max_wait:
        attempt += 1
        elapsed = int(time.time() - start)
        print(f"[OTP] Polling... attempt {attempt} ({elapsed}s)", end="\r")
        try:
            r = requests.get(f"{PINKGREEN_BASE}/api/emails/{email_id}",
                             headers=PINKGREEN_HEADERS, timeout=10)
            msgs = r.json().get("messages", [])
            for m in msgs:
                mid = m.get("id")
                if mid in seen_ids:
                    continue
                subj = m.get("subject", "").lower()
                if "verify" in subj or "verification" in subj or "code" in subj or "alibaba" in subj:
                    seen_ids.add(mid)
                    mr = requests.get(f"{PINKGREEN_BASE}/api/emails/{email_id}/{mid}",
                                      headers=PINKGREEN_HEADERS, timeout=10)
                    html = mr.json()["message"].get("html", "")
                    for candidate in re.findall(r">(\d{6})<", html):
                        if candidate not in skip:
                            print(f"\n[OTP] {candidate}")
                            return candidate
                else:
                    seen_ids.add(mid)
        except Exception as e:
            print(f"\n[OTP] Error polling: {e}")
        time.sleep(4)
    print(f"\n[OTP] Timeout setelah {max_wait}s")
    return None

def cleanup_email(email_id):
    try:
        requests.delete(f"{PINKGREEN_BASE}/api/emails/{email_id}",
                        headers=PINKGREEN_HEADERS, timeout=10)
    except:
        pass

# ── Browser Automation ────────────────────────────────────────────────────────
def human_sleep(a=0.3, b=0.8):
    time.sleep(random.uniform(a, b))

def run_signup(email_addr, email_id, profile_dir, run_idx=None):
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

        # Langsung goto tanpa proxy
        print("[GOTO] Buka qwencloud.com/api-keys ...")
        try:
            page.goto("https://home.qwencloud.com/api-keys", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            print(f"[GOTO] networkidle timeout (lanjut): {e.__class__.__name__}")
        human_sleep(1, 2)

        # Klik Sign Up atau navigate ke register
        signup_link = page.locator('a:has-text("Sign Up")')
        if signup_link.count() > 0:
            signup_link.click()
            page.wait_for_load_state("networkidle", timeout=30000)
            human_sleep(1, 2)
        elif "login" in page.url:
            reg_url = page.url.replace("sso/login", "sso/register")
            page.goto(reg_url, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            human_sleep(1, 2)

        print(f"[URL] {page.url[:80]}")

        # Isi email
        page.fill('input[type="email"], input:not([type="hidden"])', email_addr)
        human_sleep(0.5, 1)

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

        # Isi OTP digit per digit
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
        human_sleep(0.5, 1)

        # Validate
        for sel in ['button:has-text("Validate")', 'button:has-text("Verify")']:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=10000)
                break
        human_sleep(3, 5)

        debug_dump(page, "after_otp", run_idx, email_addr)

        # Pilih Indonesia
        try:
            combo = page.locator('input[role="combobox"]').first
            if combo.count() > 0:
                combo.click()
                try:
                    page.wait_for_function(
                        "() => { var el = document.querySelector('input[role=\"combobox\"]'); return el && el.getAttribute('aria-expanded') === 'true'; }",
                        timeout=5000
                    )
                except Exception:
                    combo.click()
                human_sleep(0.3, 0.6)
                try:
                    combo.focus()
                    page.keyboard.type("Indonesia", delay=80)
                    print("[STEP] typing 'Indonesia'")
                except Exception as e:
                    print(f"[STEP] keyboard.type fail: {e.__class__.__name__}")
                human_sleep(0.6, 1.0)

                opt = None
                for osel in ['div[role="option"]:has-text("Indonesia")', '[role="option"]:has-text("Indonesia")', 'li:has-text("Indonesia")']:
                    cand = page.locator(osel)
                    if cand.count() > 0:
                        opt = cand.first
                        break

                if opt is None:
                    listbox = page.locator('[role="listbox"]').first
                    if listbox.count() > 0:
                        for _ in range(20):
                            listbox.evaluate("el => el.scrollBy(0, 300)")
                            human_sleep(0.1, 0.2)
                            cand = page.locator('[role="option"]:has-text("Indonesia")')
                            if cand.count() > 0:
                                opt = cand.first
                                break

                if opt:
                    human_sleep(0.4, 0.7)
                    opt.scroll_into_view_if_needed(timeout=3000)
                    try:
                        opt.click(timeout=3000, force=True)
                    except:
                        opt.dispatch_event("click")
                    try:
                        page.wait_for_function(
                            "() => { var el = document.querySelector('input[role=\"combobox\"]'); return !el || el.getAttribute('aria-expanded') !== 'true'; }",
                            timeout=3000
                        )
                        print("[STEP] Indonesia dipilih")
                    except:
                        page.keyboard.press("Escape")
                else:
                    print("[STEP] option Indonesia tidak ditemukan")
                    debug_dump(page, "country_no_option", run_idx, email_addr)
        except Exception as e:
            print(f"[STEP] pilih Indonesia FAIL: {e.__class__.__name__}: {e}")
        human_sleep(0.5, 1)

        # Centang terms
        try:
            label = page.locator('label.maas-terms-text__checkable')
            if label.count() == 0:
                cb = page.locator('input[type="checkbox"]')
                for i in range(cb.count()):
                    try:
                        cb.nth(i).check(force=True, timeout=3000)
                    except:
                        pass
            else:
                for i in range(label.count()):
                    item = label.nth(i)
                    inp = item.locator('input[type="checkbox"]')
                    try:
                        if inp.count() > 0 and inp.is_checked():
                            continue
                    except:
                        pass
                    # Native click paling reliable
                    page.evaluate(
                        """(idx) => {
                            var lab = document.querySelectorAll('label.maas-terms-text__checkable')[idx];
                            if (!lab) return;
                            var inp = lab.querySelector('input[type="checkbox"]');
                            if (inp) inp.click();
                        }""", i
                    )
                    human_sleep(0.2, 0.4)
            print("[STEP] Terms dicentang")
        except Exception as e:
            print(f"[STEP] centang terms FAIL: {e.__class__.__name__}")
        human_sleep(0.5, 1)

        # Tunggu form ready
        try:
            page.wait_for_function(
                """() => {
                    var checkboxes = document.querySelectorAll('input[type="checkbox"]');
                    var combo = document.querySelector('input[role="combobox"]');
                    return checkboxes.length > 0 && combo !== null;
                }""",
                timeout=10000
            )
        except:
            pass
        human_sleep(0.5, 1)

        # Tunggu Continue enabled
        try:
            page.wait_for_function(
                """() => {
                    var btns = Array.from(document.querySelectorAll('button'));
                    var b = btns.find(x => (x.innerText || '').trim() === 'Continue');
                    return b && !b.disabled;
                }""",
                timeout=15000
            )
            print("[STEP] Continue enabled")
        except Exception as e:
            print(f"[STEP] Continue masih disabled: {e.__class__.__name__}")
            debug_dump(page, "continue_disabled", run_idx, email_addr)

        # Klik Continue
        clicked = False
        for sel in ['button[type="submit"]:has-text("Continue")', 'button:has-text("Continue")', 'button[type="submit"]']:
            loc = page.locator(sel)
            if loc.count() > 0:
                try:
                    if loc.first.get_attribute("disabled") is not None:
                        continue
                    loc.first.click(timeout=10000)
                    clicked = True
                    print(f"[STEP] Continue diklik via {sel}")
                    break
                except Exception as e:
                    print(f"[STEP] Continue klik fail via {sel}: {e.__class__.__name__}")
        if not clicked:
            debug_dump(page, "continue_not_clicked", run_idx, email_addr)
        human_sleep(2, 3)

        debug_dump(page, "after_continue", run_idx, email_addr)

        # Tunggu redirect
        try:
            page.wait_for_function(
                """() => {
                    var u = location.href;
                    return u.includes('home.qwencloud.com') ||
                           u.includes('account.qwencloud.com') ||
                           u.includes('/sso/login.htm');
                }""",
                timeout=20000
            )
        except Exception as e:
            print(f"[STEP] redirect timeout: {e.__class__.__name__}")
            debug_dump(page, "continue_no_redirect", run_idx, email_addr)

        post_url = page.url
        if "/sso/login.htm" in post_url:
            debug_dump(page, "bounced_to_login", run_idx, email_addr)
            raise Exception(f"Session lost, bounced ke login: {post_url[:120]}")
        print(f"[STEP] post-continue URL: {post_url[:80]}")

        # Navigate ke api-keys
        if "home.qwencloud.com" in post_url:
            human_sleep(0.5, 1)
            # Cek Failed page
            try:
                page_text = page.inner_text("body", timeout=5000) or ""
                if "Failed" in page_text and "Go to Home Page" in page_text:
                    raise Exception("home.qwencloud.com returned 'Failed' page")
            except Exception as e:
                if "Failed" in str(e):
                    raise
            if "/api-keys" not in post_url:
                try:
                    page.evaluate("() => { history.pushState({}, '', '/api-keys'); window.dispatchEvent(new PopStateEvent('popstate')); }")
                    human_sleep(1, 2)
                except:
                    page.goto("https://home.qwencloud.com/api-keys", timeout=60000, wait_until="domcontentloaded")
        else:
            for attempt in range(5):
                try:
                    page.goto("https://home.qwencloud.com/api-keys", timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception as e:
                    print(f"[RETRY] goto api-keys attempt {attempt+1}: {e.__class__.__name__}")
                    time.sleep(3)
                    continue
                if "api-keys" in page.url:
                    break
                if "/sso/login" in page.url or "login.htm" in page.url:
                    raise Exception(f"Session expired: {page.url[:120]}")
                time.sleep(3)

        human_sleep(1, 2)

        if "api-keys" not in page.url:
            raise Exception(f"Gagal navigate ke api-keys: {page.url[:80]}")

        # Tunggu loading spinner hilang
        print("[STEP] Tunggu page selesai load...")
        try:
            page.wait_for_function(
                """() => {
                    var loadingText = Array.from(document.querySelectorAll('*')).find(
                        el => el.children.length === 0 && (el.textContent || '').trim() === 'Loading...'
                    );
                    return !loadingText;
                }""",
                timeout=30000
            )
            print("[STEP] Loading selesai")
        except Exception as e:
            print(f"[STEP] Loading wait timeout: {e.__class__.__name__}")

        # Tunggu Add API key button
        try:
            page.wait_for_selector('button:has-text("Add API key")', timeout=60000)
        except Exception as e1:
            print(f"[STEP] Add API key tidak muncul (try-1): {e1.__class__.__name__}")
            debug_dump(page, "add_api_key_missing_try1", run_idx, email_addr)

            if "/sso/login" in page.url or "login.htm" in page.url:
                raise Exception(f"Session lost: {page.url[:120]}")

            page.reload()
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except:
                pass
            human_sleep(2, 3)

            if "/sso/login" in page.url or "login.htm" in page.url:
                raise Exception(f"Session lost setelah reload: {page.url[:120]}")

            try:
                page.wait_for_selector('button:has-text("Add API key")', timeout=60000)
            except Exception as e2:
                print(f"[STEP] Add API key tidak muncul (try-2): {e2.__class__.__name__}")
                debug_dump(page, "add_api_key_missing_try2", run_idx, email_addr)
                raise

        # Klik Add API key
        add_btn = page.locator('button:has-text("Add API key")').first
        try:
            add_btn.scroll_into_view_if_needed(timeout=5000)
            add_btn.click(force=True, timeout=10000)
        except:
            page.evaluate('document.querySelectorAll("button").forEach(b => { if(b.innerText.includes("Add API key")) b.click(); })')
        human_sleep(0.5, 1)

        # Isi description
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
        human_sleep(0.5, 1)

        # Generate Key - force click + fallback
        gen_key_btn = page.locator('button:has-text("Generate Key")')
        try:
            gen_key_btn.click(force=True, timeout=10000)
        except Exception as e:
            print(f"[STEP] Generate Key click fail: {e.__class__.__name__}, coba dismiss overlay")
            try:
                page.keyboard.press("Escape")
                human_sleep(0.3, 0.5)
            except:
                pass
            try:
                gen_key_btn.click(force=True, timeout=10000)
            except:
                page.evaluate('document.querySelectorAll("button").forEach(b => { if(b.innerText.includes("Generate Key")) b.click(); })')
        human_sleep(2, 3)

        # Ambil API Key
        api_key_input = page.locator('input[value^="sk-"]')
        api_key = api_key_input.input_value(timeout=30000)

        ctx.close()
        return api_key

    except Exception as e:
        print(f"[ERROR] Browser: {e}")
        try:
            if ctx is not None:
                pages = ctx.pages
                if pages:
                    debug_dump(pages[0], "top_level_exception", run_idx, email_addr)
        except:
            pass
        try:
            if ctx is not None:
                ctx.close()
        except:
            pass
        return None

# ── Main Loop ─────────────────────────────────────────────────────────────────
def count_keys():
    if not os.path.exists(KEYS_FILE):
        return 0
    n = 0
    with open(KEYS_FILE) as f:
        for line in f:
            if line.strip() and "|" in line:
                n += 1
    return n

def main():
    print("=" * 50)
    print(f"QWENCLOUD SIGNUP - WINDOWS VERSION")
    print(f"Target  : {TOTAL_ACCOUNTS} akun")
    print(f"Headless: {HEADLESS}")
    print(f"No proxy: direct connection")
    print("=" * 50)

    db_init()

    success = 0
    failed = 0
    run_idx = 0

    while True:
        existing = count_keys()
        if existing >= TOTAL_ACCOUNTS:
            print(f"\n[DONE] Target {TOTAL_ACCOUNTS} tercapai (existing={existing})")
            break

        run_idx += 1
        print(f"\n{'='*50}")
        print(f"[RUN {run_idx}] existing={existing} success={success} failed={failed}")
        print(f"{'='*50}")

        email_id = None
        profile_dir = f"./profiles/win_{int(time.time())}_{random.randint(1000,9999)}"

        try:
            email_id, email_addr = make_email()
            if not email_id:
                print(f"[SKIP] gagal buat email")
                failed += 1
                time.sleep(5)
                continue

            api_key = run_signup(email_addr, email_id, profile_dir, run_idx=run_idx)

            if api_key:
                db_save(email_addr, api_key)
                with open(KEYS_FILE, "a") as f:
                    f.write(f"{email_addr}|{api_key}\n")
                print(f"\n[SUCCESS] {email_addr} | {api_key}")
                success += 1
                delay = random.uniform(8, 15)
            else:
                print(f"[FAIL] tidak dapat API key")
                failed += 1
                delay = random.uniform(10, 20)

        except Exception as e:
            import traceback
            print(f"[ERROR] {e}")
            traceback.print_exc()
            failed += 1
            delay = random.uniform(15, 30)

        finally:
            if email_id:
                cleanup_email(email_id)
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)

        print(f"[STATS] Success: {success} | Failed: {failed} | Keys: {count_keys()}")
        print(f"[WAIT] {delay:.1f}s sebelum run berikutnya...")
        time.sleep(delay)

    print(f"\n{'='*50}")
    print(f"SELESAI! Success: {success} | Failed: {failed} | Total keys: {count_keys()}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
