import bpy
import json
import os

PRESET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "presets")

def ensure_preset_dir():
    if not os.path.exists(PRESET_DIR):
        os.makedirs(PRESET_DIR)

def get_preset_path(name):
    ensure_preset_dir()
    if not name.endswith(".json"):
        name += ".json"
    return os.path.join(PRESET_DIR, name)

def save_preset(name, data):
    r"""Save dictionary data to a json preset file"""
    path = get_preset_path(name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return True

def load_preset(name):
    r"""Load dictionary data from a json preset file"""
    path = get_preset_path(name)
    if not os.path.exists(path):
        return None
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def get_preset_list():
    ensure_preset_dir()
    files = [f for f in os.listdir(PRESET_DIR) if f.endswith(".json")]
    return sorted(files)

def get_enum_items(self, context):
    items = []
    for f in get_preset_list():
        name = os.path.splitext(f)[0]
        items.append((name, name, f"Load preset: {name}"))
    
    if not items:
        items.append(('NONE', "None", "No presets found"))
        
    return items
