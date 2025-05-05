import asyncio
import logging

from rich.logging import RichHandler

from vyxalbot3 import main
from vyxalbot3.settings import Settings, SupplementaryConfiguration

def launch():
    logging.basicConfig(
        level="DEBUG",
        format="[%(name)s] %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    asyncio.run(main(Settings(), SupplementaryConfiguration()))  # type: ignore