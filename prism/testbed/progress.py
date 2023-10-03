#  Copyright (c) 2019-2023 SRI International.

import trio
import progressbar


class Progress:
    def __init__(self, total_progress: int, total_seconds: float):
        self.total_progress = total_progress
        self.total_seconds = total_seconds
        (self._in, self._out) = trio.open_memory_channel(self.total_progress + 1)

        self.widgets = [
            '[', progressbar.SimpleProgress(), '] ',
            progressbar.Bar(), ' ',
            progressbar.Timer(format=f"%(total_seconds_elapsed)d/{self.total_seconds}s")
        ]

    async def update(self, increment=1):
        await self._in.send(increment)

    async def run(self):
        progress = 0

        with progressbar.ProgressBar(max_value=self.total_progress,
                                     widgets=self.widgets,
                                     redirect_stdout=True) as bar:
            while progress < self.total_progress:
                try:
                    while True:
                        progress += self._out.receive_nowait()
                except trio.WouldBlock:
                    pass

                bar.update(progress)
                await trio.sleep(0.1)
