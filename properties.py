import bpy
from .core.utils import preset_manager

class SpringMagicPhaserProperties(bpy.types.PropertyGroup):
    r"""Property Group for SpringMagic Phaser"""
    
    # Phaser Core Properties
    delay: bpy.props.FloatProperty(
        name="Delay", 
        description="Delay factor for the following bone",
        default=3, min=1.0, max=30.0
    )
    recursion: bpy.props.FloatProperty(
        name="Recursion", 
        description="Recursion or follow-through effect",
        default=5.0, min=0.0, max=10.0
    )
    strength: bpy.props.FloatProperty(
        name="Strength", 
        description="Strength of the spring/phaser effect",
        default=1.0, min=1.0, max=10.0
    )
    twist: bpy.props.FloatProperty(
        name="Twist",
        description="Twist damping around the bone axis",
        default=0.0, min=0.0, max=10.0
    )
    tension: bpy.props.FloatProperty(
        name="Tension",
        description="Damping to resist bending",
        default=0.0, min=0.0, max=10.0
    )
    inertia: bpy.props.FloatProperty(
        name="Inertia",
        description="Carry over motion from previous frames",
        default=0.0, min=0.0, max=10.0
    )
    extend: bpy.props.FloatProperty(
        name="Extend",
        description="Stretch along the bone axis",
        default=0.0, min=0.0, max=10.0
    )
    sub_steps: bpy.props.IntProperty(
        name="Sub Steps",
        description="Internal simulation steps per frame",
        default=1, min=1, max=10
    )
    show_advanced: bpy.props.BoolProperty(
        name="Advanced",
        description="Show advanced spring controls",
        default=False
    )
    
    # Physics / Force Properties

    use_force: bpy.props.BoolProperty(
        name="Gravity", 
        description="Apply constant force (Gravity)",
        default=False
    )
    force_vector: bpy.props.FloatVectorProperty(
        name="Direction", 
        default=(0, 0, -1), 
        subtype='XYZ',
        description="Direction of the gravity/force"
    )
    force_strength: bpy.props.FloatProperty(
        name="Strength", 
        default=0.1, min=0.0, max=10.0,
        description="Magnitude of the gravity/force"
    )

    # Scence Fields
    use_scene_fields: bpy.props.BoolProperty(
        name="Use Scene Fields",
        description="React to Blender Force Fields (Wind, Force) in the scene",
        default=False
    )
    use_wind_object: bpy.props.BoolProperty(
        name="Wind Object",
        description="Apply procedural wind using an object direction and oscillation",
        default=False
    )
    wind_object: bpy.props.PointerProperty(
        name="Wind Object",
        description="Object whose local Z axis defines wind direction",
        type=bpy.types.Object
    )
    wind_min_strength: bpy.props.FloatProperty(
        name="Min Strength",
        description="Minimum wind strength",
        default=0.0, min=-100.0, max=100.0
    )
    wind_max_strength: bpy.props.FloatProperty(
        name="Max Strength",
        description="Maximum wind strength",
        default=1.0, min=-100.0, max=100.0
    )
    wind_frequency: bpy.props.FloatProperty(
        name="Frequency",
        description="Wind oscillation frequency in Hz (0 keeps constant at max)",
        default=0.5, min=0.0, max=100.0
    )

    # Collision
    use_collision: bpy.props.BoolProperty(
        name="Collision",
        description="Enable bone-based capsule collision for bone tips",
        default=False
    )
    collision_margin: bpy.props.FloatProperty(
        name="Radius Offset",
        description="Extra offset added to bone collision radius",
        default=0.0, min=0.0, max=1.0, precision=3
    )
    collision_length_offset: bpy.props.FloatProperty(
        name="Length Offset",
        description="Extra length added to bone collision capsule",
        default=0.0, min=0.0, max=10.0, precision=3
    )
    use_collision_plane: bpy.props.BoolProperty(
        name="Plane Collision",
        description="Enable collision against a plane object",
        default=False
    )
    collision_plane_object: bpy.props.PointerProperty(
        name="Plane Object",
        description="Object used as an infinite collision plane (local Z normal)",
        type=bpy.types.Object
    )
    use_collision_collection: bpy.props.BoolProperty(
        name="Collection Collision",
        description="Use collection objects with rigid body or collision physics shapes",
        default=False
    )
    collision_collection: bpy.props.PointerProperty(
        name="Collision Collection",
        description="Collection of collision objects",
        type=bpy.types.Collection
    )

    # Presets
    preset_enum: bpy.props.EnumProperty(
        name="Presets",
        description="Load a saved preset",
        items=preset_manager.get_enum_items
    )

    # Bake Blending
    spring_bake_weight: bpy.props.FloatProperty(
        name="Bake Weight",
        description="Blend weight between existing animation and spring result (0=keep existing, 1=full spring)",
        default=1.0, min=0.0, max=1.0, precision=2
    )
    spring_bake_mode: bpy.props.EnumProperty(
        name="Bake Mode",
        description="How to blend spring result with existing animation",
        items=[
            ('OVERRIDE', "Override", "Lerp/Slerp between existing pose and spring pose"),
            ('ADDITIVE', "Additive", "Add spring delta on top of existing animation"),
        ],
        default='OVERRIDE'
    )

    # Options
    use_loop: bpy.props.BoolProperty(
        name="Loop",
        description="Match end frame to start frame for seamless loops",
        default=False
    )
    use_chain: bpy.props.BoolProperty(
        name="Chain",
        description="Include children of selected bones when baking",
        default=False
    )
    use_pose_match: bpy.props.BoolProperty(
        name="Pose Match",
        description="Match simulation to existing keyframed poses",
        default=False
    )
    pose_match_strength: bpy.props.FloatProperty(
        name="Match Strength",
        description="Blend strength when matching to keyframed poses",
        default=1.0, min=0.0, max=1.0, precision=2
    )
    controller_prefix: bpy.props.StringProperty(
        name="Controller Prefix",
        description="Prefix for generated controller bones",
        default="SM_CTRL_"
    )
    controller_remove_bind: bpy.props.BoolProperty(
        name="Remove Bind on Bake",
        description="Remove controller bind constraints after baking",
        default=True
    )

    # System
    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Optimization threshold",
        default=0.001, min=0.00001, max=0.1, step=0.01, precision=4
    )
    debug: bpy.props.BoolProperty(name="Debug", default=False)
