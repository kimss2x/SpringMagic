# SpringMagic (Blender add-on)

SpringMagic is a customized build of the Spring Magic add-on for Blender, tuned for
Blender 5.0 on Windows. This app extends 3D Max Spring Magic by porting it to Blender
5.0. It provides a physically based bone animation system with spring, force, and
wind effects for natural secondary motion.

## Features
- Spring-based follow-through for bone chains
- Optional constant force (gravity) with direction and strength
- Optional scene force fields (Wind / Force / Vortex)
- Wind object with min/max/frequency controls
- Bone-based collision using bone radius/length with offsets
- Plane collision using a designated plane object (infinite plane)
- Collection collision using rigid body or collision physics shapes
- Extra spring controls: twist, tension, inertia, extend, sub-steps
- Preset save/load and reset to defaults
- One-click bake and clear of keyframes
- Version info panel with optional update check

## Requirements
- Blender 5.0 (tested)
- Blender 2.80+ should work
- No external Python dependencies (uses Blender bundled numpy)

## Installation
1. Download or clone this repo.
2. In Blender: Edit > Preferences > Add-ons > Install...
3. Select the ZIP or the `SpringMagic` folder.
4. Enable the add-on.

## Usage
1. Select an armature and enter Pose Mode.
2. Select the bone chain(s) you want to simulate.
3. Set the scene frame range (Start/End).
4. Open View3D > Sidebar (N) > Animation tab > SpringMagic.
5. Adjust Delay / Recursion / Strength, and optional forces.
6. (Optional) Enable Collision and adjust Radius/Length Offset for self-collision.
7. (Optional) Enable Plane Collision and pick a plane object.
8. (Optional) Enable Collection Collision and pick a collection of rigid body colliders.
9. Click Calculate Physics to bake keys.
10. Use Clear Animation to remove generated keys.

## Presets
- Presets are stored as JSON in `presets/`.
- The default `.gitignore` ignores `presets/*.json` since they are usually user-specific.
- If you want to ship presets, remove that ignore and commit the files.

## Notes
- The add-on writes keyframes for location, rotation, and scale on selected bones.
- For safety, work on a duplicate action or a copy of your rig.
- Collection collision reads rigid body collision shapes and Collision modifiers; convex hull/mesh are approximated as box.
- Plane collision uses the plane object's local Z axis and is treated as infinite.
- Collision thickness/margin from physics settings is used to expand collider size.
- Update check expects a URL that returns JSON like {"version": "1.4.0"} or a plain version string.

## License
GPL v2 or later. See the header in `__init__.py`.

## Credits
- Original Spring Magic concept and this customized build are credited to the add-on
  author in `__init__.py` (`CaptainHansode`).
