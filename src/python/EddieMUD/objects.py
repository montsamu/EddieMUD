
class Area:
    def __init__(self, world, name, description, **flags):
        self.world = world
        self.world.areas.append(self)
        self.name = name
        self.description = description
        self.flags = {"open":True}
        for k,v in flags.items():
            self.flags[k] = v
        self.rooms = []

class Door:
    # closed = False
    # closable = False
    # openable = False
    def __init__(self, room_start, room_end, **flags): # closed=False, closable=False, openable=False):
        self.flags = {"closed":False, "closable":False, "openable":False}
        self.room_start = room_start
        self.room_end = room_end
        for k,v in flags.items():
            print(k,v)
            self.flags[k] = v
        # self.closed = closed
        # self.closable = closable
        # self.openable = openable
    def is_closed(self):
        return self.flags["closed"]

class Room:
    def __init__(self, area, name, description=None, **flags):
        self.area = area
        self.area.rooms.append(self)
        self.name = name
        self.description = description
        self.flags = {}
        for k, v in flags.items():
            print(k,v)
            self.flags[k] = v
        self.players = []
        self.mobs = []
        self.objects = []
        self.doors = {}
        self.actions = []
        self.resets = []

class Player:
    def __init__(self, client, room, name):
        self.client = client
        self.room = room
        room.players.append(self)
        self.name = name
    def is_fighting(self):
        return False
    def is_mobile(self):
        return True
    def is_awake(self):
        return True
    def is_standing(self):
        return True

