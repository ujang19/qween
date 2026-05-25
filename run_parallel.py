"""
QwenCloud Parallel Bulk Signup
N workers parallel, masing-masing jalanin signup flow yang sama dengan qwencloud_bulk.py.
Reuse semua helper (make_email, wait_otp, run_signup, db_save, dll) dari module utama.
"""
import os, time, random, shutil, signal
from multiprocessing import Process, Value, Lock
from dotenv import load_dotenv

load_dotenv()

# Reuse semua helper yang sudah teruji dari qwencloud_bulk
from qwencloud_bulk import (
    make_email, wait_otp, cleanup_email,
    run_signup, db_init, db_save,
)

TOTAL_ACCOUNTS = int(os.getenv("TOTAL_ACCOUNTS", "1000"))
WORKERS        = int(os.getenv("WORKERS", "3"))
RUN_TIMEOUT    = int(os.getenv("RUN_TIMEOUT", "240"))  # detik per akun


def worker(worker_id, n_accounts, success_counter, failed_counter, lock):
    print(f"[W{worker_id}] Start, target {n_accounts} akun")

    for i in range(1, n_accounts + 1):
        print(f"\n[W{worker_id}][{i}/{n_accounts}] Mulai...")

        email_id = None
        profile_dir = f"./profiles/w{worker_id}_{int(time.time())}_{random.randint(1000, 9999)}"

        try:
            email_id, email_addr = make_email()
            if not email_id:
                with lock:
                    failed_counter.value += 1
                print(f"[W{worker_id}] SKIP - gagal buat email")
                continue

            # Timeout per run
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Run timeout {RUN_TIMEOUT}s")
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(RUN_TIMEOUT)
            try:
                api_key = run_signup(email_addr, email_id, profile_dir, run_idx=f"w{worker_id}_{i}")
            finally:
                signal.alarm(0)

            if api_key:
                db_save(email_addr, api_key)
                with open("api_keys.txt", "a") as f:
                    f.write(f"{email_addr}|{api_key}\n")
                with lock:
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
            print(f"[STATS] Success: {success_counter.value} | Failed: {failed_counter.value}")

        if i < n_accounts:
            delay = random.uniform(3, 5)
            time.sleep(delay)

    print(f"[W{worker_id}] SELESAI")


def main():
    print("=" * 60)
    print(f"QWENCLOUD PARALLEL SIGNUP")
    print(f"Total akun : {TOTAL_ACCOUNTS}")
    print(f"Workers    : {WORKERS}")
    print(f"Per worker : ~{TOTAL_ACCOUNTS // WORKERS} akun")
    print(f"Timeout    : {RUN_TIMEOUT}s per akun")
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
        )
        processes.append(p)

    # Stagger start agar bypass captcha tidak hammered bersamaan
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
    print("=" * 60)


if __name__ == "__main__":
    main()
