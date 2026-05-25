# CloakBrowser Automation Documentation

## Pendahuluan

CloakBrowser adalah library Python wrapper untuk Playwright yang menyediakan fitur anti-detection dan humanization. Cocok untuk automation yang membutuhkan stealth browsing seperti login OAuth, scraping dengan proteksi bot, dan form filling.

## Instalasi

```bash
pip install cloakbrowser
```

Dependencies yang dibutuhkan:
- `playwright` - Browser automation engine
- `playwright-core` - Core browser binaries

## Konsep Dasar

### Persistent Context vs Browser

CloakBrowser menggunakan `launch_persistent_context()` yang berbeda dengan Playwright biasa:

| Fitur | Playwright Biasa | Persistent Context |
|-------|-----------------|-------------------|
| Session storage | Tidak tersimpan | Tersimpan di profile |
| Cookies | Hilang saat close | Persisten |
| Login state | Harus login ulang | Tetap logged in |
| Profile size | Ringan | Lebih besar (ada cache) |

### Humanization

CloakBrowser menyediakan fitur humanization untuk menghindari deteksi bot:

```python
ctx = launch_persistent_context(
    "./profile_dir",
    humanize=True,
    human_preset="careful"  # Options: "careful", "fast", "medium"
)
```

Preset humanization:
- `careful` - Typing lambat, delay tinggi, mirip manusia
- `medium` - Balance antara speed dan stealth
- `fast` - Lebih cepat tapi lebih terdeteksi

## API Reference

### launch_persistent_context()

```python
from cloakbrowser import launch_persistent_context

ctx = launch_persistent_context(
    user_data_dir,      # Path ke directory profile
    headless=False,     # True untuk mode tanpa UI
    humanize=True,      # Aktifkan humanization
    human_preset="careful",
    proxy="socks5://user:pass@host:port",  # Optional: proxy
)
```

**Parameters:**

| Parameter | Type | Default | Deskripsi |
|-----------|------|---------|-----------|
| `user_data_dir` | str | Required | Path untuk menyimpan browser profile |
| `headless` | bool | False | Jalankan tanpa GUI |
| `humanize` | bool | True | Aktifkan anti-detection |
| `human_preset` | str | "careful" | Preset humanization |
| `proxy` | str | None | Proxy URL (socks5/http) |

### Context Methods

```python
# Membuat halaman baru
page = ctx.new_page()

# Mendapatkan semua tabs
pages = ctx.pages

# Event listener untuk tab baru
ctx.on("page", lambda new_page: print(new_page.url))

# Mengambil cookies
cookies = ctx.cookies()

# Menutup browser
ctx.close()
```

### Page Methods

```python
# Navigasi
page.goto("https://example.com", timeout=60000)

# Selector dan interaksi
page.click("button:has-text('Submit')")
page.type("input[name='email']", "user@example.com", delay=80)
page.fill("input[name='name']", "John Doe")

# Waiting
page.wait_for_selector("input[type='password']", timeout=10000)
page.wait_for_load_state("networkidle")

# JavaScript execution
result = page.evaluate("() => document.title")
page.evaluate("() => { console.log('Hello from browser'); }")

# Screenshot
page.screenshot(path="screenshot.png")

# Page info
url = page.url
title = page.title()

# Locator (modern Playwright API)
count = page.locator("button").count()
page.locator("input[type='email']").fill("test@test.com")
```

## Pattern & Use Cases

### 1. Basic Login Flow

```python
import time
from cloakbrowser import launch_persistent_context

def login_flow():
    ctx = launch_persistent_context(
        "./my_profile",
        headless=False,
        humanize=True,
        human_preset="careful"
    )
    
    page = ctx.new_page()
    page.goto("https://example.com/login")
    time.sleep(2)
    
    # Fill credentials
    page.type('input[name="email"]', "user@example.com", delay=80)
    page.type('input[name="password"]', "mypassword", delay=80)
    page.click('button[type="submit"]')
    
    # Wait for redirect
    time.sleep(5)
    
    # Check if logged in
    if "dashboard" in page.url:
        print("Login successful!")
    
    ctx.close()
```

### 2. Google OAuth Login

Google login memerlukan penanganan khusus karena multi-step flow:

```python
def google_oauth_login(page, email, password):
    # Click Google login button
    page.click('button:has-text("Google")')
    time.sleep(3)
    
    # Step 1: Enter email
    page.wait_for_selector('input[type="email"]', timeout=15000)
    page.type('input[type="email"]', email, delay=80)
    page.click("#identifierNext")
    time.sleep(5)
    
    # Step 2: Enter password
    page.wait_for_selector('input[type="password"]', timeout=15000)
    page.type('input[type="password"]', password, delay=80)
    page.click("#passwordNext")
    time.sleep(5)
    
    # Step 3: Handle "I understand" (Google Workspace)
    try:
        page.click('button:has-text("I understand")', timeout=5000)
        time.sleep(3)
    except:
        pass
    
    # Step 4: Handle OAuth consent
    try:
        page.click('button:has-text("Continue")', timeout=5000)
        time.sleep(5)
    except:
        pass
    
    # Verify login success
    for i in range(10):
        if "signin" not in page.title().lower():
            return True
        time.sleep(1)
    
    return False
```

### 3. Proxy Configuration

```python
# SOCKS5 proxy
ctx = launch_persistent_context(
    "./profile",
    proxy="socks5://127.0.0.1:1080"
)

# SOCKS5 with auth
ctx = launch_persistent_context(
    "./profile",
    proxy="socks5://user:password@proxy.example.com:1080"
)

# HTTP proxy
ctx = launch_persistent_context(
    "./profile",
    proxy="http://user:password@proxy.example.com:8080"
)

# Rotating proxies from file
def load_proxies(filepath):
    with open(filepath) as f:
        proxies = [line.strip() for line in f if line.strip()]
    
    # Normalize proxy format
    result = []
    for p in proxies:
        if p.startswith("socks") or p.startswith("http"):
            result.append(p)
        else:
            result.append(f"socks5://{p}")
    return result

proxies = load_proxies("proxy.txt")
proxy = random.choice(proxies)

ctx = launch_persistent_context(
    "./profile",
    proxy=proxy
)
```

### 4. Handling Popup/New Tab

```python
def handle_popup_flow():
    ctx = launch_persistent_context("./profile", headless=False)
    page = ctx.new_page()
    
    popup_page = None
    
    def on_new_page(new_page):
        nonlocal popup_page
        print(f"New tab: {new_page.url}")
        if "target-site.com" in new_page.url:
            popup_page = new_page
    
    ctx.on("page", on_new_page)
    
    # Action that triggers popup
    page.click('button:has-text("Pay Now")')
    
    # Wait for popup
    for i in range(30):
        if popup_page:
            break
        time.sleep(1)
    
    if popup_page:
        popup_page.bring_to_front()
        # Work with popup
        popup_page.fill("input[name='card']", "4242424242424242")
    
    ctx.close()
```

### 5. Form Auto-Fill with JavaScript Injection

Untuk form yang menggunakan React/Vue dengan controlled inputs, perlu menggunakan native setter:

```python
FILL_SCRIPT = """
const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
).set;

async function typeText(element, text, delay = 30) {
    if (!element) return false;
    
    // Clear field using native setter
    nativeSetter.call(element, '');
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.focus();
    
    // Type character by character
    for (let char of text) {
        nativeSetter.call(element, element.value + char);
        element.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
        element.dispatchEvent(new InputEvent('input', { data: char, bubbles: true }));
        element.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
        await new Promise(r => setTimeout(r, delay));
    }
    
    element.blur();
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}

function setSelect(element, value) {
    if (!element) return false;
    element.value = value;
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}

async function fillForm(data) {
    await typeText(document.querySelector('input[name="cardNumber"]'), data.cardNumber);
    await typeText(document.querySelector('input[name="cardExpiry"]'), data.cardExpiry);
    await typeText(document.querySelector('input[name="cardCvc"]'), data.cardCvc);
    await typeText(document.querySelector('input[name="billingName"]'), data.billingName);
    setSelect(document.querySelector('select[name="billingCountry"]'), data.country);
}
"""

def fill_stripe_form(page, card_data):
    script = FILL_SCRIPT + f"\nfillForm({json.dumps(card_data)});"
    page.evaluate(script)
```

### 6. Cookie Extraction & Management

```python
def extract_cookies(ctx, cookie_name="session"):
    cookies = ctx.cookies()
    
    for c in cookies:
        if c["name"] == cookie_name:
            return c["value"]
    
    return None

def save_cookies_to_file(ctx, filepath):
    import json
    cookies = ctx.cookies()
    with open(filepath, "w") as f:
        json.dump(cookies, f)

def load_cookies_to_context(ctx, filepath):
    import json
    with open(filepath) as f:
        cookies = json.load(f)
    ctx.add_cookies(cookies)
```

### 7. Batch Processing dengan Multi-Threading

```python
import threading
import json
import os

PROGRESS_FILE = "progress.json"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": []}

def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

def process_account(account, proxy, progress):
    email = account["email"]
    profile_dir = f"./profiles/{email.split('@')[0]}"
    
    try:
        ctx = launch_persistent_context(
            profile_dir,
            headless=False,
            humanize=True,
            proxy=proxy
        )
        
        page = ctx.new_page()
        # ... automation logic ...
        
        progress["completed"].append(email)
        ctx.close()
        
    except Exception as e:
        print(f"Error: {e}")
        progress["failed"].append(email)
    
    save_progress(progress)

def main():
    accounts = load_accounts()
    proxies = load_proxies()
    progress = load_progress()
    
    # Filter already processed
    pending = [a for a in accounts 
               if a["email"] not in progress["completed"] 
               and a["email"] not in progress["failed"]]
    
    batch_size = 3
    
    for i in range(0, len(pending), batch_size):
        batch = pending[i:i+batch_size]
        threads = []
        
        for j, account in enumerate(batch):
            proxy = proxies[(i + j) % len(proxies)]
            t = threading.Thread(
                target=process_account, 
                args=(account, proxy, progress)
            )
            threads.append(t)
            t.start()
            time.sleep(2)  # Stagger start
        
        for t in threads:
            t.join()

if __name__ == "__main__":
    main()
```

### 8. Random Data Generation

```python
import random

FIRST_NAMES = ["John", "Jane", "Michael", "Sarah", "David"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones"]
STREETS = ["Main St", "Oak Ave", "Park Rd", "Elm Blvd"]
CITIES = [
    {"city": "New York", "postal": "10001"},
    {"city": "Los Angeles", "postal": "90001"},
    {"city": "Chicago", "postal": "60601"},
]

def generate_identity():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    city_data = random.choice(CITIES)
    
    return {
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}@example.com",
        "address": f"{random.randint(1, 999)} {random.choice(STREETS)}",
        "city": city_data["city"],
        "postal": city_data["postal"],
        "country": "US",
    }
```

## Selector Strategies

### Text-based Selectors (Playwright)

```python
# Contains text
page.click('button:has-text("Submit")')

# Exact text
page.click('button:has-text-is("Submit")')

# Combined
page.click('button.submit:has-text("Continue")')
```

### CSS Selectors

```python
# By attribute
page.click('button[type="submit"]')
page.fill('input[name="email"]', "test@test.com")

# By class
page.click('.submit-button')

# By ID
page.click('#login-button')

# Multiple selectors (fallback)
page.click('input[name="password"], input[type="password"]')
```

### Locator API (Recommended)

```python
# More reliable than selectors
login_btn = page.locator('button:has-text("Login")')
if login_btn.count() > 0:
    login_btn.click()

# Chaining
form = page.locator('form#login')
form.locator('input[name="email"]').fill("test@test.com")
form.locator('button[type="submit"]').click()

# Filtering
page.locator('button').filter(has_text="Submit").click()
```

## Error Handling

```python
from playwright.sync_api import TimeoutError as PlaywrightTimeout

def safe_click(page, selector, timeout=5000):
    try:
        page.click(selector, timeout=timeout)
        return True
    except PlaywrightTimeout:
        print(f"Timeout waiting for: {selector}")
        return False
    except Exception as e:
        print(f"Error clicking {selector}: {e}")
        return False

def safe_type(page, selector, text, delay=80):
    try:
        page.wait_for_selector(selector, timeout=5000)
        page.type(selector, text, delay=delay)
        return True
    except PlaywrightTimeout:
        print(f"Timeout waiting for: {selector}")
        return False
```

## Best Practices

### 1. Profile Management

```python
# Gunakan unique profile per account
def get_profile_dir(email):
    safe_name = email.split("@")[0].replace(".", "_")
    return f"./profiles/{safe_name}"

# Cleanup old profiles
import shutil
if os.path.exists("./profiles/old_account"):
    shutil.rmtree("./profiles/old_account")
```

### 2. Delay & Timing

```python
import time
import random

# Random delay untuk menghindari deteksi
def human_delay(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))

# Antara actions
page.click("button")
human_delay()
page.type("input", "text")
```

### 3. Screenshot untuk Debugging

```python
def debug_screenshot(page, name="debug"):
    timestamp = int(time.time())
    page.screenshot(path=f"debug/{name}_{timestamp}.png")

# Capture on error
try:
    # automation code
    pass
except Exception as e:
    page.screenshot(path="error_screenshot.png")
    raise e
```

### 4. Environment Variables

```python
# .env file
GOOGLE_EMAIL=your@email.com
GOOGLE_PASSWORD=yourpassword
PROXY_URL=socks5://user:pass@host:port

# Python code
from dotenv import load_dotenv
import os

load_dotenv()
EMAIL = os.getenv("GOOGLE_EMAIL")
PASSWORD = os.getenv("GOOGLE_PASSWORD")
```

### 5. Resource Cleanup

```python
def run_automation():
    ctx = None
    try:
        ctx = launch_persistent_context("./profile")
        page = ctx.new_page()
        # ... automation logic ...
    finally:
        if ctx:
            ctx.close()
```

## Troubleshooting

### Browser Tidak Muncul

```python
# Pastikan headless=False
ctx = launch_persistent_context(
    "./profile",
    headless=False  # <- Important!
)
```

### Timeout Errors

```python
# Increase timeout
page.goto("https://slow-site.com", timeout=120000)  # 2 minutes

# Use wait_for_load_state
page.goto("https://example.com")
page.wait_for_load_state("networkidle")  # Wait for network idle
```

### Element Not Found

```python
# Wait for element
page.wait_for_selector("button.submit", timeout=10000)

# Check count before action
if page.locator("button.submit").count() > 0:
    page.click("button.submit")

# Try multiple selectors
selectors = [
    'button[type="submit"]',
    'button.submit',
    '#submit-btn'
]
for sel in selectors:
    if page.locator(sel).count() > 0:
        page.click(sel)
        break
```

### Proxy Connection Failed

```python
# Test proxy manually dulu
# Pastikan format benar:
# - socks5://host:port
# - socks5://user:pass@host:port
# - http://user:pass@host:port

# Try dengan timeout lebih tinggi
ctx = launch_persistent_context(
    "./profile",
    proxy="socks5://proxy.example.com:1080",
    timeout=60000
)
```

### JavaScript Form Fill Tidak Bekerja

```python
# Gunakan native setter untuk React/Vue apps
# Lihat contoh di "Form Auto-Fill with JavaScript Injection"

# Atau gunakan page.type() dengan delay
page.type("input", "value", delay=100)  # delay per character
```

## Complete Example: Stripe Checkout Automation

```python
import time
import random
import json
from cloakbrowser import launch_persistent_context

STRIPE_URL = "https://checkout.stripe.com/pay/..."

FILL_SCRIPT = """
const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
).set;

async function typeText(element, text, delay = 30) {
    if (!element) return false;
    nativeSetter.call(element, '');
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.focus();
    
    for (let char of text) {
        nativeSetter.call(element, element.value + char);
        element.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
        element.dispatchEvent(new InputEvent('input', { data: char, bubbles: true }));
        element.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
        await new Promise(r => setTimeout(r, delay));
    }
    
    element.blur();
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}

function setSelect(element, value) {
    if (!element) return false;
    element.value = value;
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}

async function fillStripe(data) {
    await typeText(document.querySelector('input[name="cardNumber"]'), data.cardNumber);
    await typeText(document.querySelector('input[name="cardExpiry"]'), data.cardExpiry);
    await typeText(document.querySelector('input[name="cardCvc"]'), data.cardCvc);
    await typeText(document.querySelector('input[name="billingName"]'), data.billingName);
    setSelect(document.querySelector('select[name="billingCountry"]'), data.country);
    await new Promise(r => setTimeout(r, 400));
    await typeText(document.querySelector('input[name="billingAddressLine1"]'), data.address);
    await typeText(document.querySelector('input[name="billingLocality"]'), data.city);
    await typeText(document.querySelector('input[name="billingPostalCode"]'), data.postal);
}
"""

def fill_stripe_checkout(card_data):
    print(f"Card: {card_data['cardNumber']}")
    
    ctx = launch_persistent_context(
        "./stripe_profile",
        headless=False,
        humanize=True,
        human_preset="careful"
    )
    
    page = ctx.new_page()
    page.goto(STRIPE_URL, timeout=60000)
    time.sleep(5)
    
    page.screenshot(path="stripe_before.png")
    
    script = FILL_SCRIPT + f"\nfillStripe({json.dumps(card_data)});"
    page.evaluate(script)
    
    time.sleep(5)
    page.screenshot(path="stripe_after.png")
    
    print("Form filled! Waiting 60s for manual review...")
    time.sleep(60)
    
    ctx.close()

if __name__ == "__main__":
    card_data = {
        "cardNumber": "4242424242424242",
        "cardExpiry": "12/28",
        "cardCvc": "123",
        "billingName": "John Smith",
        "country": "US",
        "address": "123 Main St",
        "city": "New York",
        "postal": "10001"
    }
    fill_stripe_checkout(card_data)
```

## Referensi

- [Playwright Documentation](https://playwright.dev/python/docs/intro)
- [CloakBrowser GitHub](https://github.com/nicholasren/cloakbrowser)
- [Playwright Selectors](https://playwright.dev/python/docs/selectors)
