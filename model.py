
from datetime import datetime
from copy import deepcopy
import json
import re
import os
from pony.orm import Database, Required, Set, Optional, PrimaryKey, composite_key, Json, StrArray

db = Database()
db._in_init_ = True

# NOTE: when saving a player must also save their objects and pets, skillset and spellbook and prayerbook and songbook and runeset and cookbook and potionbook...
class OnlineEditable(object):
    """Mixin for defining entity hooks to persist in-memory entities to JSON"""
    def after_insert(self):
        if not self._database_._in_init_:
            print("storing",self,"to json...")
            # storing PlayerDefinition[2] to json...
            with open(f'data/{self.__class__.__name__}/{self.get_pk()}.json', mode='x') as f:
                json.dump(self.to_dict(), f, sort_keys=True, indent=4, default=str)
    def after_update(self): # TODO: incremental update using TinyDB? log jsondeltas to stream?
        print("updating",self,"to json...")
        with open(f'data/{self.__class__.__name__}/{self.get_pk()}.json', mode='w') as f:
            json.dump(self.to_dict(), f, sort_keys=True, indent=4, default=str)
    def after_delete(self):
        print("deleting",self,"from json...")
        os.remove(f'data/{self.__class__.__name__}/{self.get_pk()}.json') # TODO: stash in recycle bin instead?!

class ContainerBase(db.Entity):
    """Base entity type for entities which contain an inventory of instantiated objects"""
    inventory = Set('Object')

class MobGroup(db.Entity):
    """Ephemeral group of mobs/players"""
    leader = Required('MobBase')
    members = Set('MobBase')

def matching_sub_dict(d, path):
    if path == "/":
        yield None, d
    else:
        split_paths = path.split("/")
        num_splits = len(split_paths)
        for i, split_path in enumerate(split_paths):
            if split_path:
                p = re.compile(split_path)
                if p.groups:
                    for k,v in d.items():
                        m = p.match(k)
                        if m:
                            yield m, d[k]
                else:
                    d = d[split_path]
                    if i+1 == num_splits:
                        yield None, d

def compute_active_morphology(base, delta):
    active_morphology = deepcopy(base) # copy?!
    for path, removes in dict(delta.get('remove', {})).items():
        # OLD: /head/ears ['(left|right)_ear/\\1_ear(lobe|_helix)']
        # NEW: /head/ears/(left|right)_ear ['{0}_ear(lobe|_helix)']
        # /head/face/nose ['(left|right)_nasal_cartilage']
        # /torso/belly ['/bellybutton']
       for m, sub_morphology in matching_sub_dict(active_morphology, path):
           for remove in removes:
               if m is not None:
                   remove = remove.format(*m.groups())
               p = re.compile(remove)
               for k in list(sub_morphology.keys()): # this usage as we plan to modify
                   pm = p.match(k)
                   if pm:
                       del sub_morphology[k]
    for path, replaces in dict(delta.get('replace', {})).items():
        # print("REPLACES:", path, replaces)
        for m, sub_morphology in matching_sub_dict(active_morphology, path): # {'left_breast': {'left_nipple': {}}, 'right_breast': {'right_nipple': {}}}
            # print("sub_morphology:", sub_morphology)
            for k,v in replaces.items(): # {'(left|right)_breast': {'{0}_pectoral': {}}}
                p2 = re.compile(k)
                if p2.groups: # there is a pattern to match
                    for k2 in list(sub_morphology.keys()):
                        m2 = p2.match(k2)
                        if m2: # there is a match
                            v2 = {}
                            for kv2 in v.keys():
                                kv2m = kv2.format(*m2.groups())
                                v2[kv2m] = v[kv2]
                            del sub_morphology[k2]
                            sub_morphology.update(v2)
                else: # no pattern to match
                    del sub_morphology[k]
                    sub_morphology.update(v) # TODO check v for patterns needing replaced?
    for path, adds in dict(delta.get('add', {})).items():
        # print("ADDS:", path, adds)
        for m, sub_morphology in matching_sub_dict(active_morphology, path): # {'left_ear_helix': {}, 'left_ear_tragus': {}, 'left_earlobe': {}, 'right_ear_canal': {}}
            for k,v in adds.items(): # "{0}_ear_tip": {}
                if k in sub_morphology:
                    raise Exception(f"key {k} already in morphology and cannot be added!")
                if m is not None:
                    v2 = v.copy() # TODO check for patterns in there...
                    k2 = k.format(*m.groups())
                    sub_morphology[k2] = v2
                else:
                    sub_morphology[k] = v
    return active_morphology

# TODO these may need to be loaded in dependency order?
class Morphology(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # humanoid, saurianoid, elvenoid, insectoid, equine, avian...
    morphology = Optional(Json, default={}) # can be base or deltas when loading? what about saving?!
    delta = Optional(Json, default={}) # can be base or deltas when loading? what about saving?!
    base = Optional('Morphology') # implies needing to load in dependency order...
    variants = Set('Morphology', lazy=True)
    races = Set('MobRace', lazy=True)
    @property
    def active_morphology(self):
        if self.base is None:
            return self.morphology
        return compute_active_morphology(self.base.active_morphology, self.delta) # TODO: cache? calculate on update...

class MobSize(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # tiny small medium large titan...
    value = Required(int)
    races = Set('MobRace', lazy=True)

# TODO: permanent? categories?
class MobFlag(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # sentinel, aggro...
    description = Optional(str)
    default = Required(bool, default=False)

# TODO: beneficial? permanent? categories?
class MobEffect(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # fire_shield, rage, detect_evil...
    description = Optional(str)
    mobdefs = Set('MobDefinition', lazy=True)
    mobs = Set('MobBase', lazy=True)
    spells = Set('Spell', lazy=True)

class SkillCategory(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    description = Optional(str)
    skills = Set('Skill') # non lazy is ok for finite list

class Skill(OnlineEditable, db.Entity):
    name = PrimaryKey(str)
    category = Required('SkillCategory')
    sets = Set('SkillSetItem', lazy=True)
    description = Optional(str)
    passive = Required(bool, default=False)
    steps = Required(StrArray)
    base_energy_cost = Required(int, default=1)
    base_speed = Required(int, default=100)
    trainers = Set('MobDefinition')

# TODO: would some cats be evil, or things like fire/cold? or: arcane/demonic/angelic/spiritual?
# class SpellCategory(OnlineEditable, db.Entity):
#     name = Required(str, unique=True)
#     description = Optional(str)
#     spells = Set('Spell')

# TODO: target type? program? targets?
class Spell(OnlineEditable, db.Entity):
    name = PrimaryKey(str)
    books = Set('SpellBookItem', lazy=True)
    description = Optional(str)
    # category = Required(SpellCategory)
    effects = Set('MobEffect')
    init_mana_cost = Required(int, default=0)
    base_speed = Required(int, default=0)
    base_mana_leech = Required(int, default=0)
    base_duration = Required(int, default=0)
    cast_steps = Required(StrArray, default=[]) # TODO check these are valid step refs, add helper functions
    prep_steps = Required(StrArray, default=[])
    trainers = Set('MobDefinition')

# TODO: calculate how long it should take per-player (attrs, skills)
# TODO: some impact to durability? of non-consumable reagents?
# TODO: helper function to find where it is used?
class SpellStep(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    step_mana_cost = Required(int)
    requirements = Set('ObjectRequirement')
    target_slot = Optional('ObjectLocation')
    targets_mob = Required(int, default=0) # reach hands towards needs target(s)
    targets_object = Required(int, default=0) # create water needs container(s)
    open_slots = Set('ObjectLocation', reverse='required_open_by_spells') # you need at least one hand free, you must not yet be wearing a crown, etc.
    reagents = Set('ObjectDefinition') # consumes 1 'charge' of each reagent # TODO make this also a general type of object?
    products = Set('ObjectDefinition') # TODO: how to make more than 1 of a given thing...

# things like: 'holding staff' or 'owns rabbit skin'
class ObjectRequirement(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    spells = Set('SpellStep')
    skills = Set('SkillStep')
    equipment_types = Set('ObjectType')
    inventory_types = Set('ObjectType')
    equipment = Set('ObjectDefinition') # TODO: held in the *LEFT* hand?
    inventory = Set('ObjectDefinition')

class SkillSetItem(db.Entity):
    skill = Required('Skill')
    level = Required(int, default=1)
    owner = Required('MobBaseDefinition')
    PrimaryKey(owner, skill)

class SkillStep(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    step_physical_cost = Required(int)
    open_slots = Set('ObjectLocation', reverse='required_open_by_skills') # you need at least one hand free, etc.
    targets_object = Required(int, default=0) # build fire needs container(s)?
    requirements = Set('ObjectRequirement')
    ingredients = Set('ObjectDefinition')
    products = Set('ObjectDefinition') # how to make flaming sword appear directly in hand... TARGET?

class SpellBookItem(db.Entity):
    spell = Required('Spell')
    level = Required(int, default=1)
    owner = Required('MobBaseDefinition')
    PrimaryKey(owner, spell)

class MobRace(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # elf dwarf troll half-dwarf
    description = Required(str)
    parents = Set('MobRace', reverse='children')
    children = Set('MobRace', reverse='parents')
    playable = Required(bool, default=False)
    corpse = Optional('ObjectDefinition')
    morphology = Required('Morphology')
    size = Required('MobSize')
    flags = Required(Json, default={})
    races = Set('MobBaseDefinition', lazy=True)

    def descends_from(self, name):
        if self.name == name:
            return True
        for parent in self.parents:
            if parent.descends_from(name):
                return True
        return False

    def is_undead(self):
        return self.descends_from("undead")

    def is_human(self):
        return self.descends_from("human")

    def is_elf(self):
        return self.descends_from("elf")

    def is_dwarf(self):
        return self.descends_from("dwarf")

    def is_giant(self):
        return self.descends_from("giant")

    def is_angelic(self):
        return self.descends_from("angel")

    def is_demonic(self):
        return self.descends_from("demon")

# TODO: leader
class MobClan(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    members = Set('MobDefinition')

# TODO: leader
class MobNation(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    members = Set('MobDefinition')

# TODO: vows, curses, religions, blessings...
# prayer points...

# base class for definitions of mobs and players
class MobBaseDefinition(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    title = Optional(str) # Sir, Captain
    metadata = Required(Json, default={}) # created_by, etc.
    created_at = Required(datetime, default=datetime.now)
    race = Required('MobRace')
    level = Required(int, default=1)
    experience = Required(int, default=0) # TODO: default in level_table for level?
    skillset = Set('SkillSetItem')
    spellbook = Set('SpellBookItem')
    bamfin = Required(str, default='appears.')
    bamfout = Required(str, default='disappears.')

# archetypes of mobs, like "goblin raider" and "town guard" or unique Dragons etc.
# TODO: mflag use_the?
class MobDefinition(MobBaseDefinition):
    plural = Required(str, unique=True)   # TODO: default with name+s
    # metadata: created_by = Optional('Player', reverse='created_mobs')
    mflags = Required(Json, default={})  # the default flags on load
    effects = Set('MobEffect')           # the default effects on load
    long_s = Required(str, default='is standing here.')
    long_p = Required(str, default='are standing here.')
    mobs = Set('Mob', lazy=True)     # instances of this mob definition
    # TODO: equipment/inventory resets
    mresets = Set('MobReset', lazy=True) # where this mob resets
    clan = Optional('MobClan')
    unique = Required(bool, default=False)
    nation = Optional('MobNation')
    spells_trained = Set('Spell')
    skills_trained = Set('Skill')
    corpse = Optional('ObjectDefinition') # overrides race default corpse, if any

# TODO: treasure tables
# TODO: social tables
# TODO: pets
# TODO: mflag stay_area
# TODO: potions
# TODO: scrolls
# TODO: wands

class PlayerGuild(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    # TODO: charter
    # TODO: leader/officers
    # TODO: fortress/etc.
    members = Set('PlayerDefinition', reverse='guild')

# save files for players
class PlayerDefinition(MobBaseDefinition):
    mail = Optional(str)     # email for recovery
    password = Required(str) # base64-encoded, bcrypt salted first
    player = Optional('Player') # when online
    last_room = Optional('RoomDefinition')
    last_online = Required(datetime, default=datetime.now)
    guild = Optional('PlayerGuild', reverse='members')
    known = Set('PlayerDefinition', reverse='known_by')
    known_by = Set('PlayerDefinition', reverse='known')

# base for active Mob/Player in memory
class MobBase(ContainerBase):
    mflags = Required(Json, default={}) # active flags
    effects = Set('MobEffect') # active effects
    room = Required('Room')
    leader = Optional('MobBase', reverse='followers')
    followers = Set('MobBase', reverse='leader')
    group = Optional(MobGroup, reverse='members')
    group_led = Optional(MobGroup, reverse='leader')

# active Mob in memory, one of many of its type
class Mob(MobBase):
    mdef = Required(MobDefinition) # goblin raider
    name = Optional(str)      # Jack
    title = Optional(str)     # Sir
    corpse = Optional('ObjectDefinition') # overrides mdef default corpse, if any
    level = Optional(int) # override level to make slightly stronger/etc.

# active Player in memory, unique!
class Player(MobBase):
    pdef = Required(PlayerDefinition, unique=True)
    client_id = Required(str)

# TODO helpers for is_weapon, is_staff, is_wand, is_corpse, etc.
# furniture, fixture, chest, building?
class ObjectType(OnlineEditable, db.Entity):
    name = PrimaryKey(str)
    supertype = Optional('ObjectType') # multiple supertypes so we can have a chair be a weapon and furniture?
    subtypes = Set('ObjectType', lazy=True)
    objects = Set('ObjectDefinition', lazy=True)
    required_equipped_by = Set('ObjectRequirement', reverse='equipment_types', lazy=True)
    required_held_by = Set('ObjectRequirement', reverse='inventory_types', lazy=True)
    allowed_locations = Set('ObjectLocation', lazy=True)

class ObjectDefinition(OnlineEditable, db.Entity):
    created_at = Required(datetime, default=datetime.now)
    # metadata: created_by = Optional('Player', reverse='created_objects')
    metadata = Required(Json, default={})
    name = Required(str, unique=True)
    otype = Required('ObjectType')
    objects = Set('Object', lazy=True)
    doors = Set('DoorDefinition', lazy=True) # for keys
    oresets = Set('ObjectReset', lazy=True)
    corpse_of_race = Set('MobRace')
    corpse_of_mob_definition = Set('MobDefinition')
    corpse_of_mob = Set('Mob') # this is not 'savable' as 'Mob' is ephemeral...
    consumed_by_spells = Set('SpellStep', reverse='reagents', lazy=True)
    consumed_by_skills = Set('SkillStep', reverse='ingredients', lazy=True)
    produced_by_spells = Set('SpellStep', reverse='products', lazy=True)
    produced_by_skills = Set('SkillStep', reverse='products', lazy=True)
    required_equipped_by = Set('ObjectRequirement', reverse='equipment', lazy=True)
    required_held_by = Set('ObjectRequirement', reverse='inventory', lazy=True)

# active Object in memory
class Object(ContainerBase):
    odef = Required(ObjectDefinition)
    owner = Required(ContainerBase)
    location = Optional(str)

class ObjectLocation(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # right_arm, torso, horn...
    allowed_types = Set('ObjectType')
    required_open_by_spells = Set('SpellStep', reverse='open_slots', lazy=True)
    required_open_by_skills = Set('SkillStep', reverse='open_slots', lazy=True)
    targeted_open_by_spells = Set('SpellStep', reverse='target_slot', lazy=True)

class AreaFlag(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # open
    default = Required(bool)

class AreaDefinition(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    area = Optional('Area') # , unique=True) # CAUSED ERROR!
    metadata = Required(Json, default={}) # created_by...
    rdefs = Set('RoomDefinition')
    aflagdefs = Required(Json, default={}) # todo: check insert/update for existence using py_check function

# active Area loaded
class Area(db.Entity):
    adef = Required(AreaDefinition, unique=True)
    rooms = Set('Room') # active rooms
    aflags = Required(Json, default={}) # active area flags, not persisted

class ObjectReset(OnlineEditable, db.Entity):
    room = Required('RoomDefinition')
    odef = Required('ObjectDefinition')

class MobReset(OnlineEditable, db.Entity):
    room = Required('RoomDefinition')
    mdef = Required('MobDefinition') # todo: add ability to name, provide special weapons?

class RoomFlag(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # safe, pkill, ...
    default = Required(bool, default=False)

class RoomDefinition(OnlineEditable, db.Entity):
    id = Required(int)
    adef = Required(AreaDefinition)
    room = Optional('Room') # , unique=True) # CAUSED ERROR!
    name = Required(str) # todo: auto strip?
    ddefs = Set('DoorDefinition', reverse='room') # todo: json?
    entrancedefs = Set('DoorDefinition', reverse='destination')
    rflagdefs = Required(Json, default={}) # todo: check insert/update for rflag existence
    oresets = Set('ObjectReset') # todo: json?
    mresets = Set('MobReset') # todo: json?
    last_players = Set('PlayerDefinition', lazy=True) # players last seen in this room, for relog
    PrimaryKey(adef, id)

class Room(ContainerBase):
    area = Required('Area')
    rdef = Required(RoomDefinition, unique=True)
    doors = Set('Door')
    mobs = Set('MobBase')
    rflags = Required(Json, default={}) # active ephemeral flags?

class Direction(OnlineEditable, db.Entity):
    name = PrimaryKey(str)
    long_name = Required(str, unique=True)
    ddefs_leading = Set('DoorDefinition', lazy=True)
    @property
    def opposite_long_name(self):
        if self.name == "n":
            return "south"
        if self.name == "u":
            return "down"
        if self.name == "d":
            return "up"
        if self.name == "s":
            return "north"
        if self.name == "e":
            return "west"
        if self.name == "w":
            return "east"
    @property
    def arrives_opposite_long_name(self):
        opln = self.opposite_long_name
        if self.name == "u":
            opln = "below"
        if self.name == "d":
            opln = "above"
        if self.name in ["n","s","e","w"]:
            opln = "the " + opln
        return opln
    # doors_leading = Set('Door', lazy=True)
    # TODO: opposite?

class DoorDefinition(OnlineEditable, db.Entity):
    room = Required('RoomDefinition')
    door = Optional('Door') # , unique=True) # CAUSED ERROR
    direction = Required(Direction) # Direction todo: check insert/update for existence
    destination = Required('RoomDefinition')
    dflagdefs = Required(Json, default={}) # todo: check insert/update for dflag existence
    key = Optional('ObjectDefinition')
    composite_key(room, direction)

class Door(db.Entity):
    ddef = Required('DoorDefinition', unique=True)
    room = Required('Room')
    dflags = Required(Json, default={}) # active ephemeral flags? i.e. unlocked

class DoorFlag(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # reset_closed, is_closed,...
    default = Required(bool, default=False)

