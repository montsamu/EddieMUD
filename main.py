
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

if __name__=="__main__":
    db.bind('sqlite', ':memory:', create_db=True)
    db.generate_mapping(create_tables=True)

    set_sql_debug(True)

    with db_session:
        for dtype in [ObjectType, ObjectDefinition, SpellStep, Spell, MobMorphology, MobFlag, MobEffect, RoomFlag, AreaFlag, DoorFlag, Direction]:
            print(f"Loading: {dtype.__qualname__}")
            # dtype = getattr(model, dtype_dir)

            dtype_json_files = glob.glob(f'data/{dtype.__qualname__}/*.json')
            for dtype_json_file in dtype_json_files:
                with open(dtype_json_file) as f:
                    print(f"Loading: {dtype_json_file}")
                    dtype_json = json.load(f)
                    print(dtype_json['name'])
                    _dtype = dtype(**dtype_json)
                    print(f"Loaded: {_dtype.name}")

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

    db._in_init_ = False

    engine = Engine(db)
    asyncio.run(engine.loop())

