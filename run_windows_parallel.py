"""
QwenCloud Auto Signup - Windows Parallel Version
- No proxy
- 3 akun sekaligus (multiprocessing, Windows-compatible)
- Simpan ke api_keys.txt + Turso DB
- Compatible Windows (no SIGALRM, no fcntl)

Requirements:
    pip install cloakbrowser playwright requests python-dotenv libsql-client
    playwright install chromium
"""
import os, time, random, shutil
from multiprocessing import Process, Value, Lock
from dotenv import load_dotenv

load_dotenv()

# Reuse semua helper dari run_windows
from run_windows import (
    make_email, wait_otp, cleanup_email,
    run_signup, db_init, db_save,
    TOTAL_ACCOUNTS, KEYS_FILE
)

WORKERS     = int(os.getenv("WORKERS", "3"))
RUN_TIMEOUT = int(os.getenv("RUN_TIMEOUT", "300"))  # detik per akun (no SIGALRM, pakai threading.Timer)


def count_keys():
    if not os.path.exists(KEYS_FILE):
        return 0
    n = 0
    with open(KEYS_FILE) as f:
        for line in f:
            if line.strip() and "|" in line:
                n += 1
    return n


def worker(worker_id, n_accounts, success_counter, failed_counter, lock):
    import threading

    print(f"[W{worker_id}] Start, target {n_accounts} akun")

    for i in range(1, n_accounts + 1):
        print(f"\n[W{worker_id}][{i}/{n_accounts}] Mulai...")

        email_id    = None
        profile_dir = f"./profiles/w{worker_id}_{int(time.time())}_{random.randint(1000, 9999)}"
        api_key     = None
        timed_out   = [False]

        try:
            email_id, email_addr = make_email()
            if not email_id:
                with lock:
                    failed_counter.value += 1
                print(f"[W{worker_id}] SKIP - gagal buat email")
                continue

            # Windows-compatible timeout via threading.Timer
            result_holder = [None]
            exc_holder    = [None]

            def run_in_thread():
                try:
                    result_holder[0] = run_signup(
                        email_addr, email_id, profile_dir,
                        run_idx=f"w{worker_id}_{i}"
                    )
                except Exception as e:
                    exc_holder[0] = e

            t = threading.Thread(target=run_in_thread, daemon=True)
            t.start()
            t.join(timeout=RUN_TIMEOUT)

            if t.is_alive():
                timed_out[0] = True
                print(f"[W{worker_id}] TIMEOUT setelah {RUN_TIMEOUT}s")
                with lock:
                    failed_counter.value += 1
                # thread daemon akan mati sendiri saat process selesai
                continue

            if exc_holder[0]:
                raise exc_holder[0]

            api_key = result_holder[0]

            if api_key:
                db_save(email_addr, api_key)
                with lock:
                    with open(KEYS_FILE, "a") as f:
                        f.write(f"{email_addr}|{api_key}\n")
                    success_counter.value += 1
                print(f"[W{worker_id}] SUCCESS - {email_addr} | {api_key}")
            else:
                with lock:
                    failed_counter.value += 1
                print(f"[W{worker_id}] FAIL - tidak dapat API key")

        except Exception as e:
            import traceback
            print(f"[W{worker_id}] ERROR - {e}")
            traceback.print_exc()
            with lock:
                failed_counter.value += 1

        finally:
            if email_id:
                cleanup_email(email_id)
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)

        with lock:
            print(f"[STATS] Success: {success_counter.value} | Failed: {failed_counter.value} | Keys: {count_keys()}")

        if i < n_accounts:
            delay = random.uniform(5, 10)
            print(f"[W{worker_id}] Tunggu {delay:.1f}s...")
            time.sleep(delay)

    print(f"[W{worker_id}] SELESAI")


def main():
    print("=" * 60)
    print(f"QWENCLOUD PARALLEL SIGNUP - WINDOWS VERSION")
    print(f"Total akun : {TOTAL_ACCOUNTS}")
    print(f"Workers    : {WORKERS}")
    print(f"Per worker : ~{TOTAL_ACCOUNTS // WORKERS} akun")
    print(f"Timeout    : {RUN_TIMEOUT}s per akun")
    print(f"No proxy   : direct connection")
    print("=" * 60)

    db_init()

    success_counter = Value('i', 0)
    failed_counter  = Value('i', 0)
    lock = Lock()

    accounts_per_worker = TOTAL_ACCOUNTS // WORKERS
    remainder = TOTAL_ACCOUNTS % WORKERS

    processes = []
    for w in range(WORKERS):
        count = accounts_per_worker + (1 if w < remainder else 0)
        p = Process(
            target=worker,
            args=(w + 1, count, success_counter, failed_counter, lock),
            daemon=False
        )
        processes.append(p)

    # Stagger start 5 detik antar worker biar tidak hammered bersamaan
    for p in processes:
        p.start()
        time.sleep(5)

    for p in processes:
        p.join()

    print("\n" + "=" * 60)
    print(f"SELESAI!")
    print(f"Success : {success_counter.value}")
    print(f"Failed  : {failed_counter.value}")
    print(f"Total   : {TOTAL_ACCOUNTS}")
    print(f"Keys    : {count_keys()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
