import bpy
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
