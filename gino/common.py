import os
import typing as T
import logging
from pathlib import Path
import shelve
import time

from datetime import datetime, timezone
import dateparser

# pip install python-dotenv
import dotenv

logger = logging.getLogger()

INTER_RUN_INTERVAL_SEC = 300

LINKED_WITH_NOTION = "notion:opened"
WAITING_FOR_TRIAGE = "waiting-for-triage"
CLOSED_IN_NOTION = "notion:closed"


def load_config():
    """Load configuration"""
    envfiles = [
        Path(__file__).parent.parent / ".env",
        Path.home() / ".config" / "gino" / "env",
    ]
    for envfile in envfiles:
        if envfile.exists():
            logging.info(f"Reading env from {envfile}")
            dotenv.load_dotenv(envfile)
            return

    raise RuntimeError(f"At least of these these env file is required: {envfiles}")


def get_config(key: str) -> str:
    """Get configuration for a given key"""
    if key not in os.environ:
        logging.warn(f"Key {key} not found in env variable. Reloading config...")
        load_config()
    return os.environ[key]


def parse_date(date: T.Optional[str]):
    if not date:
        return None
    return dateparser.parse(date).replace(tzinfo=timezone.utc)


def now_utc():
    return datetime.now(timezone.utc)


def from_now_mins(date_utc) -> int:
    return (now_utc() - parse_date(date_utc)).total_seconds() / 60


def shelve_it(file_name, expiry_mins=10):
    now = time.time()
    fname = Path(file_name + ".dat")
    print(f"Selving using {file_name}")
    if fname.exists():
        ctime = fname.stat().st_ctime
        if (now - ctime) > (expiry_mins * 60):
            for p in Path().glob(file_name + "*"):
                p.unlink()

    d = shelve.open(file_name)

    def decorator(func, *args, **kwargs):
        def new_func(param, *args, **kwargs):
            if param not in d:
                d[param] = func(param, *args, **kwargs)
            else:
                logging.info(f"using selve for {param}")
            return d[param]

        return new_func

    return decorator


STORE_NAME = "gino.shelve"


def store(key, val):
    with shelve.open(STORE_NAME) as db:
        db[key] = val


def load(key):
    with shelve.open(STORE_NAME) as db:
        if key in db:
            return db[key]
    return None
