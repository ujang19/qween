# QwenCloud Auto Signup

Script otomatis untuk membuat akun QwenCloud + generate API key menggunakan temp email dari Pinkgreen, browser automation CloakBrowser, dan menyimpan hasil ke Turso (libsql).

---

## Requirements

- Python 3.11+
- Google Chrome / Chromium

Install dependencies:

```bash
pip install cloakbrowser playwright requests python-dotenv libsql-client
```

---

## Setup

### 1. Clone repo

```bash
git clone https://github.com/ujang19/qween.git
cd qween
```

### 2. Buat file `.env`

Copy dari template:

```bash
cp .env.example .env
```

Isi `.env` dengan credentials kamu:

```env
# Pinkgreen API
PINKGREEN_API_KEY=your-pinkgreen-api-key
PINKGREEN_BASE_URL=https://pinkgreen.me
PINKGREEN_DOMAIN=ascentia.site

# Turso DB
TURSO_URL=https://your-db.turso.io
TURSO_TOKEN=your-turso-token

# Script Config
TOTAL_ACCOUNTS=1000
HEADLESS=true
```

### 3. Setup Turso DB

Buat database di [turso.io](https://turso.io), lalu isi `TURSO_URL` dan `TURSO_TOKEN` di `.env`.

Tabel akan dibuat otomatis saat script pertama kali dijalankan.

---

## Cara Menjalankan

### Single Signup (1 akun)

```bash
python qwencloud_auto.py
```

Output:
```
==================================================
QWENCLOUD AUTO SIGNUP
==================================================
[1] Membuat email temporary...
[EMAIL] user12345@ascentia.site (ID: xxx-xxx)
[2] Launch CloakBrowser...
[3] Buka qwencloud.com...
...
[SUCCESS] Signup selesai! URL: https://home.qwencloud.com/api-keys
[API KEY] sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
[DONE] API key tersimpan di api_keys.txt
```

### Bulk Signup (1000 akun)

```bash
python qwencloud_bulk.py
```

Output per run:
```
==================================================
QWENCLOUD BULK SIGNUP - 1000 accounts
==================================================
[DB] Table ready.

==================================================
[RUN 1/1000] Starting...
==================================================
[EMAIL] user12345@ascentia.site
[OTP] 123456
[DB] Saved: user12345@ascentia.site | sk-xxxx...
[RUN 1] SUCCESS - user12345@ascentia.site | sk-xxxx...
[STATS] Success: 1 | Failed: 0 | Total: 1
[WAIT] Delay 8.3s sebelum run berikutnya...
```

---

## Konfigurasi

Semua konfigurasi ada di file `.env`:

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `PINKGREEN_API_KEY` | - | API key dari pinkgreen.me |
| `PINKGREEN_BASE_URL` | `https://pinkgreen.me` | Base URL Pinkgreen |
| `PINKGREEN_DOMAIN` | `ascentia.site` | Domain untuk temp email |
| `TURSO_URL` | - | URL database Turso |
| `TURSO_TOKEN` | - | Auth token Turso |
| `TOTAL_ACCOUNTS` | `1000` | Jumlah akun yang dibuat |
| `HEADLESS` | `true` | Jalankan browser tanpa UI |

---

## Output

### File `api_keys.txt`

Setiap akun yang berhasil dibuat disimpan ke file lokal:

```
user12345@ascentia.site|sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
user67890@ascentia.site|sk-yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

### Turso Database

Data juga disimpan ke Turso dengan struktur:

```sql
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    api_key TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Cek data di DB:

```python
import requests

TURSO_URL = "https://your-db.turso.io"
TURSO_TOKEN = "your-token"
HEADERS = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}

r = requests.post(f"{TURSO_URL}/v2/pipeline", headers=HEADERS, json={
    "requests": [
        {"type": "execute", "stmt": {"sql": "SELECT COUNT(*) FROM accounts"}},
        {"type": "close"}
    ]
})
print(r.json())
```

---

## Flow Script

```
1. Buat temp email via Pinkgreen API
        ↓
2. Launch CloakBrowser (headless, humanize)
        ↓
3. Buka https://home.qwencloud.com/api-keys
        ↓
4. Redirect ke Alibaba SSO login → klik Sign Up
        ↓
5. Isi email temp → klik Next → OTP dikirim
        ↓
6. Poll inbox Pinkgreen untuk OTP
        ↓
7. Isi OTP → Validate
        ↓
8. Pilih negara Indonesia → Centang terms → Continue
        ↓
9. Klik Add API Key → Generate Key
        ↓
10. Ambil API key → Simpan ke Turso + api_keys.txt
        ↓
11. Hapus temp email + browser profile
        ↓
12. Delay 5-15 detik → Run berikutnya
```

---

## Troubleshooting

### OTP tidak diterima
- Pastikan `PINKGREEN_API_KEY` valid
- Cek domain `PINKGREEN_DOMAIN` tersedia di Pinkgreen
- Tambah `max_wait` di fungsi `wait_otp()`

### Browser error / timeout
- Set `HEADLESS=false` untuk debug visual
- Cek koneksi internet
- Hapus folder `profiles/` dan coba lagi

### Turso connection error
- Pastikan `TURSO_URL` dan `TURSO_TOKEN` benar
- Cek quota Turso tidak habis

---

## Tech Stack

| Library | Kegunaan |
|---------|----------|
| `cloakbrowser` | Browser automation dengan anti-detection |
| `playwright` | Browser engine |
| `requests` | HTTP client untuk Pinkgreen + Turso API |
| `python-dotenv` | Load environment variables dari `.env` |
