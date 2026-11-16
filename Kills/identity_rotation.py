import time
import random
import pickle
from curl_cffi import requests as cffi_requests


# ---- Identity rotation ----

IMPERSONATE_OPTIONS = ['chrome120', 'chrome119', 'chrome116', 'safari15_5', 'edge99']

UA_MAP = {
    'chrome120': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'chrome119': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'chrome116': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
    'safari15_5': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15',
    'edge99': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36 Edg/99.0.1150.30',
}


def new_identity(base_headers: dict, proxies: dict | None = None):
    """
    Returns a fresh (session, headers) pair with a matched TLS
    impersonation + User-Agent, so nothing mismatches.
    base_headers: your existing headers dict (Referer/Origin/Accept etc.)
                  — everything except User-Agent is kept as-is.
    proxies: optional dict like {'http': '...', 'https': '...'}
    """
    imp = random.choice(IMPERSONATE_OPTIONS)
    session = cffi_requests.Session(impersonate=imp, proxies=proxies)
    headers = dict(base_headers)
    headers['User-Agent'] = UA_MAP[imp]
    return session, headers


def jitter_sleep(low=2.0, high=4.0):
    """Randomized delay so request timing doesn't look robotic."""
    time.sleep(random.uniform(low, high))


# ---- Checkpointing ----

def save_checkpoint(data, filename):
    with open(filename, 'wb') as f:
        pickle.dump(data, f)


def load_checkpoint(filename, default):
    try:
        with open(filename, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return default


# ---- Rotation driver ----

def should_rotate(i: int, every: int = 50) -> bool:
    return i % every == 0