"""
QwenCloud Persistent Runner
- Sequential (satu-satu, 1 akun pada satu waktu)
- Proxy rotated per run dari proxy.txt (sudah otomatis di qwencloud_bulk.bypass_captcha)
- Persistent: auto-restart kalau crash, sleep & retry kalau error
- Run sampai TARGET_TOTAL akun sukses tercapai (read dari Turso/api_keys.txt count)
- Stop graceful via SIGTERM/SIGINT (Ctrl+C)
"""
import os, time, random, shutil, signal, sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from qwencloud_bulk import (
    make_email, cleanup_email,
    run_signup, db_init, db_save,
)

TARGET_TOTAL  = int(os.getenv("TARGET_TOTAL", "1000"))
RUN_TIMEOUT   = int(os.getenv("RUN_TIMEOUT", "240"))
DELAY_MIN     = float(os.getenv("DELAY_MIN", "5"))
DELAY_MAX     = float(os.getenv("DELAY_MAX", "10"))
ERROR_BACKOFF = float(os.getenv("ERROR_BACKOFF", "20"))
KEYS_FILE     = "api_keys.txt"
LOG_FILE      = os.getenv("LOG_FILE", "persistent.log")

_stop = False

def _handle_stop(signum, frame):
    global _stop
    _stop = True
    print(f"\n[STOP] sinyal {signum} diterima, akan berhenti setelah run ini selesai...")

signal.signal(signal.SIGTERM, _handle_stop)
signal.signal(signal.SIGINT, _handle_stop)


def count_existing_keys():
    if not os.path.exists(KEYS_FILE):
        return 0
    n = 0
    try:
        with open(KEYS_FILE) as f:
            for line in f:
                if line.strip() and "|" in line:
                    n += 1
    except Exception:
        pass
    return n


def run_once(idx):
    email_id = None
    profile_dir = f"./profiles/persist_{int(time.time())}_{random.randint(1000, 9999)}"
    try:
        email_id, email_addr = make_email()
        if not email_id:
            print("[SKIP] gagal buat email")
            return False

        # Timeout per run via SIGALRM
        def _to(signum, frame):
            raise TimeoutError(f"run timeout {RUN_TIMEOUT}s")
        signal.signal(signal.SIGALRM, _to)
        signal.alarm(RUN_TIMEOUT)
        try:
            api_key = run_signup(email_addr, email_id, profile_dir, run_idx=idx)
        finally:
            signal.alarm(0)

        if api_key:
            db_save(email_addr, api_key)
            with open(KEYS_FILE, "a") as f:
                f.write(f"{email_addr}|{api_key}\n")
            print(f"[OK] {email_addr} | {api_key}")
            return True
        else:
            print("[FAIL] tidak dapat API key")
            return False
    except Exception as e:
        import traceback
        print(f"[ERROR] {e.__class__.__name__}: {e}")
        traceback.print_exc()
        return False
    finally:
        if email_id:
            cleanup_email(email_id)
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir, ignore_errors=True)


def main():
    db_init()
    started_at = datetime.now()
    print("=" * 60)
    print(f"QWENCLOUD PERSISTENT RUNNER")
    print(f"Started   : {started_at.isoformat()}")
    print(f"Target    : {TARGET_TOTAL} akun total (di {KEYS_FILE})")
    print(f"Existing  : {count_existing_keys()} akun")
    print(f"Timeout   : {RUN_TIMEOUT}s per run")
    print(f"Delay     : {DELAY_MIN}-{DELAY_MAX}s antar run")
    print(f"Backoff   : {ERROR_BACKOFF}s setelah fail")
    print(f"PID       : {os.getpid()}")
    print("=" * 60)

    success = 0
    failed = 0
    consecutive_fails = 0
    run_idx = 0

    while not _stop:
        existing = count_existing_keys()
        if existing >= TARGET_TOTAL:
            print(f"[DONE] target {TARGET_TOTAL} tercapai (existing={existing})")
            break

        run_idx += 1
        print(f"\n[{datetime.now().isoformat()}] RUN #{run_idx} (existing={existing}, success_session={success}, failed_session={failed})")

        ok = run_once(run_idx)
        if ok:
            success += 1
            consecutive_fails = 0
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
        else:
            failed += 1
            consecutive_fails += 1
            # exponential-ish backoff sampai 5 menit
            backoff = min(ERROR_BACKOFF * (1 + consecutive_fails // 3), 300)
            delay = backoff
            print(f"[BACKOFF] {consecutive_fails} fail beruntun, sleep {delay:.1f}s")

        if _stop:
            break

        if delay > 0:
            print(f"[WAIT] {delay:.1f}s sebelum run berikutnya...")
            for _ in range(int(delay)):
                if _stop:
                    break
                time.sleep(1)

    ended_at = datetime.now()
    print("\n" + "=" * 60)
    print(f"BERHENTI")
    print(f"Started   : {started_at.isoformat()}")
    print(f"Ended     : {ended_at.isoformat()}")
    print(f"Duration  : {ended_at - started_at}")
    print(f"Session   : success={success} failed={failed}")
    print(f"Total keys: {count_existing_keys()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
