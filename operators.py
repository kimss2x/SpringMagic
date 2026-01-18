import bpy
from .core.phaser import PhaserCore
from .core.utils import preset_manager

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
        core.threshold = sjps.threshold
        
        core.use_force = sjps.use_force
        core.force_vector = sjps.force_vector
        core.force_strength = sjps.force_strength
        
        # Pass new property
        core.use_scene_fields = sjps.use_scene_fields

        if core.sf >= core.ef:
            self.report({'ERROR'}, "Start Frame must be smaller than End Frame.")
            return {'FINISHED'}

        context.scene.frame_set(core.sf)
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        
        obj_trees = core.get_tree_list(context)
        core.delete_anim_keys(obj_trees, context)
        
        for k in obj_trees:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    core.set_animkey(pbn, context)

        obj_trees = core.set_pre_data(obj_trees, context)
        core.execute_simulation(obj_trees, context)

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
        
        obj_trees = core.get_tree_list(context)
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
            "use_force": sjps.use_force,
            "force_vector": [v for v in sjps.force_vector],
            "force_strength": sjps.force_strength,
            "use_scene_fields": sjps.use_scene_fields
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
            sjps.use_force = data.get("use_force", sjps.use_force)
            if "force_vector" in data:
                sjps.force_vector = data["force_vector"]
            sjps.force_strength = data.get("force_strength", sjps.force_strength)
            sjps.use_scene_fields = data.get("use_scene_fields", False)
            
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
        sjps.use_force = False
        sjps.force_vector = (0, 0, -1)
        sjps.force_strength = 0.1
        sjps.use_scene_fields = False
        sjps.threshold = 0.001
        
        self.report({'INFO'}, "Settings reset to default.")
        return {'FINISHED'}
