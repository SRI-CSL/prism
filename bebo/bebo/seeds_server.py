
#  Copyright (c) 2019-2023 SRI International.

import argparse
import logging
import quart
import quart_trio
import sys
import trio    # type: ignore

import bebo.seeds
import bebo.util

from typing import List

class SeedsServer:
    async def main(self, argv: List[str]):
        parser = argparse.ArgumentParser(description='bebo server')
        parser.add_argument('--address', '-a', metavar='ADDRESS',
                            default='0.0.0.0',
                            help='the address to listen on')
        parser.add_argument('--seeds', '-s', metavar='SEED',
                            default='seeds.json',
                            help='JSON file with neighbor seeds information')
        args = parser.parse_args(argv)
        host = bebo.util.hostify(args.address)
        format = f'{host} %(asctime)s %(name)s %(levelname)s %(message)s'
        logging.basicConfig(filename=f'{host}.seeds.log',
                            level=logging.INFO, format=format)
        self.seeds = bebo.seeds.Seeds(args.seeds)
        async with trio.open_nursery() as nursery:
            nursery.start_soon(app.run_task, host,
                               bebo.util.HTTP_SEEDS_PORT,
                               False, False)

server = SeedsServer()
app = quart_trio.QuartTrio('bebo-seeds')

@app.route('/seeds')
async def seeds():
    return quart.jsonify({'seeds': list(server.seeds.all_seeds)}), 200

def main():
    try:
        trio.run(server.main, sys.argv[1:])
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
