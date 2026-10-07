"""Point d'entrée : `python -m jarvis`."""

import logging

import discord

from jarvis.bot import Jarvis
from jarvis.config import Config


def main() -> None:
    discord.utils.setup_logging(level=logging.INFO)
    config = Config.from_env()
    Jarvis(config).run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
