"""Reusable filters for django queries"""
import logging

from django.db import models as m

logger = logging.getLogger('bot')

def song_annotate_title(queryset: m.QuerySet) -> m.QuerySet:
    """Annotate the title"""
    if hasattr(queryset, 'query') and 'title' in queryset.query.annotations:
        return queryset
    res = queryset
    res = res.annotate(title=m.Case(
        m.When(m.Q(manual_title__isnull=False), then=m.F('manual_title')),
        default=m.F('original_title'),
        output_field=m.CharField(),
    ))
    return res

def song_annotate_times_played(queryset: m.QuerySet, server_id: int = None) -> m.QuerySet:
    """Annotate the times played"""
    if hasattr(queryset, 'query') and 'times_played' in queryset.query.annotations:
        return queryset
    res = queryset
    pv_query = m.Q(playevent__song=m.F('id'))
    if server_id is not None:
        pv_query &= m.Q(playevent__server_id=server_id)
    res = res.annotate(times_played=m.Count(
        m.Case(
            m.When(pv_query, then=1),
            output_field=m.IntegerField(),
        )
    ))
    return res

def ytsong_odby_title(queryset: m.QuerySet, asc: str = '', server_id: int = None) -> m.QuerySet:
    """Filter queryset by title"""
    logger.debug(f'Ordering queryset by title `{asc or "+"}`')
    res = queryset
    res = song_annotate_title(res)

    ord_func = m.functions.Lower('title')
    ord_func = ord_func if asc == '' else ord_func.desc()

    res = res.order_by(ord_func)
    return res

def ytsong_odby_duration(queryset: m.QuerySet, asc: str = '', server_id: int = None) -> m.QuerySet:
    """Filter queryset by duration"""
    logger.debug(f'Ordering queryset by duration `{asc or "+"}`')
    res = queryset
    res = res.order_by(f'{asc}duration')
    return res

def ytsong_odby_times_played(queryset: m.QuerySet, asc: str = '-', server_id: int = None) -> m.QuerySet:
    """Filter queryset by times played"""
    logger.debug(f'Ordering queryset by times played `{asc or "+"}`')
    res = queryset
    res = song_annotate_times_played(res, server_id=server_id)
    res = res.order_by(f'{asc}times_played')
    return res

def ytsong_odby_times_added(queryset: m.QuerySet, asc: str = '-', server_id: int = None) -> m.QuerySet:
    """Filter queryset by times added"""
    logger.debug(f'Ordering queryset by times added `{asc or "+"}`')
    res = queryset
    pv_query = m.Q(playlistthrough__song=m.F('id'))
    if server_id:
        pv_query &= m.Q(playlistthrough__playlist__server_id=server_id)
    res = res.annotate(times_added=m.Count(
        m.Case(
            m.When(pv_query, then=1),
            output_field=m.IntegerField(),
        )
    ))
    res = res.order_by(f'{asc}times_added')
    return res

def ytsong_odby_last_played(queryset: m.QuerySet, asc: str = '-', server_id: int = None) -> m.QuerySet:
    """Filter queryset by last played"""
    logger.debug(f'Ordering queryset by last played `{asc or "+"}`')
    res = queryset
    pv_query = m.Q(playevent__song=m.F('id'))
    if server_id:
        pv_query &= m.Q(playevent__server_id=server_id)
    res = res.annotate(last_played=m.Max(
        m.Case(
            m.When(pv_query, then=m.F('playevent__date')),
            default=m.Value('1970-01-01T00:00:00Z'),
            output_field=m.DateTimeField(),
        )
    ))
    res = res.order_by(f'{asc}last_played')
    return res

def ytsong_odby_random(queryset: m.QuerySet, asc: str = '', server_id: int = None) -> m.QuerySet:
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

song_order_descr = {
    'title': 'Sort by title',
    'duration': 'Sort by duration',
    'last_played': 'Sort by last played',
    'times_played': 'Sort by times played',
    'times_added': 'Sort by times added to playlists',
    'random': 'Sort randomly',
}

async def get_all_songs(
        query: m.QuerySet,
        limit: int = None,
        sorting: str = 'title',
        asc: str = None,
        filter_title: str = None,
        server_id: int = None,
        times_played: bool = True
    ) -> m.QuerySet:
    """Return N songs from the playlist with custom sorting

    Args:
        query (m.QuerySet): The original query set of YTSong objects
        limit (int, optional): Limit the number of results. Defaults to None.
        sorting (str, optional): The sorting method. Defaults to 'title'.
        asc (str, optional): The sorting direction. Defaults to None.
        filter_title (str, optional): Filter by title. Defaults to None.
        server_id (int, optional): The server id. Defaults to None.
        times_played (bool, optional): Include times played. Defaults to True.

    Returns:
        m.QuerySet: The filtered / ordered queryset
    """
    if isinstance(query, m.QuerySet):
        res = query
    elif isinstance(query, m.Manager):
        res = query.get_queryset()
    else:
        raise ValueError('Invalid queryset')
    if filter_title:
        res = res.filter(
            m.Q(original_title__icontains=filter_title) |
            m.Q(manual_title__icontains=filter_title)
        )
    kwargs = {}
    if asc is not None:
        kwargs['asc'] = '' if asc else '-'
    res = song_order_map[sorting](res, server_id=server_id, **kwargs)
    if limit:
        res = res[:limit]

    if times_played:
        res = song_annotate_times_played(res, server_id=server_id)

    res = [a async for a in res]

    return res
