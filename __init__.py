# -*- coding: utf-8 -*-
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "SpringMagic",
    "description": "Physically based bone animation system with spring, force, and wind effects for creating natural secondary motion and overlapping action.",
    "author": "CaptainHansode",
    "version": (1, 0, 1),
    "blender": (2, 80, 0),
    "location":  "View3D > Sidebar > Tool Tab",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "support": "COMMUNITY",
    "category": "Animation"
}

import bpy
import importlib

# Check if we need to reload modules (for development)
if "bpy" in locals():
    if "core" in locals():
        importlib.reload(core.utils.math_utils)
        importlib.reload(core.utils.preset_manager)
        importlib.reload(core.phaser)
        
    if "properties" in locals():
        importlib.reload(properties)
    if "operators" in locals():
        importlib.reload(operators)
    if "ui" in locals():
        importlib.reload(ui)

from . import properties
from . import operators
from . import ui
from .core import phaser

classes = (
    properties.SpringMagicPhaserProperties,
    operators.SpringMagicPhaserCalculate,
    operators.SpringMagicPhaserDelAnim,
    operators.SpringMagicPhaserSavePreset,
    operators.SpringMagicPhaserLoadPreset,
    operators.SpringMagicPhaserResetDefault,
    ui.SpringMagicPhaserPanel
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.sj_phaser_props = bpy.props.PointerProperty(type=properties.SpringMagicPhaserProperties)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.sj_phaser_props

if __name__ == "__main__":
    register()
