"""Global runtime server variables."""

memo = {}

class QueuedServer:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'discord_id'):
            raise AttributeError('discord_id attribute not found')
        memo.setdefault(self.discord_id, {
            'queue': [],
            'idx': 0,
            'loop_all': False,
            'loop_one': False
        })

    @property
    def queue(self) -> list:
        """Return the queue"""
        return memo[self.discord_id]['queue']
    @queue.setter
    def queue(self, value):
        memo[self.discord_id]['queue'] = value

    @property
    def idx(self) -> int:
        """Return the index"""
        return memo[self.discord_id]['idx']
    @idx.setter
    def idx(self, value):
        memo[self.discord_id]['idx'] = value

    @property
    def loop_all(self) -> bool:
        """Return the loop all status"""
        return memo[self.discord_id]['loop_all']
    @loop_all.setter
    def loop_all(self, value):
        memo[self.discord_id]['loop_all'] = value

    @property
    def loop_one(self) -> bool:
        """Return the loop one status"""
        return memo[self.discord_id]['loop_one']
    @loop_one.setter
    def loop_one(self, value):
        memo[self.discord_id]['loop_one'] = value

    def get_next_song(self):
        """Return the next song"""
        if not self.queue:
            return None
        if self.loop_one:
            return self.queue[self.idx]
        self.idx += 1
        if self.idx >= len(self.queue):
            if self.loop_all:
                self.idx = 0
            else:
                return None
        song = self.queue[self.idx]
        return song

    def add_song(self, song):
        """Add a song to the queue"""
        self.queue.append(song)

    def jump(self, pos: int):
        """Jump to a position in the queue"""
        self.idx += pos - 1
        if self.idx >= len(self.queue):
            self.idx = len(self.queue) - 1
        if self.idx < 0:
            self.idx = 0

    def set_loop_all(self, value: bool):
        """Set loop all"""
        self.loop_all = value

