# Pinkgreen API Documentation

Dokumentasi lengkap cara kerja Pinkgreen API untuk temporary email, OTP, dan OAuth sync.

---

## Daftar Isi

1. [Konfigurasi](#konfigurasi)
2. [Endpoint API](#endpoint-api)
3. [Flow Penggunaan](#flow-penggunaan)
4. [Contoh Implementasi](#contoh-implementasi)
5. [Error Handling](#error-handling)

---

## Konfigurasi

### Environment Variables

```env
# Pinkgreen API
PINKGREEN_BASE_URL=https://pinkgreen.me
PINKGREEN_API_KEY=your-pinkgreen-api-key
PINKGREEN_MANAGEMENT_KEY=your-management-key-here

# Domain yang tersedia
PINKGREEN_DOMAIN=truelove.id
DEFAULT_DOMAIN=ascentia.site
```

### Base URL

| Environment | URL |
|-------------|-----|
| Production | `https://pinkgreen.me` |
| API Endpoint | `https://api.pinkgreen.me` |

### Authentication

Pinkgreen menggunakan 2 jenis API Key:

| Key Type | Header | Kegunaan |
|----------|--------|----------|
| `PINKGREEN_API_KEY` | `X-API-Key` | Operasi email (create, read, delete) |
| `PINKGREEN_MANAGEMENT_KEY` | `Authorization: Bearer` | OAuth sync ke Pinkgreen |

### Domain yang Tersedia

Ambil daftar domain dari API config:

```
GET {PINKGREEN_BASE_URL}/api/config
Response: { "emailDomains": "truelove.id,ascentia.site,zapin.my.id,..." }
```

Domain default: `truelove.id`

---

## Endpoint API

### 1. Ambil Daftar Domain

```http
GET {PINKGREEN_BASE_URL}/api/config
Headers:
  X-API-Key: {PINKGREEN_API_KEY}
  Content-Type: application/json

Response:
{
  "emailDomains": "truelove.id,ascentia.site,zapin.my.id"
}
```

### 2. Buat Email Baru

```http
POST {PINKGREEN_BASE_URL}/api/emails/generate
Headers:
  X-API-Key: {PINKGREEN_API_KEY}
  Content-Type: application/json

Body:
{
  "name": "john.doe",        // local part (sebelum @)
  "domain": "truelove.id",   // domain
  "expiryTime": 0            // 0 = tidak expired
}

Response:
{
  "id": "35c62b6d-e5f1-44ad-81b4-2aed2e323c80",
  "email": "john.doe@truelove.id",
  "createdAt": "2024-01-15T10:30:00Z",
  "expiresAt": null
}
```

**Parameter:**
- `name`: Local part email (huruf kecil, tanpa spasi)
- `domain`: Domain dari daftar yang tersedia
- `expiryTime`: 
  - `0` = tidak ada expiry
  - angka lain = durasi dalam detik

### 3. Ambil Daftar Email

```http
GET {PINKGREEN_BASE_URL}/api/emails
Headers:
  X-API-Key: {PINKGREEN_API_KEY}

Response:
{
  "emails": [
    {
      "id": "uuid-1",
      "address": "john.doe@truelove.id",
      "createdAt": "2024-01-15T10:30:00Z"
    },
    {
      "id": "uuid-2",
      "address": "jane.smith@truelove.id",
      "createdAt": "2024-01-15T11:00:00Z"
    }
  ],
  "nextCursor": "cursor-string-for-pagination"
}
```

**Pagination:**
```
GET /api/emails?cursor={nextCursor}
```

### 4. Cari Email by Address

```python
# Loop through all emails to find specific address
email_id = None
cursor = None

while True:
    url = f"{PINKGREEN_BASE_URL}/api/emails"
    if cursor:
        url += f"?cursor={cursor}"
    
    resp = requests.get(url, headers=headers)
    data = resp.json()
    
    for email in data.get('emails', []):
        if target_email.lower() in email.get('address', '').lower():
            email_id = email.get('id')
            break
    
    if email_id:
        break
    
    cursor = data.get('nextCursor')
    if not cursor:
        break
```

### 5. Ambil Pesan/Email Inbox

```http
GET {PINKGREEN_BASE_URL}/api/emails/{email_id}
Headers:
  X-API-Key: {PINKGREEN_API_KEY}

Response:
{
  "id": "uuid",
  "address": "john.doe@truelove.id",
  "messages": [
    {
      "id": "msg-uuid-1",
      "subject": "Verify your email",
      "from": "noreply@openai.com",
      "date": "2024-01-15T12:00:00Z"
    },
    {
      "id": "msg-uuid-2",
      "subject": "Welcome to ChatGPT Business",
      "from": "invite@openai.com",
      "date": "2024-01-15T12:05:00Z"
    }
  ]
}
```

### 6. Ambil Konten Pesan (Text)

```http
GET {PINKGREEN_BASE_URL}/api/emails/{email_id}/{message_id}
Headers:
  X-API-Key: {PINKGREEN_API_KEY}

Response:
{
  "message": {
    "id": "msg-uuid",
    "subject": "Verify your email",
    "from": "noreply@openai.com",
    "to": "john.doe@truelove.id",
    "date": "2024-01-15T12:00:00Z",
    "content": "Your verification code is 123456...",
    "html": "<html><body>Your verification code is <b>123456</b>...</body></html>"
  }
}
```

**Field penting:**
- `content`: Plain text body
- `html`: HTML body (berisi link, formatting)

### 7. Hapus Email

```http
DELETE {PINKGREEN_BASE_URL}/api/emails/{email_id}
Headers:
  X-API-Key: {PINKGREEN_API_KEY}

Response:
{
  "success": true
}
```

---

## Flow Penggunaan

### Flow 1: Buat Email Baru

```
1. POST /api/emails/generate
   ↓
2. Response: { id, email, createdAt }
   ↓
3. Simpan email_id untuk polling messages
```

### Flow 2: Ambil OTP dari Email

```
1. GET /api/emails/{email_id}
   ↓
2. Loop through messages
   ↓
3. Cari message dengan subject mengandung "verification" atau "code"
   ↓
4. GET /api/emails/{email_id}/{message_id}
   ↓
5. Extract OTP dari field "html" atau "content"
   ↓
6. Pattern: \b(\d{6})\b (6 digit)
```

### Flow 3: Extract Invite Link dari Email

```
1. GET /api/emails/{email_id}
   ↓
2. Cari message dengan subject mengandung "invited you" atau "ChatGPT Business"
   ↓
3. GET /api/emails/{email_id}/{message_id}
   ↓
4. Extract link dari field "html"
   ↓
5. Pattern regex:
   - https://chatgpt.com/...
   - https://auth.openai.com/...
   - https://chat.openai.com/invite/...
```

### Flow 4: OAuth Sync ke Pinkgreen

```
1. GET https://api.pinkgreen.me/v0/management/codex-auth-url?is_webui=true
   Headers: Authorization: Bearer {PINKGREEN_MANAGEMENT_KEY}
   ↓
2. Response: { url: "oauth_url", state: "..." }
   ↓
3. Navigate ke OAuth URL di browser
   ↓
4. Login dengan email yang sudah di-register
   ↓
5. Setelah consent, redirect ke localhost:1455?code=xxx
   ↓
6. Capture code dari URL
   ↓
7. POST https://api.pinkgreen.me/v0/management/oauth-callback
   Body: { provider: "codex", code: captured_code, state: state }
   ↓
8. Response: { success: true }
```

---

## Contoh Implementasi

### Python: Buat Email

```python
import requests

PINKGREEN_BASE_URL = "https://pinkgreen.me"
PINKGREEN_API_KEY = "your-api-key"

headers = {
    "X-API-Key": PINKGREEN_API_KEY,
    "Content-Type": "application/json"
}

# Buat email
resp = requests.post(
    f"{PINKGREEN_BASE_URL}/api/emails/generate",
    headers=headers,
    json={
        "name": "john.doe",
        "domain": "truelove.id",
        "expiryTime": 0
    }
)

data = resp.json()
print(f"Email: {data['email']}")
print(f"ID: {data['id']}")
```

### Python: Polling OTP

```python
import re
import time

def get_otp(email_id, max_retries=30, interval=5):
    """Poll untuk OTP dari inbox"""
    
    for attempt in range(max_retries):
        # Ambil messages
        resp = requests.get(
            f"{PINKGREEN_BASE_URL}/api/emails/{email_id}",
            headers=headers
        )
        data = resp.json()
        messages = data.get('messages', [])
        
        for msg in messages:
            subject = msg.get('subject', '').lower()
            
            # Cari email yang berisi OTP
            if 'openai' in subject or 'verification' in subject or 'code' in subject:
                # Ambil konten HTML
                msg_resp = requests.get(
                    f"{PINKGREEN_BASE_URL}/api/emails/{email_id}/{msg['id']}",
                    headers=headers
                )
                msg_data = msg_resp.json()
                html = msg_data['message'].get('html', '')
                
                # Extract 6 digit OTP
                match = re.search(r'\b(\d{6})\b', html)
                if match:
                    return match.group(1)
        
        time.sleep(interval)
    
    return None

# Usage
otp = get_otp("email-uuid-here")
print(f"OTP: {otp}")
```

### Python: Extract Invite Link

```python
import re

def extract_invite_link(email_id, max_retries=30, interval=3):
    """Poll untuk invitation link dari inbox"""
    
    patterns = [
        r'https://chat\.openai\.com/invite/[^\s<>"']+',
        r'https://auth\.openai\.com/[^\s<>"']+',
        r'https://openai\.com/[^\s<>"']*invite[^\s<>"']*',
        r'href="(https?://[^"]*(?:openai|chatgpt)[^"]*)"',
        r'https://chatgpt\.com/[^\s<>"']+',
    ]
    
    for attempt in range(max_retries):
        resp = requests.get(
            f"{PINKGREEN_BASE_URL}/api/emails/{email_id}",
            headers=headers
        )
        data = resp.json()
        messages = data.get('messages', [])
        
        for msg in messages:
            subject = msg.get('subject', '').lower()
            
            if 'invited you' in subject or 'chatgpt business' in subject:
                msg_resp = requests.get(
                    f"{PINKGREEN_BASE_URL}/api/emails/{email_id}/{msg['id']}",
                    headers=headers
                )
                msg_data = msg_resp.json()
                html = msg_data['message'].get('html', '')
                
                for pattern in patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        # Jika pattern punya capture group
                        invite_link = match.group(1) if match.lastindex else match.group(0)
                        return invite_link
        
        time.sleep(interval)
    
    return None

# Usage
invite_link = extract_invite_link("email-uuid-here")
print(f"Invite: {invite_link}")
```

### Python: OAuth Sync

```python
PINKGREEN_MANAGEMENT_KEY = "your-management-key"

mgmt_headers = {
    "Authorization": f"Bearer {PINKGREEN_MANAGEMENT_KEY}"
}

# 1. Get OAuth URL
resp = requests.get(
    "https://api.pinkgreen.me/v0/management/codex-auth-url?is_webui=true",
    headers=mgmt_headers
)

data = resp.json()
oauth_url = data['url']
state = data['state']

print(f"OAuth URL: {oauth_url}")

# 2. Navigate ke OAuth URL di browser (Playwright/Puppeteer)
# ... browser automation code ...

# 3. Setelah redirect ke localhost:1455?code=xxx
# Capture code dari URL

# 4. POST callback
callback_resp = requests.post(
    "https://api.pinkgreen.me/v0/management/oauth-callback",
    headers=mgmt_headers,
    json={
        "provider": "codex",
        "code": captured_code,
        "state": state
    }
)

print(f"Sync result: {callback_resp.json()}")
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | - |
| 400 | Bad Request | Check request body/format |
| 401 | Unauthorized | Check API key |
| 404 | Not Found | Email/message tidak ditemukan |
| 429 | Rate Limited | Tunggu dan retry |
| 500 | Server Error | Retry setelah delay |

### Retry Logic

```python
import time
from requests.exceptions import RequestException

def api_call_with_retry(url, headers, max_retries=3, delay=2):
    """API call dengan retry logic"""
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise
```

---

## Tips & Best Practices

### 1. Polling Rate

- Jangan poll terlalu cepat (min 3-5 detik interval)
- Max retries 30-60 attempts untuk OTP/invite
- Gunakan exponential backoff jika server error

### 2. Email Lifetime

- `expiryTime: 0` = tidak expired
- Email tetap ada selama tidak di-delete
- Recommended: delete email setelah tidak diperlukan

### 3. OTP Pattern

```python
# OTP biasanya 6 digit
pattern = r'\b(\d{6})\b'

# Kadang ada di HTML tag
pattern = r'>(\d{6})<'

# Atau di attribute
pattern = r'data-code="(\d{6})"'
```

### 4. Invite Link Pattern

```python
# ChatGPT Business invitation
patterns = [
    r'https://chatgpt\.com/[^"\s<>]+',
    r'https://auth\.openai\.com/[^"\s<>]+',
    r'https://chat\.openai\.com/invite/[^"\s<>]+',
]
```

---

## Referensi File

| File | Deskripsi |
|------|-----------|
| `src/pinkgreen_client.py` | Client class untuk Pinkgreen API |
| `src/config.py` | Konfigurasi dan environment variables |
| `main.py` | Implementasi lengkap dengan browser automation |
| `claim_and_sync.py` | Flow claim invite + OAuth sync |
| `.env.example` | Contoh environment variables |

---

## Changelog

- **2024-01**: Initial documentation
- Base URL: `https://pinkgreen.me`
- API URL: `https://api.pinkgreen.me`
