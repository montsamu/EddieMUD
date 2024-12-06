
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
            print("TICK")
            with db_session:
                for mob_morphology in select(m for m in Morphology):
                    print(f"Morphology: {mob_morphology.name}")
                    # print(mob_morphology.active_morphology)
                for area in select(a for a in AreaDefinition):
                    print(f"Area: {area}")
                    for room in area.rooms:
                        print(f"Room: {room}")
            await asyncio.sleep(1)

