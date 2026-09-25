"""python -m proxybot – reads the settings from the environment and runs until stopped."""

import logging

from .bot import ProxyBot
from .config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    ProxyBot(settings).run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
