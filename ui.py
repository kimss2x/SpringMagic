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

        # Frame Range Info
        layout.label(text=f"Scene Frame Range: {scene.frame_start} - {scene.frame_end}")
        
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

        # Force Settings
        col = layout.column(align=True)
        row = col.row(align=True)
        sub = row.split(factor=0.2, align=True)
        sub.prop(sjps, "use_scene_fields", toggle=True, icon="FORCE_WIND", text="")
        sub.prop(sjps, "use_force", toggle=True)
        if sjps.use_force:
            box = col.box()
            box.prop(sjps, "force_vector")
            box.prop(sjps, "force_strength")            

        # Collision
        col = layout.column(align=True)
        col.label(text="Collision:")
        col.prop(sjps, "use_collision", text="Bone Collision")
        if sjps.use_collision:
            col.prop(sjps, "collision_margin", text="Radius Offset")
            col.prop(sjps, "collision_length_offset", text="Length Offset")
        col.separator()
        col.prop(sjps, "use_collision_collection", text="Collision Collection")
        if sjps.use_collision_collection:
            col.prop(sjps, "collision_collection", text="Collection")

        # System
        col = layout.column(align=False)
        col.prop(sjps, "threshold")

        col = layout.column(align=True)
        col.label(text="Options:")
        row = col.row(align=True)
        row.prop(sjps, "use_loop", icon="CON_FOLLOWPATH", text="Loop")
        row.prop(sjps, "use_chain", icon="LINKED", text="Chain")

        layout.label(text="Actions(Bake):")
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("sj_phaser.calculate", text="Calculate Physics", icon="PHYSICS")
        row.operator("sj_phaser.del_anim", text="", icon="TRASH")
