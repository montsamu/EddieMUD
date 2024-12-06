
from datetime import datetime
from copy import deepcopy
import re
from pony.orm import Database, Required, Set, Optional, PrimaryKey, composite_key, Json, StrArray

db = Database()
db._in_init_ = True

# NOTE: when saving a player must also save their objects and pets, skillset and spellbook and prayerbook and songbook and runeset and cookbook and potionbook...
class OnlineEditable(object):
    """Mixin for defining entity hooks to persist in-memory entities to JSON"""
    def after_insert(self):
        if not self._database_._in_init_:
            print("storing",self,"to json...")
    def after_update(self):
        print("updating",self,"to json...")
    def after_delete(self):
        print("deleting",self,"from json...")

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
    equipment = Set('ObjectDefinition')
    inventory = Set('ObjectDefinition')

class SkillSetItem(db.Entity):
    skill = Required('Skill')
    level = Required(int, default=1)
    mob = Required('MobBase')
    PrimaryKey(mob, skill)

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
    mob = Required('MobBase')
    PrimaryKey(mob, spell)

class MobRace(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # elf dwarf troll half-dwarf
    parents = Set('MobRace', reverse='children')
    children = Set('MobRace', reverse='parents')
    morphology = Required('Morphology')
    size = Required('MobSize')
    flags = Required(Json, default={})
    races = Set('MobDefinition', lazy=True)

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

class MobDefinition(OnlineEditable, db.Entity):
    name = Required(str, unique=True)
    metadata = Required(Json, default={})
    created_at = Required(datetime, default=datetime.now)
    # metadata: created_by = Optional('Player', reverse='created_mobs')
    race = Required('MobRace')
    mflags = Required(Json, default={})
    effects = Set('MobEffect')
    mobs = Set('MobBase', lazy=True)
    mresets = Set('MobReset', lazy=True)
    level = Required(int, default=1)
    experience = Required(int, default=0)

class PlayerDefinition(OnlineEditable, MobDefinition):
    password = Required(str)
    known = Set('PlayerDefinition', reverse='known_by')
    known_by = Set('PlayerDefinition', reverse='known')

class MobBase(ContainerBase):
    mflags = Required(Json, default={})
    effects = Set('MobEffect')
    room = Required('Room')
    leader = Optional('MobBase', reverse='followers')
    followers = Set('MobBase', reverse='leader')
    group = Optional(MobGroup, reverse='members')
    group_led = Optional(MobGroup, reverse='leader')
    skillset = Set('SkillSetItem')
    spellbook = Set('SpellBookItem')

class Mob(OnlineEditable, MobBase):
    mdef = Required(MobDefinition)
    name = Optional(str)
    title = Optional(str)

class Player(OnlineEditable, MobBase):
    pdef = Required(PlayerDefinition)
    last_room = Optional('RoomDefinition')

# TODO helpers for is_weapon, is_staff, is_wand, etc.
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
    created_at = Required(datetime)
    # metadata: created_by = Optional('Player', reverse='created_objects')
    metadata = Required(Json, default={})
    name = Required(str, unique=True)
    otype = Required('ObjectType')
    objects = Set('Object', lazy=True)
    doors = Set('DoorDefinition', lazy=True) # for keys
    oresets = Set('ObjectReset', lazy=True)
    consumed_by_spells = Set('SpellStep', reverse='reagents', lazy=True)
    consumed_by_skills = Set('SkillStep', reverse='ingredients', lazy=True)
    produced_by_spells = Set('SpellStep', reverse='products', lazy=True)
    produced_by_skills = Set('SkillStep', reverse='products', lazy=True)
    required_equipped_by = Set('ObjectRequirement', reverse='equipment', lazy=True)
    required_held_by = Set('ObjectRequirement', reverse='inventory', lazy=True)

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
    rooms = Set('RoomDefinition')
    aflagdefs = Required(Json, default={}) # todo: check insert/update for existence using py_check function

class Area(db.Entity):
    adef = Required(AreaDefinition, unique=True)
    rooms = Set('Room')
    aflags = Required(Json, default={})

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
    exits = Set('DoorDefinition', reverse='room') # todo: json?
    entrances = Set('DoorDefinition', reverse='destination')
    rflagdefs = Required(Json, default={}) # todo: check insert/update for rflag existence
    oresets = Set('ObjectReset') # todo: json?
    mresets = Set('MobReset') # todo: json?
    PrimaryKey(adef, id)

class Room(ContainerBase):
    area = Required('Area')
    rdef = Required(RoomDefinition, unique=True)
    exits = Set('Door', reverse="room")
    entrances = Set('Door', reverse="destination")
    mobs = Set('MobBase')
    rflags = Required(Json, default={})

class Direction(OnlineEditable, db.Entity):
    name = PrimaryKey(str)
    long_name = Required(str, unique=True)
    ddefs_leading = Set('DoorDefinition', lazy=True)
    doors_leading = Set('Door', lazy=True)
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
    ddef = Required('DoorDefinition')
    room = Required('Room')
    direction = Required(Direction)
    destination = Required('Room')
    dflags = Required(Json, default={})
    composite_key(room, direction)

class DoorFlag(OnlineEditable, db.Entity):
    name = PrimaryKey(str) # reset_closed, is_closed,...
    default = Required(bool, default=False)

