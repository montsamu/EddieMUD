
import asyncio
from pony.orm import db_session, select
from model import *

class Engine:
    def __init__(self, db):
        self.db = db
        self.running = False
        self.shutdown = False

    async def loop(self):
        self.running = True
        while not self.shutdown:
            await asyncio.sleep(1)
            print("TICK")
            with db_session:
                for area in select(a for a in Area):
                    print(f"Area: {area}")
                    for room in area.rooms:
                        print(f"Room: {room}")

