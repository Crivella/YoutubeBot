"""Reusable filters for django queries"""
import logging

from django.db import models as m

logger = logging.getLogger('bot')

def ytsong_odby_title(queryset: m.QuerySet, asc: str = '', server = None) -> m.QuerySet:
    """Filter queryset by title"""
    logger.debug(f'Ordering queryset by title `{asc or "+"}`')
    res = queryset
    res = res.annotate(title=m.F('manual_title') or m.F('original_title'))
    res = res.order_by(f'{asc}title')
    return res

def ytsong_odby_duration(queryset: m.QuerySet, asc: str = '', server = None) -> m.QuerySet:
    """Filter queryset by duration"""
    logger.debug(f'Ordering queryset by duration `{asc or "+"}`')
    res = queryset
    res = res.order_by(f'{asc}duration')
    return res

def ytsong_odby_times_played(queryset: m.QuerySet, asc: str = '-', server = None) -> m.QuerySet:
    """Filter queryset by times played"""
    logger.debug(f'Ordering queryset by times played `{asc or "+"}`')
    res = queryset
    pv_query = m.Q(playevent__song=m.F('id'))
    if server:
        pv_query &= m.Q(playevent__server=server)
    res = res.annotate(times_played=m.Count(
        m.Case(
            m.When(pv_query, then=1),
            output_field=m.IntegerField(),
        )
    ))
    res = res.order_by(f'{asc}times_played')
    return res

def ytsong_odby_times_added(queryset: m.QuerySet, asc: str = '-', server = None) -> m.QuerySet:
    """Filter queryset by times added"""
    logger.debug(f'Ordering queryset by times added `{asc or "+"}`')
    res = queryset
    pv_query = m.Q(playlistthrough__song=m.F('id'))
    if server:
        pv_query &= m.Q(playlistthrough__playlist__server=server)
    res = res.annotate(times_added=m.Count(
        m.Case(
            m.When(pv_query, then=1),
            output_field=m.IntegerField(),
        )
    ))
    res = res.order_by(f'{asc}times_added')
    return res

def ytsong_odby_last_played(queryset: m.QuerySet, asc: str = '-', server = None) -> m.QuerySet:
    """Filter queryset by last played"""
    logger.debug(f'Ordering queryset by last played `{asc or "+"}`')
    res = queryset
    pv_query = m.Q(playevent__song=m.F('id'))
    if server:
        pv_query &= m.Q(playevent__server=server)
    res = res.annotate(last_played=m.Max(
        m.Case(
            m.When(pv_query, then=m.F('playevent__date')),
            default=m.Value('1970-01-01T00:00:00Z'),
            output_field=m.DateTimeField(),
        )
    ))
    res = res.order_by(f'{asc}last_played')
    return res

def ytsong_odby_random(queryset: m.QuerySet, asc: str = '', server = None) -> m.QuerySet:
    """Filter queryset by random"""
    logger.debug(f'Ordering queryset by random `{asc or "+"}`')
    res = queryset
    res = res.order_by('?')
    return res

song_order_map = {
    'times_played': ytsong_odby_times_played,
    'times_added': ytsong_odby_times_added,
    'last_played': ytsong_odby_last_played,
    'random': ytsong_odby_random,
    'title': ytsong_odby_title,
    'duration': ytsong_odby_duration,
}

song_order_desc = {
    'title': 'Sort by title',
    'duration': 'Sort by duration',
    'last_played': 'Sort by last played',
    'times_played': 'Sort by times played',
    'times_added': 'Sort by times added to playlists',
    'random': 'Sort randomly',
}
