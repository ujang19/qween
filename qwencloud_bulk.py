"""
QwenCloud Auto Signup - CloakBrowser + Pinkgreen Email + Turso DB
Buat 1000 akun otomatis, simpan ke Turso libsql
"""
import os, re, time, random, requests, shutil, signal
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PINKGREEN_API_KEY = os.getenv("PINKGREEN_API_KEY")
PINKGREEN_BASE    = os.getenv("PINKGREEN_BASE_URL", "https://pinkgreen.me")
PINKGREEN_DOMAIN  = os.getenv("PINKGREEN_DOMAIN", "pinkgreen.me")
PINKGREEN_HEADERS = {"X-API-Key": PINKGREEN_API_KEY, "Content-Type": "application/json"}

TURSO_URL     = os.getenv("TURSO_URL")
TURSO_TOKEN   = os.getenv("TURSO_TOKEN")
TURSO_HEADERS = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

TOTAL_ACCOUNTS = int(os.getenv("TOTAL_ACCOUNTS", "1000"))
HEADLESS       = os.getenv("HEADLESS", "true").lower() == "true"
DEBUG_DIR      = os.getenv("DEBUG_DIR", "./debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

# ── Debug helpers ─────────────────────────────────────────────────────────────
def debug_dump(page, tag, run_idx=None, email=None):
    """Snapshot page state: screenshot + URL + HTML head, dipanggil saat fail/branch tak terduga."""
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

def step(label, fn, page, run_idx=None, email=None, fatal=True):
    """Wrap a step. Log start/end, dump on exception. Re-raise jika fatal."""
    print(f"[STEP] {label} ...")
    try:
        res = fn()
        print(f"[STEP] {label} OK")
        return res
    except Exception as e:
        print(f"[STEP] {label} FAIL: {e.__class__.__name__}: {e}")
        try:
            debug_dump(page, f"step_fail_{label}", run_idx, email)
        except Exception:
            pass
        if fatal:
            raise
        return None

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

def wait_otp(email_id, max_wait=60):
    start = time.time()
    skip = ["333333","666666","600000","000000","ffffff","189554",
            "115455","925380","000342","000425","000406","000207",
            "000422","000490","000404","000312"]
    attempt = 0
    while time.time() - start < max_wait:
        attempt += 1
        elapsed = int(time.time() - start)
        print(f"[OTP] Polling... attempt {attempt} ({elapsed}s)", end="\r")
        try:
            r = requests.get(f"{PINKGREEN_BASE}/api/emails/{email_id}",
                             headers=PINKGREEN_HEADERS, timeout=10)
            msgs = r.json().get("messages", [])
            for m in msgs:
                subj = m.get("subject", "").lower()
                if "verify" in subj or "verification" in subj or "code" in subj or "alibaba" in subj:
                    mr = requests.get(f"{PINKGREEN_BASE}/api/emails/{email_id}/{m['id']}",
                                      headers=PINKGREEN_HEADERS, timeout=10)
                    html = mr.json()["message"].get("html", "")
                    for candidate in re.findall(r">(\d{6})<", html):
                        if candidate not in skip:
                            print(f"\n[OTP] {candidate}")
                            return candidate
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

# Proxy rotation buat bypass captcha
PROXY_FILE = os.getenv("PROXY_FILE", "proxy.txt")
_proxy_state_file = ".proxy_idx"
_proxy_cache = None

def _load_proxies():
    global _proxy_cache
    if _proxy_cache is not None:
        return _proxy_cache
    proxies = []
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
    _proxy_cache = proxies
    return proxies

def _next_proxy():
    """Round-robin pick proxy dari proxy.txt, persisted ke .proxy_idx.
    Pakai fcntl.flock supaya aman dipakai oleh multiple process bersamaan
    (run_persistent + run_parallel + workers child)."""
    proxies = _load_proxies()
    if not proxies:
        return None
    import fcntl
    # Buka rw, buat kalau belum ada
    fd = os.open(_proxy_state_file, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.lseek(fd, 0, 0)
        raw = os.read(fd, 32).decode().strip() or "0"
        try:
            idx = int(raw) % len(proxies)
        except Exception:
            idx = 0
        chosen = proxies[idx]
        next_idx = (idx + 1) % len(proxies)
        os.lseek(fd, 0, 0)
        os.ftruncate(fd, 0)
        os.write(fd, str(next_idx).encode())
        return chosen
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(fd)

def bypass_captcha():
    """Bypass captcha Alibaba via requests + proxy rotated dari proxy.txt, return login URL + cookies."""
    proxy_str = _next_proxy()
    if proxy_str is None:
        # fallback hardcoded kalau proxy.txt kosong
        proxy_str = 'a810789af3288983f034__cr.gb,us,sg,au:995f6c9c7606ffde@gw.dataimpulse.com:10000'
    proxy = f'http://{proxy_str}'
    print(f"[BYPASS] proxy={proxy_str.split('@')[-1]}")
    proxies = {'http': proxy, 'https': proxy}
    session = requests.Session()
    session.proxies = proxies
    r = session.get('https://home.qwencloud.com/api-keys', timeout=30)
    cookies = []
    for c in session.cookies:
        cookies.append({
            'name': c.name,
            'value': c.value,
            'domain': c.domain or '.alibabacloud.com',
            'path': c.path or '/'
        })
    return r.url, cookies

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

        # Bypass captcha tepat sebelum goto (URL ada expireTime)
        print("[BYPASS] Bypass captcha...")
        login_url, cookies = bypass_captcha()
        print(f"[BYPASS] OK -> {login_url[:60]}")

        # Inject cookies dan goto login URL langsung
        ctx.add_cookies(cookies)
        for attempt in range(3):
            try:
                page.goto(login_url, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=30000)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"[RETRY] goto login gagal, bypass ulang...")
                login_url, cookies = bypass_captcha()
                ctx.add_cookies(cookies)
                time.sleep(3)
        page.wait_for_load_state("networkidle")
        human_sleep(1, 2)

        # Klik Sign Up atau langsung ke register
        signup_link = page.locator('a:has-text("Sign Up")')
        if signup_link.count() > 0:
            signup_link.click()
            page.wait_for_load_state("networkidle")
            human_sleep(1, 2)
        elif "login" in page.url:
            reg_url = page.url.replace("sso/login", "sso/register")
            page.goto(reg_url, timeout=60000)
            page.wait_for_load_state("networkidle")
            human_sleep(1, 2)

        # Isi email
        page.fill('input[type="email"], input:not([type="hidden"])', email_addr)
        human_sleep(0.5, 1)

        # Klik Next
        page.click('button:has-text("Next")', timeout=10000)
        print("[WAIT] Menunggu OTP 12 detik...")
        time.sleep(12)

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

        human_sleep(0.5, 1)

        # Validate
        for sel in ['button:has-text("Validate")', 'button:has-text("Verify")']:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=10000)
                break
        human_sleep(3, 5)

        # Snapshot setelah OTP, sebelum form Indonesia
        debug_dump(page, "after_otp", run_idx, email_addr)

        # Pilih Indonesia (input readonly -> harus klik combobox lalu klik option)
        country_ok = False
        try:
            combo = page.locator('input[role="combobox"]').first
            if combo.count() == 0:
                print("[STEP] country combobox NOT FOUND")
                debug_dump(page, "no_country_combo", run_idx, email_addr)
            else:
                # Buka dropdown
                combo.click()
                # Tunggu aria-expanded jadi true
                try:
                    page.wait_for_function(
                        "() => { var el = document.querySelector('input[role=\"combobox\"]'); return el && el.getAttribute('aria-expanded') === 'true'; }",
                        timeout=5000
                    )
                except Exception as ex:
                    print(f"[STEP] dropdown tidak terbuka via klik pertama: {ex.__class__.__name__}, retry click")
                    combo.click()
                    page.wait_for_function(
                        "() => { var el = document.querySelector('input[role=\"combobox\"]'); return el && el.getAttribute('aria-expanded') === 'true'; }",
                        timeout=5000
                    )
                human_sleep(0.3, 0.6)

                # Combobox punya aria-autocomplete="list". Walaupun input readonly,
                # keyboard events di-listen handler untuk filter listbox.
                # Pakai page.keyboard.type (langsung dispatch ke focused element).
                try:
                    combo.focus()
                except Exception:
                    pass
                try:
                    page.keyboard.type("Indonesia", delay=80)
                    print("[STEP] typing 'Indonesia' ke combobox")
                except Exception as te:
                    print(f"[STEP] keyboard.type fail: {te.__class__.__name__}: {te}")
                human_sleep(0.6, 1.0)

                # Strategi: cari option Indonesia langsung di list (tanpa typing, karena input readonly).
                # Selector kandidat: role=option, listbox item, atau li dengan text Indonesia.
                option_selectors = [
                    'div[role="option"]:has-text("Indonesia")',
                    '[role="option"]:has-text("Indonesia")',
                    'li:has-text("Indonesia")',
                    'div:has-text("Indonesia"):not(:has(div))',
                ]
                opt = None
                for osel in option_selectors:
                    cand = page.locator(osel)
                    if cand.count() > 0:
                        opt = cand.first
                        print(f"[STEP] country option ditemukan via selector={osel} (count={cand.count()})")
                        break

                if opt is None:
                    # List besar -> coba scroll listbox cari Indonesia
                    print("[STEP] option Indonesia tidak langsung terlihat, coba scroll listbox")
                    listbox = page.locator('[role="listbox"]').first
                    if listbox.count() > 0:
                        for _ in range(20):
                            listbox.evaluate("el => el.scrollBy(0, 300)")
                            human_sleep(0.1, 0.2)
                            cand = page.locator('[role="option"]:has-text("Indonesia")')
                            if cand.count() > 0:
                                opt = cand.first
                                break

                if opt is None:
                    debug_dump(page, "country_no_option", run_idx, email_addr)
                    raise Exception("option Indonesia tidak ditemukan di dropdown")

                # Tunggu animasi dropdown reda sebelum klik option
                human_sleep(0.4, 0.7)
                opt.scroll_into_view_if_needed(timeout=3000)
                # Pakai force=True untuk skip stability check (dropdown sering animated)
                clicked = False
                try:
                    opt.click(timeout=3000, force=True)
                    clicked = True
                except Exception as ce:
                    print(f"[STEP] option.click(force) fail: {ce.__class__.__name__}: {ce}, fallback dispatch_event")
                if not clicked:
                    try:
                        opt.dispatch_event("click")
                        clicked = True
                    except Exception as ce:
                        print(f"[STEP] option.dispatch_event fail: {ce.__class__.__name__}: {ce}")
                if not clicked:
                    debug_dump(page, "country_click_fail", run_idx, email_addr)
                    raise Exception("klik option Indonesia fail di semua strategi")

                # Sumber kebenaran: dropdown ketutup setelah klik (aria-expanded=false).
                # Jangan strict-check input.value karena UI ini sering nampilkan country di elemen lain.
                try:
                    page.wait_for_function(
                        "() => { var el = document.querySelector('input[role=\"combobox\"]'); return !el || el.getAttribute('aria-expanded') !== 'true'; }",
                        timeout=3000
                    )
                    country_ok = True
                    print("[STEP] country option dipilih (dropdown closed)")
                except Exception:
                    print("[STEP] dropdown masih open setelah klik option, paksa tutup via Escape + klik body")
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    try:
                        page.locator("body").click(position={"x": 5, "y": 5}, timeout=2000)
                    except Exception:
                        pass
                    human_sleep(0.3, 0.5)

                # Log kondisi UI buat info (tidak fatal)
                try:
                    info = page.evaluate(
                        """() => {
                            var el = document.querySelector('input[role=\"combobox\"]');
                            return {
                                value: el ? (el.value || '') : null,
                                expanded: el ? el.getAttribute('aria-expanded') : null,
                                placeholder: el ? el.getAttribute('placeholder') : null
                            };
                        }"""
                    )
                    print(f"[STEP] combobox state: {info}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[STEP] pilih Indonesia FAIL: {e.__class__.__name__}: {e}")
            debug_dump(page, "country_fail", run_idx, email_addr)
        human_sleep(0.5, 1)

        # Centang terms (input checkbox di-hide via CSS, klik label-nya)
        # Kalau ada overlay/dropdown nutupin -> fallback dispatch_event lalu JS native setter.
        try:
            label = page.locator('label.maas-terms-text__checkable')
            if label.count() == 0:
                # fallback ke input langsung
                cb = page.locator('input[type="checkbox"]')
                n = cb.count()
                print(f"[STEP] tidak ada label.maas-terms-text__checkable, fallback ke input checkbox (count={n})")
                for i in range(n):
                    try:
                        cb.nth(i).check(force=True, timeout=3000)
                    except Exception as ce:
                        print(f"[STEP] checkbox[{i}] check fail: {ce.__class__.__name__}")
            else:
                n = label.count()
                checked_any = False
                for i in range(n):
                    item = label.nth(i)
                    inp = item.locator('input[type="checkbox"]')
                    try:
                        already = inp.is_checked() if inp.count() > 0 else False
                    except Exception:
                        already = False
                    if already:
                        continue
                    # Strategi berlapis. Prioritas: HTMLInputElement.click() langsung di input
                    # (paling reliable, browser otomatis toggle checked + fire click+change yang React listen).
                    ok = False
                    for strat in ("input_native_click", "label_click", "label_click_force", "label_dispatch", "js_native_setter"):
                        try:
                            if strat == "input_native_click":
                                page.evaluate(
                                    """(idx) => {
                                        var labels = document.querySelectorAll('label.maas-terms-text__checkable');
                                        var lab = labels[idx];
                                        if (!lab) return false;
                                        var inp = lab.querySelector('input[type=\"checkbox\"]');
                                        if (!inp) return false;
                                        inp.click();
                                        return inp.checked === true;
                                    }""",
                                    i,
                                )
                            elif strat == "label_click":
                                item.click(timeout=2000)
                            elif strat == "label_click_force":
                                item.click(timeout=2000, force=True)
                            elif strat == "label_dispatch":
                                item.dispatch_event("click")
                            elif strat == "js_native_setter":
                                page.evaluate(
                                    """(idx) => {
                                        var labels = document.querySelectorAll('label.maas-terms-text__checkable');
                                        var lab = labels[idx];
                                        if (!lab) return false;
                                        var inp = lab.querySelector('input[type=\"checkbox\"]');
                                        if (!inp) return false;
                                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked').set;
                                        setter.call(inp, true);
                                        inp.dispatchEvent(new Event('input', {bubbles:true}));
                                        inp.dispatchEvent(new Event('change', {bubbles:true}));
                                        inp.dispatchEvent(new Event('click', {bubbles:true}));
                                        return inp.checked === true;
                                    }""",
                                    i,
                                )
                            # Verifikasi tercentang
                            try:
                                checked_now = inp.is_checked()
                            except Exception:
                                checked_now = page.evaluate(
                                    "(idx) => { var l = document.querySelectorAll('label.maas-terms-text__checkable')[idx]; var c = l && l.querySelector('input[type=\"checkbox\"]'); return !!(c && c.checked); }",
                                    i,
                                )
                            if checked_now:
                                ok = True
                                checked_any = True
                                print(f"[STEP] terms label[{i}] tercentang via {strat}")
                                break
                            else:
                                print(f"[STEP] terms label[{i}] strategi={strat} tidak tercentang, lanjut")
                        except Exception as ce:
                            print(f"[STEP] terms label[{i}] strategi={strat} fail: {ce.__class__.__name__}: {ce}")
                    if not ok:
                        debug_dump(page, f"checkbox_label_{i}_fail", run_idx, email_addr)
                # Verifikasi: semua checkbox tercentang
                try:
                    all_checked = page.evaluate(
                        "() => Array.from(document.querySelectorAll('input.maas-terms-text__checkbox, input[type=\"checkbox\"]')).every(c => c.checked)"
                    )
                except Exception:
                    all_checked = None
                print(f"[STEP] terms label count={n} checked_any={checked_any} all_checked={all_checked}")
        except Exception as e:
            print(f"[STEP] centang terms FAIL: {e.__class__.__name__}: {e}")
            debug_dump(page, "checkbox_fail", run_idx, email_addr)
        human_sleep(0.5, 1)

        # Deteksi slider captcha (baxia-wrapper)
        try:
            baxia_iframe = page.locator('#baxia-wrapper iframe')
            if baxia_iframe.count() > 0:
                print("[STEP] Slider captcha (baxia) terdeteksi -> dump, lanjut tunggu Continue enabled")
                debug_dump(page, "baxia_slider_present", run_idx, email_addr)
        except Exception:
            pass

        # Continue: tunggu sampai tombol enabled, baru klik
        clicked_continue = False
        continue_btn = page.locator('button[type="submit"]:has-text("Continue")').first
        if continue_btn.count() == 0:
            continue_btn = page.locator('button:has-text("Continue")').first
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
            print(f"[STEP] Continue tetap disabled setelah 15s: {e.__class__.__name__}")
            # Post-mortem state: kenapa Continue masih disabled?
            try:
                state = page.evaluate(
                    """() => {
                        var combo = document.querySelector('input[role=\"combobox\"]');
                        var checkboxes = Array.from(document.querySelectorAll('input[type=\"checkbox\"]'));
                        var btns = Array.from(document.querySelectorAll('button'));
                        var cont = btns.find(b => (b.innerText || '').trim() === 'Continue');
                        var baxia = document.querySelector('#baxia-wrapper');
                        return {
                            combo_value: combo ? (combo.value || '') : null,
                            combo_expanded: combo ? combo.getAttribute('aria-expanded') : null,
                            combo_placeholder: combo ? combo.getAttribute('placeholder') : null,
                            checkbox_count: checkboxes.length,
                            checkbox_checked: checkboxes.map(c => c.checked),
                            continue_disabled: cont ? cont.disabled : null,
                            continue_aria_disabled: cont ? cont.getAttribute('aria-disabled') : null,
                            baxia_has_iframe: baxia ? !!baxia.querySelector('iframe') : false,
                            error_text: (document.querySelector('.error-text')?.innerText || '').trim()
                        };
                    }"""
                )
                print(f"[POSTMORTEM] continue_disabled state: {state}")
            except Exception as pe:
                print(f"[POSTMORTEM] gagal ambil state: {pe.__class__.__name__}: {pe}")
            debug_dump(page, "continue_still_disabled", run_idx, email_addr)

        for sel in ['button[type="submit"]:has-text("Continue")', 'button:has-text("Continue")', 'button:has-text("Submit")', 'button[type="submit"]']:
            loc = page.locator(sel)
            if loc.count() > 0:
                try:
                    # cek disabled state dari attribute
                    is_disabled = loc.first.get_attribute("disabled") is not None
                    if is_disabled:
                        print(f"[STEP] selector={sel} masih disabled, skip")
                        continue
                    loc.first.click(timeout=10000)
                    clicked_continue = True
                    print(f"[STEP] continue klik via selector={sel}")
                    break
                except Exception as e:
                    print(f"[STEP] continue klik FAIL via {sel}: {e.__class__.__name__}: {e}")
        if not clicked_continue:
            print("[STEP] tidak ada tombol Continue/Submit yang bisa diklik")
            debug_dump(page, "continue_not_clicked", run_idx, email_addr)
        human_sleep(2, 3)

        # Snapshot setelah Continue, sebelum goto api-keys
        debug_dump(page, "after_continue", run_idx, email_addr)

        # Tunggu redirect setelah Continue. Sukses kalau URL pindah ke home.qwencloud.com.
        # Kalau redirect ke sso/login.htm = session lost (race condition), bail out cepat.
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
            print(f"[STEP] redirect setelah Continue timeout: {e.__class__.__name__}")
            debug_dump(page, "continue_no_redirect", run_idx, email_addr)

        post_url = page.url
        if "/sso/login.htm" in post_url or "Log In" in (page.title() or ""):
            # Akun sudah dibuat di server, tapi browser session tidak forward.
            # Tidak bisa recover di run ini tanpa OTP ulang. Bail out.
            debug_dump(page, "bounced_to_login", run_idx, email_addr)
            raise Exception(f"Continue bounced ke login (session lost): {post_url[:120]}")
        print(f"[STEP] post-continue URL: {post_url[:80]}")

        # Force navigate ke halaman api-keys dengan retry robust
        for attempt in range(5):
            try:
                page.goto("https://home.qwencloud.com/api-keys", timeout=60000, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                print(f"[RETRY] goto api-keys attempt {attempt+1}: {e.__class__.__name__}")
                time.sleep(3)
                continue
            if "api-keys" in page.url and "chrome-error" not in page.url:
                break
            if "/sso/login.htm" in page.url:
                debug_dump(page, f"api_keys_bounce_attempt{attempt+1}", run_idx, email_addr)
                raise Exception(f"goto api-keys bounced ke login (session expired): {page.url[:120]}")
            time.sleep(3)
        human_sleep(1, 2)

        if "api-keys" not in page.url:
            raise Exception(f"Gagal navigate ke api-keys, URL: {page.url[:80]}")

        # Tunggu tombol Add API key muncul (max 20 detik), kalau gagal -> dump + reload + dump lagi
        try:
            page.wait_for_selector('button:has-text("Add API key")', timeout=20000)
        except Exception as e1:
            print(f"[STEP] Add API key tidak muncul (try-1): {e1.__class__.__name__}")
            debug_dump(page, "add_api_key_missing_try1", run_idx, email_addr)
            page.reload()
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as e:
                print(f"[STEP] networkidle setelah reload fail: {e.__class__.__name__}")
            human_sleep(2, 3)
            try:
                page.wait_for_selector('button:has-text("Add API key")', timeout=20000)
            except Exception as e2:
                print(f"[STEP] Add API key tidak muncul (try-2 setelah reload): {e2.__class__.__name__}")
                debug_dump(page, "add_api_key_missing_try2", run_idx, email_addr)
                raise

        add_btn = page.locator('button:has-text("Add API key")').first
        try:
            add_btn.scroll_into_view_if_needed(timeout=5000)
            add_btn.click(force=True, timeout=10000)
        except:
            page.evaluate('document.querySelectorAll("button").forEach(b => { if(b.innerText.includes("Add API key")) b.click(); })')
            human_sleep(0.5, 1)
        human_sleep(0.5, 1)

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
        human_sleep(0.5, 1)

        # Generate Key
        page.click('button:has-text("Generate Key")', timeout=15000)
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
        except Exception as e:
            print(f"[STEP] escape close dialog fail (non-fatal): {e.__class__.__name__}")

        ctx.close()
        return api_key

    except Exception as e:
        print(f"[ERROR] Browser: {e}")
        try:
            if ctx is not None:
                # Best-effort dump dari page pertama yang masih hidup
                try:
                    pages = ctx.pages
                    if pages:
                        debug_dump(pages[0], "top_level_exception", run_idx, email_addr)
                except Exception as de:
                    print(f"[DEBUG] top-level dump fail: {de}")
        except Exception:
            pass
        try:
            if ctx is not None:
                ctx.close()
        except Exception:
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

            # Jalankan signup dengan timeout 3 menit
            def timeout_handler(signum, frame):
                raise TimeoutError("Run timeout 3 menit")
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(180)
            try:
                api_key = run_signup(email_addr, email_id, profile_dir, run_idx=i)
            finally:
                signal.alarm(0)

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
            delay = random.uniform(3, 5)
            print(f"[WAIT] Delay {delay:.1f}s sebelum run berikutnya...")
            time.sleep(delay)

    print(f"\n{'='*50}")
    print(f"SELESAI! Success: {success} | Failed: {failed}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
