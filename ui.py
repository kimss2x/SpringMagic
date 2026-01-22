import bpy

class SpringMagicPhaserPanel(bpy.types.Panel):
    r"""UI Panel for SpringMagic Phaser"""
    bl_label = "SpringMagic"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "posemode"
    bl_category = "Animation"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        sjps = context.scene.sj_phaser_props
        scene = context.scene

        # Presets Section (Simplified)
        layout.label(text="Presets:")
        row = layout.row(align=True)
        row.prop(sjps, "preset_enum", text="")
        row.operator("sj_phaser.load_preset", text="", icon="IMPORT")
        row.operator("sj_phaser.save_preset", text="", icon="EXPORT")
        row.operator("sj_phaser.reset_default", text="", icon="LOOP_BACK")
        
        # Core Properties
        col = layout.column(align=True)
        col.label(text="Phaser Settings:")
        col.prop(sjps, "delay")
        col.prop(sjps, "recursion")
        col.prop(sjps, "strength")
        col.prop(sjps, "show_advanced")
        if sjps.show_advanced:
            row = col.row(align=True)
            row.prop(sjps, "twist")
            row.prop(sjps, "tension")

            row = col.row(align=True)
            row.prop(sjps, "inertia")
            row.prop(sjps, "extend")
            col.prop(sjps, "sub_steps")
            col.prop(sjps, "threshold")

        # Force Settings
        col = layout.column(align=True)
        col.label(text="Forces:")
        row = col.row(align=True)
        row.prop(sjps, "use_scene_fields", toggle=True, icon="FORCE_WIND", text="Scene")
        row.prop(sjps, "use_force", toggle=True, text="Gravity")
        row.prop(sjps, "use_wind_object", toggle=True, text="Wind Obj")
        if sjps.use_force:
            box = col.box()
            box.prop(sjps, "force_vector")
            box.prop(sjps, "force_strength")
        if sjps.use_wind_object:
            box = col.box()
            box.prop(sjps, "wind_object")
            row = box.row(align=True)
            row.prop(sjps, "wind_min_strength")
            row.prop(sjps, "wind_max_strength")
            box.prop(sjps, "wind_frequency")

        # Collision
        col = layout.column(align=True)
        col.label(text="Collision:")
        col.prop(sjps, "use_collision", text="Bone Collision")
        if sjps.use_collision:
            col.prop(sjps, "collision_margin", text="Radius Offset")
            col.prop(sjps, "collision_length_offset", text="Length Offset")
        col.separator()
        col.prop(sjps, "use_collision_plane", text="Plane Collision")
        if sjps.use_collision_plane:
            col.prop(sjps, "collision_plane_object", text="Plane Object")
        col.separator()
        col.prop(sjps, "use_collision_collection", text="Collision Collection")
        if sjps.use_collision_collection:
            col.prop(sjps, "collision_collection", text="Collection")
            col.prop(sjps, "collision_auto_register", text="Auto-register Collision")

        col = layout.column(align=True)
        col.label(text="Options:")
        row = col.row(align=True)
        row.prop(sjps, "use_loop", icon="CON_FOLLOWPATH", text="Loop")
        row.prop(sjps, "use_chain", icon="LINKED", text="Chain")
        row = col.row(align=True)
        row.prop(sjps, "use_pose_match", icon="KEY_HLT", text="Pose Match")
        if sjps.use_pose_match:
            col.prop(sjps, "pose_match_strength", slider=True)

        col = layout.column(align=True)
        col.label(text="Controllers:")
        col.prop(sjps, "controller_prefix", text="Prefix")
        row = col.row(align=True)
        row.operator("sj_phaser.bind_controllers", text="Bind", icon="CONSTRAINT")
        row.operator("sj_phaser.bake_controllers", text="Bake", icon="REC")
        col.prop(sjps, "controller_remove_bind", text="Remove Bind on Bake")

        # Bake Blending
        col = layout.column(align=True)
        col.label(text="Bake Blending:")
        row = col.row(align=True)
        row.prop(sjps, "spring_bake_mode", expand=True)
        col.prop(sjps, "spring_bake_weight", slider=True)


        # Frame Range
        layout.label(text="Actions(Bake):")
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(sjps, "frame_range_mode", expand=True)
        if sjps.frame_range_mode == 'SCENE':
            col.label(text=f"Range: {scene.frame_start} - {scene.frame_end}")
        else:
            row = col.row(align=True)
            row.prop(sjps, "custom_frame_start")
            row.prop(sjps, "custom_frame_end")

        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("sj_phaser.calculate", text="Calculate Physics", icon="PHYSICS")
        row.operator("sj_phaser.del_anim", text="", icon="TRASH")

