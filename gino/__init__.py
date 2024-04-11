import logging
import typing as T
import gino.common
from rich.logging import RichHandler

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

sentry_logging = LoggingIntegration(
    level=logging.INFO,  # Capture info and above as breadcrumbs
    event_level=logging.WARNING,  # Send errors as events
)
sentry_sdk.init(
    dsn="https://343e5e415aaf4289b639d304dad9cecf@traces.subcom.link/14",
    integrations=[
        sentry_logging,
    ],
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production,
    traces_sample_rate=0.1,
)

# writing to stdout
FORMAT: T.Final[str] = "%(message)s"
logging.basicConfig(level="INFO", format=FORMAT, handlers=[RichHandler(markup=True)])

gino.common.load_config()
