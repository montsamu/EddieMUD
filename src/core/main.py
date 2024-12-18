"""A simple telnetlib3 server"""

import asyncio
from functools import partial
import json
import inspect
from telnetlib3 import create_server
from telnetlib3.server import TelnetServer
from telnetlib3.telopt import WONT, ECHO, SGA
from . import commands
from .objects import Area, Door, Room, Player, MobDefinition, ObjDefinition, Obj

class Client:
    def __init__(self, world, reader, writer):
        self.world = world
        self.reader = reader
        self.writer = writer
        self.connected = False
        self.player = None
    async def loop(self):
        self.writer.write(f"\rName: ")
        await self.writer.drain()
        name = await self.reader.readline()
        name = name.strip()
        if not name:
            await self.send_line("No name entered. Goodbye.")
        else:
            await self.send_line(f"Welcome, {name}.")
        # TODO: check name not already taken / password
        self.connected = True
        # name, description, definition, inventory, equipment, stats, flags...
        self.player = Player(self, self.world.start_room, name, "human fighter", self.world.mob_definitions[0], [Obj(self.world.obj_definitions[0])],{'right_hand':Obj(self.world.obj_definitions[1])},{})
        for p in self.player.room.players:
            if p is not self.player:
                await p.client.send_line(f"{self.player.name} appears out of the void.")
        await commands.do_look(self, "")
        while self.connected:
            msg = await self.reader.readline()
            if msg == "":
                self.connected = False
                self.player.room.players.remove(self.player)
                for p in self.player.room.players:
                    if p is not self.player:
                        await p.client.send_line(f"{self.player.name} disappears though you did not see him leave.")
                self.reader.feed_eof()
                self.writer.close()
                return
            msg = msg.strip()
            await self.handle(msg)

    async def handle(self, msg):
        if msg in ["n","north","s","south","e","east","w","west","u","up","d","down"]:
            msg = "move " + msg
        elif msg.startswith("'"):
            msg = "say " + msg[1:]
        words = msg.split(" ", 1)
        cmd = words[0]
        target = words[1].strip() if len(words) > 1 else ""
        c = self.world.commands_table.get(cmd)
        if c is None:
            await self.send_line(f"No such command: {cmd}")
        else:
            await c(self, target)

    async def send_line(self, msg):
        self.writer.write(f"\r{msg}\r\n")
        await self.writer.drain()

class World:
    def __init__(self):
        self.shutdown = False
        self.server = None
        self.clients = []
        self.commands_table = {}
        self.areas = []
        human_def = MobDefinition("human")
        bag_def = ObjDefinition("canvas bag")
        ls_def = ObjDefinition("iron longsword")
        self.mob_definitions = [human_def]
        self.obj_definitions = [bag_def, ls_def]
        self.start_room = None
        a = Area(self, "Chiiron", "The City of Chiiron.")
        fountain_square = Room(a, "Fountain Square")
        library = Room(a, "The Library")
        temple = Room(a, "The Temple")
        east_gate = Room(a, "The East Gate")
        outside_east_gate = Room(a, "Outside the East Gate")
        west_gate = Room(a, "The West Gate")
        outside_west_gate = Room(a, "Outside the West Gate")
        bell_tower = Room(a, "Bell Tower", safe=True)
        archives = Room(a, "Archive Room")
        fountain_square.doors["n"] = Door(fountain_square, library)
        library.doors["s"] = Door(library, fountain_square)
        library.doors["d"] = Door(library, archives)
        archives.doors["u"] = Door(archives, library)
        fountain_square.doors["s"] = Door(fountain_square, temple)
        temple.doors["n"] = Door(temple, fountain_square)
        temple.doors["u"] = Door(temple, bell_tower)
        bell_tower.doors["d"] = Door(bell_tower, temple)
        fountain_square.doors["e"] = Door(fountain_square, east_gate)
        east_gate.doors["w"] = Door(east_gate, fountain_square)
        east_gate.doors["e"] = Door(east_gate, outside_east_gate, closed=True)
        fountain_square.doors["w"] = Door(fountain_square, west_gate)
        west_gate.doors["e"] = Door(west_gate, fountain_square)
        west_gate.doors["w"] = Door(west_gate, outside_west_gate, closed=True)

        self.start_room = fountain_square
        # self.limbo

        functions = inspect.getmembers(commands, inspect.iscoroutinefunction)
        for name, f in functions:
            if name.startswith("do_"):
                self.commands_table[name[3:]] = f

    async def shell(self, reader, writer):
        print(f"shell: {reader}, {writer}")
        writer.iac(WONT, ECHO)
        writer.iac(WONT, SGA)
        client = Client(self, reader, writer)
        self.clients.append(client)
        await client.loop()

    async def loop(self):
        self.server = await create_server(port=6023, shell=self.shell)
        while not self.shutdown:
            await asyncio.sleep(1)
            await self.broadcast("TICK!")
        asyncio.get_event_loop().run_until_complete(self.server.wait_closed())

    async def broadcast(self, msg):
        for c in [c for c in self.clients if c.connected == True]:
            await c.send_line(msg)

    async def ncast(self, client, client_msg, others_msg):
        for c in [c for c in self.clients if c.connected == True and c is not client]:
            await c.send_line(others_msg)
        await client.send_line(client_msg)

if __name__=="__main__":
    world = World()
    asyncio.get_event_loop().run_until_complete(world.loop())
