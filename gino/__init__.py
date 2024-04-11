import logging
import typing as T
import gino.common
from rich.logging import RichHandler

# writing to stdout
FORMAT: T.Final[str] = "%(message)s"
logging.basicConfig(level="INFO", format=FORMAT, handlers=[RichHandler(markup=True)])
