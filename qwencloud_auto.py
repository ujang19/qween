"""
QwenCloud Auto Signup - CloakBrowser + Pinkgreen Email
"""
import os, re, time, random, requests
from cloakbrowser import launch_persistent_context

# Config
API_KEY = "mk_-jzruhSjJxxtVCJKbs81dx_OtvMaPJ2V"
BASE = "https://pinkgreen.me"
DOMAIN = "ascentia.site"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def human_sleep(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))

def make_email():
    """Buat temp email via Pinkgreen."""
    name = f"user{random.randint(100,999)}{int(time.time())%100}"
    r = requests.post(f"{BASE}/api/emails/generate", headers=HEADERS,
                      json={"name": name, "domain": DOMAIN, "expiryTime": 0}, timeout=30)
    if r.status_code == 200:
        d = r.json()
        email = d.get("email") or d.get("address")
        eid = d.get("id")
        print(f"[EMAIL] {email} (ID: {eid})")
        return eid, email
    print(f"[EMAIL] Gagal: {r.status_code} {r.text[:100]}")
    return None, None

def wait_otp(email_id, max_wait=180):
    """Poll inbox sampai dapat OTP."""
    start = time.time()
    while time.time() - start < max_wait:
        r = requests.get(BASE + "/api/emails/" + email_id, headers=HEADERS, timeout=30)
        msgs = r.json().get("messages", [])
        for m in msgs:
            subj = m.get("subject", "").lower()
            if "verify" in subj or "verification" in subj or "code" in subj:
                mid = m["id"]
                mr = requests.get(BASE + "/api/emails/" + email_id + "/" + mid, headers=HEADERS, timeout=30)
                html = mr.json()["message"].get("html", "")
                skip = ["333333", "666666", "600000", "000000", "ffffff", "189554", "115455", "925380", "000342", "000425", "000406", "000207", "000422", "000490", "000404", "000312"]
                all_matches = re.findall(r">(\d{6})<", html)
                for candidate in all_matches:
                    if candidate not in skip:
                        print("[OTP] Dapat:", candidate)
                        return candidate
        time.sleep(5)
    return None

def cleanup(email_id):
    requests.delete(f"{BASE}/api/emails/{email_id}", headers=HEADERS, timeout=10)
    print("[CLEANUP] Email dihapus.")

def main():
    print("="*50)
    print("QWENCLOUD AUTO SIGNUP")
    print("="*50)

    # 1. Buat email
    print("\n[1] Membuat email temporary...")
    email_id, email_addr = make_email()
    if not email_id:
        print("GAGAL buat email!")
        return

    ctx = None
    page = None
    try:
        # 2. Buka browser
        print("\n[2] Launch CloakBrowser...")
        ctx = launch_persistent_context(
            "./profiles/qwencloud",
            headless=False,
            humanize=True,
            human_preset="careful"
        )
        page = ctx.new_page()

        # 3. Buka langsung ke API Keys page (akan redirect ke login)
        print("\n[3] Buka API Keys page...")
        
        # Handle tab baru yang dibuka oleh Alibaba SSO
        new_page = None
        def on_new_page(p):
            nonlocal new_page
            new_page = p
        ctx.on("page", on_new_page)
        
        page.goto("https://home.qwencloud.com/api-keys", timeout=60000)
        page.wait_for_load_state("networkidle")
        human_sleep(2, 3)
        print(f"  -> URL: {page.url}")
        
        # Kalau ada tab baru, pakai tab baru
        if new_page:
            page = new_page
            page.wait_for_load_state("networkidle")
            human_sleep(2, 3)
            print(f"  -> New tab URL: {page.url}")

        # 4. Klik Sign Up
        print("[4] Klik Sign Up...")
        signup_link = page.locator('a:has-text("Sign Up")')
        if signup_link.count() > 0:
            signup_link.click()
            page.wait_for_load_state("networkidle")
            human_sleep(2, 3)
        else:
            cur = page.url
            reg_url = cur.replace("sso/login", "sso/register")
            print(f"  -> Navigate: {reg_url[:80]}")
            page.goto(reg_url, timeout=60000)
            page.wait_for_load_state("networkidle")
            human_sleep(2, 3)
        print(f"  -> URL signup: {page.url}")

        # 6. Isi email
        print(f"[6] Isi email: {email_addr}...")
        page.fill('input[type="email"], input:not([type="hidden"])', email_addr)
        human_sleep(1, 2)

        # 7. Klik Next
        print("[7] Klik Next (kirim OTP)...")
        page.click('button:has-text("Next")', timeout=10000)
        print("[WAIT] Menunggu OTP 15 detik...")
        time.sleep(15)

        # 8. Poll OTP
        print("\n[8] Poll inbox untuk OTP...")
        otp = wait_otp(email_id, max_wait=180)
        if not otp:
            print("OTP tidak diterima!")
            ctx.close()
            cleanup(email_id)
            return

        # 9. Isi OTP digit per digit dengan keyboard events
        print(f"[9] Isi OTP: {otp}...")
        page.wait_for_load_state("networkidle")
        human_sleep(1, 2)

        # Klik input pertama lalu ketik semua digit sekaligus
        # Form akan auto-advance ke box berikutnya
        otp_inputs = page.locator('input:visible').all()
        empty_inputs = []
        for inp in otp_inputs:
            try:
                val = inp.input_value()
                if not val:
                    empty_inputs.append(inp)
            except:
                continue

        print(f"  -> Found {len(empty_inputs)} empty inputs")

        if len(empty_inputs) >= 6:
            # Klik input pertama
            empty_inputs[0].click()
            human_sleep(0.3, 0.5)
            # Ketik semua digit sekaligus - form akan auto-advance
            for digit in otp[:6]:
                page.keyboard.press(digit)
                human_sleep(0.1, 0.2)
            print("  -> OTP filled via keyboard")
        human_sleep(1, 2)

        # 10. Klik Validate
        print("[10] Klik Validate...")
        for sel in ['button:has-text("Validate")', 'button:has-text("Verify")', 'button:has-text("Next")']:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=10000)
                break
        human_sleep(3, 5)

        # 11. Pilih negara Indonesia
        print("[11] Pilih negara Indonesia...")
        human_sleep(2, 3)
        try:
            # Input combobox untuk country
            combo_input = page.locator('input[role="combobox"]')
            combo_input.click()
            human_sleep(0.5, 1)
            combo_input.type("Indonesia", delay=80)
            human_sleep(1, 2)
            # Klik option Indonesia dari listbox
            page.locator('div[role="option"]:has-text("Indonesia")').first.click()
            print("  -> Indonesia dipilih")
        except Exception as e:
            print("  -> Gagal pilih negara:", str(e)[:80])
        human_sleep(1, 2)

        # 12. Centang terms
        print("[12] Centang terms...")
        try:
            cb = page.locator('input[type="checkbox"]')
            if cb.count() > 0 and not cb.is_checked():
                cb.check()
                print("  -> Terms dicentang")
        except:
            pass
        human_sleep(1, 2)

        # 13. Klik Continue
        print("[13] Klik Continue...")
        for sel in ['button:has-text("Continue")', 'button[type="submit"]']:
            if page.locator(sel).count() > 0:
                page.click(sel, timeout=10000)
                print("  -> Continue diklik")
                break
        human_sleep(5, 8)

        page.wait_for_load_state("networkidle")
        page.screenshot(path="signup_success.png")
        print(f"\n[SUCCESS] Signup selesai! URL: {page.url}")
        print("[SUCCESS] Screenshot: signup_success.png")

        # 14. Sudah di API Keys page, tunggu load
        print("\n[14] Tunggu API Keys page load...")
        human_sleep(3, 5)

        # 15. Klik Add API Key
        print("[15] Klik Add API Key...")
        page.click('button:has-text("Add API key")', timeout=10000)
        human_sleep(1, 2)

        # 16. Isi description via JS (bypass pointer events)
        print("[16] Isi description...")
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

        # 17. Klik Generate Key
        print("[17] Klik Generate Key...")
        page.click('button:has-text("Generate Key")', timeout=10000)
        human_sleep(2, 3)

        # 18. Ambil API Key
        print("[18] Ambil API Key...")
        api_key_input = page.locator('input[value^="sk-"]')
        api_key = api_key_input.input_value()
        print(f"\n[API KEY] {api_key}")

        # 19. Simpan ke file
        with open("api_keys.txt", "a") as f:
            f.write(f"email: {email_addr} | api_key: {api_key}\n")
        print("[SAVED] API key disimpan ke api_keys.txt")

        # 20. Klik Copy via JS
        page.evaluate("""() => {
            var btns = document.querySelectorAll('span[role="button"]');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].title === 'Copy to clipboard') {
                    btns[i].click();
                    break;
                }
            }
        }""")
        print("[COPIED] API key di-copy ke clipboard")

        # 21. Tutup dialog (optional)
        try:
            page.keyboard.press("Escape")
        except:
            pass
        human_sleep(1, 2)

        print(f"\n[DONE] Email: {email_addr}")
        print(f"[DONE] API Key: {api_key}")
        print("[DONE] API key tersimpan di api_keys.txt")

        time.sleep(5)
        ctx.close()

    except Exception as e:
        print(f"[ERROR] {e}")
        try:
            page.screenshot(path="signup_error.png")
        except:
            pass
        if ctx:
            ctx.close()

    cleanup(email_id)
    print("[DONE] Selesai.")

if __name__ == "__main__":
    main()
