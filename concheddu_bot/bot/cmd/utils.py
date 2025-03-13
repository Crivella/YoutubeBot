"""Music commands for the bot"""
import logging
import re

logger = logging.getLogger('bot')

# TODO: need to add proper invalidation before using this
#  probably based on django signals on when playlists are updated
# server_playlist_cache = {}

def sanitize_ffmpeg_filter(afilt: str):
    """Sanitize the ffmpeg filter"""
    if afilt is None:
        return
    rgx = re.compile(r'^[a-z0-9=_:,\-\.]+$')
    res = afilt
    res = res.replace(';', '')
    res = res.replace('|', '')
    res = res.replace('"', '')
    res = res.replace("'", '')

    if not rgx.match(res):
        logger.warning(f'Invalid ffmpeg filter: {afilt}')
        raise ValueError(f'Invalid ffmpeg filter: {afilt}')
    logger.debug(f'Sanitized ffmpeg filter: {afilt} -> {res}')

    return res
