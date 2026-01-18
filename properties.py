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

    # Presets
    preset_enum: bpy.props.EnumProperty(
        name="Presets",
        description="Load a saved preset",
        items=preset_manager.get_enum_items
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

    # System
    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Optimization threshold",
        default=0.001, min=0.00001, max=0.1, step=0.01, precision=4
    )
    debug: bpy.props.BoolProperty(name="Debug", default=False)
