
from model import *
from engine import Engine

# db = model.db
# db._in_init_ = True

import asyncio
import json
import glob
import json5
# from os import walk
# import importlib
from pony.orm import db_session, set_sql_debug

def load_dtype_instance(dtype, dtype_json, set_references):
    for k, v in set_references.items():
        if k in dtype_json:
            s = []
            for sk in dtype_json[k]:
                s.append(v[sk])
            dtype_json[k] = s

    _dtype = dtype(**dtype_json)
    return _dtype

# TODO refactor
def load_dtype(dtype, hierarchy_attr=None, multiple_inheritance=False, set_references={}):
    with db_session:

        print(f"Loading: {dtype.__qualname__}")
        # dtype = getattr(model, dtype_dir)

        loaded = set()
        delayed_loads = []
        dtype_json_files = glob.glob(f'data/{dtype.__qualname__}/*.json')
        for dtype_json_file in dtype_json_files:
            with open(dtype_json_file) as f:
                print(f"Loading: {dtype_json_file}")
                dtype_json = json.load(f)
                print(dtype_json['name'])
                if hierarchy_attr and dtype_json.get(hierarchy_attr):
                    print(f"Delaying: {dtype_json['name']}")
                    delayed_loads.append(dtype_json)
                else:
                    _dtype = load_dtype_instance(dtype, dtype_json, set_references)
                    loaded.add(_dtype.name)
                    print(f"Loaded: {_dtype.name}")

        redelayed_loads = []
        for delayed_load in delayed_loads:
            print(f"Loading: {delayed_load['name']}")
            parent_set = set()
            if multiple_inheritance:
                for p in delayed_load[hierarchy_attr]:
                    parent_set.add(p)
            else:
                parent_set.add(delayed_load[hierarchy_attr])
            if parent_set.issubset(loaded):
                _dtype = load_dtype_instance(dtype, delayed_load, set_references)
                loaded.add(_dtype.name)
                print(f"Loaded: {_dtype.name}")
            else:
                print(f"Redelaying: {delayed_load['name']}")
                redelayed_loads.append(delayed_load)

        for redelayed_load in redelayed_loads:
            print(f"Loading: {redelayed_load['name']}")
            _dtype = load_dtype_instance(dtype, redelayed_load, set_references)
            loaded.add(_dtype.name)
            print(f"Loaded: {_dtype.name}")

def load_objects():
    pass

def load_mobs():
    pass

def load_areas():
    with db_session:
        door_data = []
        area_json5_files = glob.glob('data/areas/*.json5')
        for area_json5_file in area_json5_files:
            with open(area_json5_file) as f:
                print("Loading:", area_json5_file)
                adefdata = json5.load(f)
                _adef = AreaDefinition(id=adefdata['id'], name=adefdata['name'])
                for rdefdata in adefdata['rooms']:
                    _rdef = RoomDefinition(id=rdefdata['id'], name=rdefdata['name'], adef=_adef)
                    if "doors" in rdefdata:
                        door_data.append({'room':_rdef, 'doors':rdefdata["doors"], 'area':_adef})
        for d in door_data:
            for k, v in d['doors'].items():
                _adef = d['area'] if "in" not in v else AreaDefinition[v['in']]
                _ddef = DoorDefinition(room=d['room'], direction=Direction[k], destination=RoomDefinition[_adef, v["to"]], dflagdefs=v.get("flags",{}))

def load_players():
    pass

if __name__=="__main__":
    db.bind('sqlite', ':memory:', create_db=True)
    db.generate_mapping(create_tables=True)

    load_dtype(ObjectType, hierarchy_attr='supertype')
    load_dtype(ObjectDefinition)
    load_dtype(MobSize)
    load_dtype(Morphology, hierarchy_attr='base')
    set_sql_debug(True)
    load_dtype(MobRace, hierarchy_attr='parents', multiple_inheritance=True, set_references={'parents': MobRace})

    # TODO: control order outside of code?
    for dtype in [
            SpellStep, Spell,
            MobFlag, MobEffect,
            RoomFlag, AreaFlag, DoorFlag, Direction,
            Player,
            MobDefinition]:
        load_dtype(dtype)

    load_areas()

    # load players
    db._in_init_ = False

    engine = Engine(db)
    asyncio.run(engine.run())

