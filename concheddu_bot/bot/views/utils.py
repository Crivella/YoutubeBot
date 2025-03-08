import logging
import os

try:
    MAX_LIST_OPT = int(os.getenv('BOT_MAX_LIST_OPT', 10))
except ValueError:
    MAX_LIST_OPT = 10
if MAX_LIST_OPT > 25:
    MAX_LIST_OPT = 25

logger = logging.getLogger('bot')

def elide(text: str, length: int = 60) -> str:
    if len(text) > length:
        return text[:length - 3] + '...'
    return text

def pad(text: str, length: int = 60) -> str:
    return text.rjust(length, '.')

def elide_and_pad(text: str, length: int = 60) -> str:
    return elide(pad(text, length), length)
