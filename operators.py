import bpy
import json
import time
import urllib.request
from .core.phaser import PhaserCore
from .core.utils import preset_manager

def _get_selected_pose_bones(context):
    try:
        selected = context.selected_pose_bones
    except AttributeError:
        if bpy.context.active_object and bpy.context.active_object.mode == 'POSE':
            selected = bpy.context.selected_pose_bones
        else:
            selected = []
    if not selected:
        return []
    return list(selected)

def _expand_with_children(bones):
    result = list(bones)
    seen = {b.name for b in bones}
    stack = list(bones)
    while stack:
        bone = stack.pop()
        for child in bone.children:
            if child.name in seen:
                continue
            seen.add(child.name)
            result.append(child)
            stack.append(child)
    return result

def _get_effective_selection(context, include_children=False):
    selected = _get_selected_pose_bones(context)
    if include_children and selected:
        return _expand_with_children(selected)
    return selected

def _get_addon_prefs(context):
    addon = context.preferences.addons.get(__package__)
    if addon:
        return addon.preferences
    return None

def _parse_version(value):
    if isinstance(value, (list, tuple)):
        parts = value
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith(("v", "V")):
            text = text[1:]
        parts = text.split(".")
    else:
        return None
    try:
        return tuple(int(p) for p in parts)
    except (TypeError, ValueError):
        return None


class SpringMagicPhaserCalculate(bpy.types.Operator):
    r"""Generate phase animation"""
    bl_idname = "sj_phaser.calculate"
    bl_label = "Calculate"
    bl_description = "Calculate a phase animation."

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        sjps = context.scene.sj_phaser_props
        core = PhaserCore()

        core.sf = context.scene.frame_start
        core.ef = context.scene.frame_end
        core.debug = sjps.debug

        core.delay = sjps.delay
        core.recursion = sjps.recursion / 10.0
        core.strength = 1.0 + ((sjps.strength - 1.0) / 10.0)
        core.twist = sjps.twist / 10.0
        core.tension = sjps.tension / 10.0
        core.inertia = sjps.inertia / 10.0
        core.extend = sjps.extend / 10.0
        core.sub_steps = max(1, int(sjps.sub_steps))
        core.threshold = sjps.threshold
        
        core.use_force = sjps.use_force
        core.force_vector = sjps.force_vector
        core.force_strength = sjps.force_strength
        
        # Pass new property
        core.use_scene_fields = sjps.use_scene_fields
        core.use_wind_object = sjps.use_wind_object
        core.wind_object = sjps.wind_object
        core.wind_min_strength = sjps.wind_min_strength
        core.wind_max_strength = sjps.wind_max_strength
        core.wind_frequency = sjps.wind_frequency
        core.use_collision = sjps.use_collision
        core.collision_margin = sjps.collision_margin
        core.collision_length_offset = sjps.collision_length_offset
        core.use_collision_collection = sjps.use_collision_collection
        core.collision_collection = sjps.collision_collection
        core.use_collision_plane = sjps.use_collision_plane
        core.collision_plane_object = sjps.collision_plane_object

        if core.sf >= core.ef:
            self.report({'ERROR'}, "Start Frame must be smaller than End Frame.")
            return {'FINISHED'}

        context.scene.frame_set(core.sf)
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        
        selected = _get_effective_selection(context, sjps.use_chain)
        obj_trees = core.get_tree_list(context, selected)
        core.delete_anim_keys(obj_trees, context)
        
        for k in obj_trees:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    core.set_animkey(pbn, context)

        obj_trees = core.set_pre_data(obj_trees, context)
        core.execute_simulation(obj_trees, context)
        if sjps.use_loop:
            core.match_end_to_start(obj_trees, context)

        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        return {'FINISHED'}


class SpringMagicPhaserDelAnim(bpy.types.Operator):
    r"""Delete Animation Keys"""
    bl_idname = "sj_phaser.del_anim"
    bl_label = "Delete Keyframe"
    bl_description = "Delete animation keys."

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        sjps = context.scene.sj_phaser_props
        core = PhaserCore()

        core.sf = context.scene.frame_start
        core.ef = context.scene.frame_end
        
        if core.sf >= core.ef:
            self.report({'ERROR'}, "Start Frame must be smaller than End Frame.")
            return {'FINISHED'}

        context.scene.frame_set(core.sf)
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        
        selected = _get_effective_selection(context, sjps.use_chain)
        obj_trees = core.get_tree_list(context, selected)
        core.delete_anim_keys(obj_trees, context)
        
        for k in obj_trees:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    core.set_animkey(pbn, context)

        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        return {'FINISHED'}

class SpringMagicPhaserSavePreset(bpy.types.Operator):
    r"""Save current settings as a preset"""
    bl_idname = "sj_phaser.save_preset"
    bl_label = "Save Preset"
    
    preset_name: bpy.props.StringProperty(
        name="Preset Name",
        description="Name of the preset to save",
        default="MyPreset"
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        sjps = context.scene.sj_phaser_props
        name = self.preset_name.strip()
        
        if not name:
            self.report({'ERROR'}, "Please enter a preset name")
            return {'CANCELLED'}
        
        data = {
            "delay": sjps.delay,
            "recursion": sjps.recursion,
            "strength": sjps.strength,
            "twist": sjps.twist,
            "tension": sjps.tension,
            "inertia": sjps.inertia,
            "extend": sjps.extend,
            "sub_steps": sjps.sub_steps,
            "use_force": sjps.use_force,
            "force_vector": [v for v in sjps.force_vector],
            "force_strength": sjps.force_strength,
            "use_scene_fields": sjps.use_scene_fields,
            "use_wind_object": sjps.use_wind_object,
            "wind_object": sjps.wind_object.name if sjps.wind_object else "",
            "wind_min_strength": sjps.wind_min_strength,
            "wind_max_strength": sjps.wind_max_strength,
            "wind_frequency": sjps.wind_frequency,
            "use_collision": sjps.use_collision,
            "collision_margin": sjps.collision_margin,
            "collision_length_offset": sjps.collision_length_offset,
            "use_collision_plane": sjps.use_collision_plane,
            "collision_plane_object": sjps.collision_plane_object.name if sjps.collision_plane_object else "",
            "use_collision_collection": sjps.use_collision_collection,
            "collision_collection": sjps.collision_collection.name if sjps.collision_collection else "",
            "use_loop": sjps.use_loop,
            "use_chain": sjps.use_chain
        }
        
        if preset_manager.save_preset(name, data):
            self.report({'INFO'}, f"Saved preset: {name}")
            def update_enum():
                if hasattr(sjps, "property_unset"): pass 
            bpy.app.timers.register(update_enum, first_interval=0.1)
        else:
            self.report({'ERROR'}, "Failed to save preset")

        return {'FINISHED'}

class SpringMagicPhaserLoadPreset(bpy.types.Operator):
    r"""Load selected preset"""
    bl_idname = "sj_phaser.load_preset"
    bl_label = "Load Preset"
    
    def execute(self, context):
        sjps = context.scene.sj_phaser_props
        name = sjps.preset_enum
        if name == 'NONE':
            return {'CANCELLED'}
            
        data = preset_manager.load_preset(name)
        if data:
            sjps.delay = data.get("delay", sjps.delay)
            sjps.recursion = data.get("recursion", sjps.recursion)
            sjps.strength = data.get("strength", sjps.strength)
            sjps.twist = data.get("twist", sjps.twist)
            sjps.tension = data.get("tension", sjps.tension)
            sjps.inertia = data.get("inertia", sjps.inertia)
            sjps.extend = data.get("extend", sjps.extend)
            sjps.sub_steps = data.get("sub_steps", sjps.sub_steps)
            sjps.use_force = data.get("use_force", sjps.use_force)
            if "force_vector" in data:
                sjps.force_vector = data["force_vector"]
            sjps.force_strength = data.get("force_strength", sjps.force_strength)
            sjps.use_scene_fields = data.get("use_scene_fields", False)
            sjps.use_wind_object = data.get("use_wind_object", False)
            wind_obj_name = data.get("wind_object", "")
            sjps.wind_object = bpy.data.objects.get(wind_obj_name) if wind_obj_name else None
            sjps.wind_min_strength = data.get("wind_min_strength", sjps.wind_min_strength)
            sjps.wind_max_strength = data.get("wind_max_strength", sjps.wind_max_strength)
            sjps.wind_frequency = data.get("wind_frequency", sjps.wind_frequency)
            sjps.use_collision = data.get("use_collision", False)
            sjps.collision_margin = data.get("collision_margin", sjps.collision_margin)
            sjps.collision_length_offset = data.get("collision_length_offset", sjps.collision_length_offset)
            sjps.use_collision_plane = data.get("use_collision_plane", False)
            plane_name = data.get("collision_plane_object", "")
            sjps.collision_plane_object = bpy.data.objects.get(plane_name) if plane_name else None
            sjps.use_collision_collection = data.get("use_collision_collection", False)
            collection_name = data.get("collision_collection", "")
            sjps.collision_collection = bpy.data.collections.get(collection_name) if collection_name else None
            sjps.use_loop = data.get("use_loop", False)
            sjps.use_chain = data.get("use_chain", False)
            
            self.report({'INFO'}, f"Loaded preset: {name}")
        else:
            self.report({'ERROR'}, f"Could not load preset: {name}")

        return {'FINISHED'}

class SpringMagicPhaserResetDefault(bpy.types.Operator):
    r"""Reset settings to default"""
    bl_idname = "sj_phaser.reset_default"
    bl_label = "Reset Default"
    bl_description = "Reset all properties to default values."
    
    def execute(self, context):
        sjps = context.scene.sj_phaser_props
        sjps.delay = 3.0
        sjps.recursion = 5.0
        sjps.strength = 1.0
        sjps.twist = 0.0
        sjps.tension = 0.0
        sjps.inertia = 0.0
        sjps.extend = 0.0
        sjps.sub_steps = 1
        sjps.use_force = False
        sjps.force_vector = (0, 0, -1)
        sjps.force_strength = 0.1
        sjps.use_scene_fields = False
        sjps.use_wind_object = False
        sjps.wind_object = None
        sjps.wind_min_strength = 0.0
        sjps.wind_max_strength = 1.0
        sjps.wind_frequency = 0.5
        sjps.use_collision = False
        sjps.collision_margin = 0.0
        sjps.collision_length_offset = 0.0
        sjps.use_collision_plane = False
        sjps.collision_plane_object = None
        sjps.use_collision_collection = False
        sjps.collision_collection = None
        sjps.use_loop = False
        sjps.use_chain = False
        sjps.threshold = 0.001
        
        self.report({'INFO'}, "Settings reset to default.")
        return {'FINISHED'}

class SpringMagicCheckUpdate(bpy.types.Operator):
    r"""Check for add-on updates"""
    bl_idname = "sj_phaser.check_update"
    bl_label = "Check Updates"
    bl_description = "Check for updates using the configured Update URL"

    def execute(self, context):
        prefs = _get_addon_prefs(context)
        if not prefs or not prefs.update_url:
            self.report({'ERROR'}, "Set Update URL in add-on preferences.")
            return {'CANCELLED'}

        try:
            with urllib.request.urlopen(prefs.update_url, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:
            self.report({'ERROR'}, f"Update check failed: {exc}")
            return {'CANCELLED'}

        data = None
        latest_version = None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw.strip()

        if isinstance(data, dict):
            latest_version = _parse_version(data.get("version"))
        else:
            latest_version = _parse_version(data)

        if not latest_version:
            self.report({'ERROR'}, "Update data missing a valid version.")
            return {'CANCELLED'}

        addon = context.preferences.addons.get(__package__)
        current_version = (0, 0, 0)
        if addon and hasattr(addon, "module") and hasattr(addon.module, "bl_info"):
            current_version = addon.module.bl_info.get("version", current_version)

        latest_str = ".".join(str(v) for v in latest_version)
        current_str = ".".join(str(v) for v in current_version)

        prefs.last_update_version = latest_str
        prefs.last_checked = time.strftime("%Y-%m-%d %H:%M:%S")

        if latest_version > tuple(current_version):
            prefs.last_update_status = f"Update available: {latest_str} (current {current_str})"
            self.report({'INFO'}, prefs.last_update_status)
        elif latest_version == tuple(current_version):
            prefs.last_update_status = f"Up to date: {current_str}"
            self.report({'INFO'}, prefs.last_update_status)
        else:
            prefs.last_update_status = f"Local version ahead: {current_str}"
            self.report({'INFO'}, prefs.last_update_status)

        return {'FINISHED'}
