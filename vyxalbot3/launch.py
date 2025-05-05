import asyncio
import logging

from rich.logging import RichHandler

from vyxalbot3 import main
from vyxalbot3.settings import Settings, SupplementaryConfiguration

def launch():
    settings = Settings() # type: ignore
    logging.basicConfig(
        level=settings.log_level,
        format="[%(name)s] %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    logging.getLogger("httpx").setLevel("WARN")

    asyncio.run(main(settings, SupplementaryConfiguration())) # type: ignore