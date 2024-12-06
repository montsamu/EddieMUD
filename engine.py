
import asyncio
from enum import Enum, auto
from pony.orm import db_session, select
from model import *
from telnetlib3 import create_server
from telnetlib3.telopt import WONT, ECHO, SGA

class ClientState(Enum):
    CONNECTING = auto() # -> CREATING or AUTHENTICATING
    CREATING = auto() # -> LOADED
    AUTHENTICATING = auto() # -> LOADED
    LOADED = auto() # -> CONNECTED
    CONNECTED = auto()
    DISCONNECTED = auto()

class Client:
    def __init__(self, engine, reader, writer):
        self.engine = engine
        self.reader = reader
        self.writer = writer
        self.state = ClientState.CONNECTING
        self.player = None
        self.engine.clients.append(self)

    async def send(self, msg):
        self.writer.write(msg)
        await self.writer.drain()

    async def send_line(self, msg=""):
        await self.send(f"\r{msg}\r\n")

    async def send_lines(self, *msgs):
        await self.send_line("\r\n".join(msgs))

    async def read_line(self):
        msg = await self.reader.readline()
        msg = msg.strip()
        return msg

    async def shell(self):
        await self.welcome_screen()
        print(f"Client {self} reached terminal state: {self.state}")
        self.reader.feed_eof()
        self.writer.close()

    async def welcome_screen(self):
        # TODO check for disconnect
        await self.send_line("\r\nW E L C O M E") # TODO center, etc.
        await self.send_lines(
            "",
            "  By what name are you called, traveller?",
            "",
            "  [ Enter a name. If known, you will be asked for your password.",
            "    If unknown, you will enter player creation. ]",
            "")
        await self.send("      Name: ")
        name = await self.read_line() # TODO timeout
        if not name:
            await self.send_line("No choice made. Goodbye!") # rename nameless and begone!
            self.state = ClientState.DISCONNECTED
        elif not self.engine.check_player_name_is_valid(name):
            await self.send_line("*** INVALID NAME ***")
            await self.welcome_screen()
        elif self.engine.check_player_name_is_available(name):
            await self.create_player(name)
        else:
            self.state = ClientState.AUTHENTICATING
            password = await self.read_line() # TODO timeout, input masking
            if self.engine.check_player_password(name, password):
                await self.send_line(f"\r\nWelcome, {name}!")
                self.player = self.engine.load_player(name)
                await self.loop()
            else:
                await self.send_line("No matching player/password found.")
                await self.welcome_screen()

    async def create_player(self, name):
        self.state = ClientState.CREATING
        await self.send_line("\r\nC R E A T E   A   P L A Y E R") # TODO center, refactor
        await self.send_line()
        await self.send_lines(
                "",
                f"  Welcome, '{name}'! We do not seem to have met before...",
                "",
                "   ...let me know a phrase by which I can recognize you?",
                "",
                "  [ Enter and confirm a password. If an empty password is entered,",
                "    return to the welcome screen. ]",
                "",
                "")
        confirmed_password = None
        while not confirmed_password:
            await self.send("  Password: ") # TODO indent, enable input masking/cancel echo
            password = await self.read_line() # TODO timeout, mask
            if not password:
                await self.welcome_screen()
            elif not self.engine.check_password_is_valid(password):
                await self.send_line("Invalid password. Try again?")
            else:
                await self.send("\r   Confirm: ") # TODO indent/align, enable input masking...
                confirm_password = await self.read_line() # TODO timeout, handle input masking here?
                if password != confirm_password:
                    await self.send_line("Confirm does not match. Try again.")
                else:
                    confirmed_password = password
        self.player = self.engine.create_player(name, password)
        await self.loop()

    async def loop(self):
        self.state = ClientState.CONNECTED
        while self.state == ClientState.CONNECTED:
            await self.send("\rCommand: ")
            msg = await self.read_line()
            if msg == "":
                self.state = ClientState.DISCONNECTED
            else:
                await self.handle(msg)

    async def handle(self, msg):
        await self.send_line(f"You typed: {msg}")

class Engine:
    def __init__(self, db):
        self.db = db
        self.running = False
        self.shutdown = False
        self.server = None
        self.clients = []

    def check_password_is_valid(self, password):
        return len(password) > 1 and len(password) < 128

    def check_player_name_is_valid(self, name):
        return len(name) > 1 and len(name) < 32

    def check_player_name_is_available(self, name):
        with db_session: # TODO async call?
            return not Player.exists(name=name)

    def check_player_password(self, name, password):
        return name == password

    def load_player(self, name):
        with db_session:
            return Player['name':name]

    def create_player(self, name, password):
        with db_session:
            return Player(name=name, password=password)

    async def shell(self, reader, writer):
        writer.iac(WONT, ECHO)
        writer.iac(WONT, SGA)
        client = Client(self, reader, writer)
        await client.shell()
        self.clients.remove(client)

    async def run(self):
        self.running = True
        self.server = await create_server(port=6023, shell=self.shell)

        while not self.shutdown:
            print("TICK")
            print("CLIENTS:", len(self.clients))
            for client in self.clients:
                print(client, client.state)
            with db_session:
                for area in select(a for a in AreaDefinition): # TODO loop through ACTIVE areas...
                    print(f"Area: {area.name}")
                    for room in area.rooms:
                        print(f"  Room: {room.name}")
            await asyncio.sleep(1)

