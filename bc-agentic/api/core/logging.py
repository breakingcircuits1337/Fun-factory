import sys
from loguru import logger


def configure_logging():
    logger.remove()
    logger.add(sys.stdout, format="{message}", serialize=True, level="INFO")
    return logger
