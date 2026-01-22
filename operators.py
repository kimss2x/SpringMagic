import bpy
import json
import time
import urllib.request
import mathutils
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

def _get_frame_range(context):
    """Get frame range based on mode (scene or custom)."""
    sjps = context.scene.sj_phaser_props
    if sjps.frame_range_mode == 'CUSTOM':
        return sjps.custom_frame_start, sjps.custom_frame_end
    return context.scene.frame_start, context.scene.frame_end

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

def _iter_action_fcurves(action, obj=None):
    if not action:
        return []
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        return list(fcurves)

    found = []
    seen = set()

    def add_fcurves(items):
        if not items:
            return
        for fcu in items:
            key_func = getattr(fcu, "as_pointer", None)
            key = key_func() if callable(key_func) else id(fcu)
            if key in seen:
                continue
            seen.add(key)
            found.append(fcu)

    def add_channelbags(bags):
        if not bags:
            return
        for bag in bags:
            add_fcurves(getattr(bag, "fcurves", None))

    slot = None
    if obj:
        anim_data = getattr(obj, "animation_data", None)
        slot = getattr(anim_data, "action_slot", None) if anim_data else None

    layers_owner = slot.id_data if slot and hasattr(slot, "id_data") else action
    layers = getattr(layers_owner, "layers", None)
    if layers is None and layers_owner is not action:
        layers = getattr(action, "layers", None)
    if layers:
        for layer in layers:
            strips = getattr(layer, "strips", None)
            if not strips:
                continue
            for strip in strips:
                bag = None
                channelbag = getattr(strip, "channelbag", None)
                if callable(channelbag):
                    try:
                        bag = channelbag(slot) if slot else channelbag()
                    except TypeError:
                        try:
                            bag = channelbag(slot.handle) if slot else None
                        except Exception:
                            bag = None
                elif channelbag:
                    bag = channelbag
                if bag:
                    add_fcurves(getattr(bag, "fcurves", None))
                add_fcurves(getattr(strip, "fcurves", None))

    add_channelbags(getattr(action, "channelbags", None))
    if slot:
        add_channelbags(getattr(slot, "channelbags", None))

    return found

def _get_keyframes_for_bone(action, bone_name, frame_start, frame_end, obj=None):
    if not action:
        return set()
    frames = set()
    prefix = f'pose.bones["{bone_name}"].'
    for fcu in _iter_action_fcurves(action, obj):
        if not fcu.data_path.startswith(prefix):
            continue
        for kp in fcu.keyframe_points:
            frame = int(round(kp.co.x))
            if frame_start <= frame <= frame_end:
                frames.add(frame)
    return frames

def _collect_pose_match_data(context, bones, frame_start, frame_end):
    obj = context.active_object
    if not obj or not bones:
        return {}
    anim_data = obj.animation_data
    action = anim_data.action if anim_data else None
    if not action:
        return {}

    bone_frames = {}
    for bone in bones:
        frames = _get_keyframes_for_bone(action, bone.name, frame_start, frame_end, obj)
        if frames:
            bone_frames[bone.name] = frames
    if not bone_frames:
        return {}

    union_frames = sorted({f for frames in bone_frames.values() for f in frames})
    current_frame = context.scene.frame_current
    cache = {}
    for frame in union_frames:
        context.scene.frame_set(frame)
        context.view_layer.update()
        frame_cache = {}
        for bone_name, frames in bone_frames.items():
            if frame not in frames:
                continue
            pbn = obj.pose.bones.get(bone_name)
            if not pbn:
                continue
            frame_cache[bone_name] = pbn.matrix.copy()
        if frame_cache:
            cache[frame] = frame_cache

    context.scene.frame_set(current_frame)
    context.view_layer.update()
    return cache

def _get_unique_bones_from_trees(obj_trees):
    bones = {}
    for k in obj_trees:
        for t in obj_trees[k]:
            for pbn in obj_trees[k][t]["obj_list"]:
                bones[pbn.name] = pbn
    return list(bones.values())

def _blend_matrix(base_mat, target_mat, strength):
    loc_a, rot_a, scale_a = base_mat.decompose()
    loc_b, rot_b, scale_b = target_mat.decompose()
    loc = loc_a.lerp(loc_b, strength)
    rot = rot_a.slerp(rot_b, strength)
    scale = scale_a.lerp(scale_b, strength)
    return (
        mathutils.Matrix.Translation(loc)
        @ rot.to_matrix().to_4x4()
        @ mathutils.Matrix.Diagonal(scale).to_4x4()
    )

def _apply_pose_match(context, pose_cache, strength):
    if not pose_cache:
        return
    obj = context.active_object
    if not obj:
        return
    strength = max(0.0, min(1.0, strength))
    if strength <= 0.0:
        return

    current_frame = context.scene.frame_current
    for frame in sorted(pose_cache.keys()):
        context.scene.frame_set(frame)
        context.view_layer.update()
        for bone_name, target_mat in pose_cache[frame].items():
            pbn = obj.pose.bones.get(bone_name)
            if not pbn:
                continue
            if strength >= 0.999:
                pbn.matrix = target_mat
            else:
                pbn.matrix = _blend_matrix(pbn.matrix.copy(), target_mat, strength)
            pbn.keyframe_insert(data_path='location', frame=frame)
            pbn.keyframe_insert(data_path='rotation_euler', frame=frame)
            pbn.keyframe_insert(data_path='rotation_quaternion', frame=frame)
            pbn.keyframe_insert(data_path='scale', frame=frame)

    context.scene.frame_set(current_frame)
    context.view_layer.update()

_CTRL_BIND_CONSTRAINT = "SM_CTRL_BIND"

def _get_controller_prefix(sjps):
    prefix = sjps.controller_prefix.strip()
    return prefix if prefix else "SM_CTRL_"

def _get_pose_bone_depth(pbn):
    depth = 0
    parent = pbn.parent
    while parent:
        depth += 1
        parent = parent.parent
    return depth

def _find_bind_constraint(pbn):
    for con in pbn.constraints:
        if con.type == 'COPY_TRANSFORMS' and con.name == _CTRL_BIND_CONSTRAINT:
            return con
    return None

def _resolve_controller_pair(obj, pbn, prefix):
    if "sm_controller_for" in pbn:
        target = obj.pose.bones.get(pbn["sm_controller_for"])
        if target:
            return target, pbn
        return None
    if "sm_controller" in pbn:
        ctrl = obj.pose.bones.get(pbn["sm_controller"])
        if ctrl:
            return pbn, ctrl
        return None
    con = _find_bind_constraint(pbn)
    if con and con.subtarget:
        ctrl = obj.pose.bones.get(con.subtarget)
        if ctrl:
            return pbn, ctrl
    if prefix and pbn.name.startswith(prefix):
        target = obj.pose.bones.get(pbn.name[len(prefix):])
        if target:
            return target, pbn
    return None

def _insert_pose_keys(pbn, frame):
    pbn.keyframe_insert(data_path='location', frame=frame)
    pbn.keyframe_insert(data_path='rotation_euler', frame=frame)
    pbn.keyframe_insert(data_path='rotation_quaternion', frame=frame)
    pbn.keyframe_insert(data_path='scale', frame=frame)

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

        core.sf, core.ef = _get_frame_range(context)
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
        core.collision_auto_register = sjps.collision_auto_register
        core.use_collision_plane = sjps.use_collision_plane
        core.collision_plane_object = sjps.collision_plane_object

        # Bake Blending settings
        core.bake_weight = sjps.spring_bake_weight
        core.bake_mode = sjps.spring_bake_mode

        if core.sf >= core.ef:
            self.report({'ERROR'}, "Start Frame must be smaller than End Frame.")
            return {'CANCELLED'}

        # Limit frame range to prevent performance issues
        max_frames = 10000
        frame_count = core.ef - core.sf
        if frame_count > max_frames:
            self.report({'ERROR'}, f"Frame range too large ({frame_count} frames). Maximum is {max_frames}.")
            return {'CANCELLED'}

        context.scene.frame_set(core.sf)
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        selected = _get_effective_selection(context, sjps.use_chain)
        if not selected:
            self.report({'ERROR'}, "No bones selected. Select pose bones to calculate physics.")
            return {'CANCELLED'}

        obj_trees = core.get_tree_list(context, selected)
        if not obj_trees:
            self.report({'ERROR'}, "No valid bone chains found. Select bones with parents.")
            return {'CANCELLED'}

        pose_match_cache = None
        if sjps.use_pose_match and obj_trees:
            pose_bones = _get_unique_bones_from_trees(obj_trees)
            pose_match_cache = _collect_pose_match_data(context, pose_bones, core.sf, core.ef)

        # Cache existing animation for blending (must be before delete_anim_keys)
        core.cache_existing_animation(obj_trees, context)
        core.delete_anim_keys(obj_trees, context)
        
        for k in obj_trees:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    core.set_animkey(pbn, context)

        obj_trees, skipped_colliders, auto_registered = core.set_pre_data(obj_trees, context)

        # Info about auto-registered collision objects
        if auto_registered:
            names = ', '.join(auto_registered[:5])
            msg = f"Auto-registered {len(auto_registered)} object(s) with Collision modifier: {names}"
            if len(auto_registered) > 5:
                msg += f" and {len(auto_registered) - 5} more..."
            self.report({'INFO'}, msg)

        # Warn about skipped collision objects
        if skipped_colliders:
            skipped_names = [f"{name}({obj_type})" for name, obj_type, reason in skipped_colliders[:5]]
            msg = f"Skipped {len(skipped_colliders)} object(s) without physics: {', '.join(skipped_names)}"
            if len(skipped_colliders) > 5:
                msg += f" and {len(skipped_colliders) - 5} more..."
            self.report({'WARNING'}, msg)

        # Progress callback for visual feedback
        wm = context.window_manager
        wm.progress_begin(0, 100)

        def progress_callback(current, total):
            if total > 0:
                percent = int((current / total) * 100)
                wm.progress_update(percent)

        try:
            core.execute_simulation(obj_trees, context, progress_callback)
        finally:
            wm.progress_end()

        if sjps.use_pose_match and pose_match_cache:
            _apply_pose_match(context, pose_match_cache, sjps.pose_match_strength)
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

        core.sf, core.ef = _get_frame_range(context)

        if core.sf >= core.ef:
            self.report({'ERROR'}, "Start Frame must be smaller than End Frame.")
            return {'CANCELLED'}

        # Limit frame range to prevent performance issues
        max_frames = 10000
        frame_count = core.ef - core.sf
        if frame_count > max_frames:
            self.report({'ERROR'}, f"Frame range too large ({frame_count} frames). Maximum is {max_frames}.")
            return {'CANCELLED'}

        context.scene.frame_set(core.sf)
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        selected = _get_effective_selection(context, sjps.use_chain)
        if not selected:
            self.report({'ERROR'}, "No bones selected.")
            return {'CANCELLED'}

        obj_trees = core.get_tree_list(context, selected)
        if not obj_trees:
            self.report({'ERROR'}, "No valid bone chains found.")
            return {'CANCELLED'}

        core.delete_anim_keys(obj_trees, context, force_delete=True)

        for k in obj_trees:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    core.set_animkey(pbn, context)

        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        return {'FINISHED'}

class SpringMagicControllerBind(bpy.types.Operator):
    r"""Create controller bones and bind them to selected bones"""
    bl_idname = "sj_phaser.bind_controllers"
    bl_label = "Bind Controllers"
    bl_description = "Create controller bones and bind them to selected bones"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'ARMATURE'

    def execute(self, context):
        obj = context.active_object
        sjps = context.scene.sj_phaser_props
        prefix = _get_controller_prefix(sjps)

        selected = _get_effective_selection(context, sjps.use_chain)
        bones = []
        seen = set()
        for pbn in selected:
            if pbn.name in seen:
                continue
            if pbn.name.startswith(prefix):
                continue
            seen.add(pbn.name)
            bones.append(pbn)
        if not bones:
            self.report({'ERROR'}, "Select pose bones to bind controllers.")
            return {'CANCELLED'}

        bones_sorted = sorted(bones, key=_get_pose_bone_depth)
        prev_mode = obj.mode
        created = 0
        try:
            if prev_mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            edit_bones = obj.data.edit_bones
            for pbn in bones_sorted:
                src = edit_bones.get(pbn.name)
                if not src:
                    continue
                ctrl_name = prefix + pbn.name
                ctrl = edit_bones.get(ctrl_name)
                if not ctrl:
                    ctrl = edit_bones.new(ctrl_name)
                    ctrl.head = src.head.copy()
                    ctrl.tail = src.tail.copy()
                    ctrl.roll = src.roll
                    ctrl.use_deform = False
                    created += 1

                parent_ctrl = None
                if src.parent:
                    parent_ctrl = edit_bones.get(prefix + src.parent.name)
                if parent_ctrl:
                    ctrl.parent = parent_ctrl
                    ctrl.use_connect = src.use_connect
                else:
                    ctrl.parent = src.parent
                    ctrl.use_connect = False
        finally:
            if prev_mode != obj.mode:
                bpy.ops.object.mode_set(mode=prev_mode)

        bound = 0
        for pbn in bones:
            ctrl_name = prefix + pbn.name
            ctrl_pbn = obj.pose.bones.get(ctrl_name)
            if not ctrl_pbn:
                continue
            con = _find_bind_constraint(pbn)
            if not con:
                con = pbn.constraints.new('COPY_TRANSFORMS')
                con.name = _CTRL_BIND_CONSTRAINT
            con.target = obj
            con.subtarget = ctrl_name
            con.owner_space = 'POSE'
            con.target_space = 'POSE'
            pbn["sm_controller"] = ctrl_name
            ctrl_pbn["sm_controller_for"] = pbn.name
            bound += 1

        self.report({'INFO'}, f"Bound {bound} controller(s) (created {created}).")
        return {'FINISHED'}

class SpringMagicControllerBake(bpy.types.Operator):
    r"""Bake controller motion onto bound bones"""
    bl_idname = "sj_phaser.bake_controllers"
    bl_label = "Bake Controllers"
    bl_description = "Bake controller motion onto bound bones"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'ARMATURE'

    def execute(self, context):
        obj = context.active_object
        sjps = context.scene.sj_phaser_props
        prefix = _get_controller_prefix(sjps)

        selected = _get_effective_selection(context, sjps.use_chain)
        candidates = selected if selected else list(obj.pose.bones)
        pairs = []
        seen = set()
        for pbn in candidates:
            pair = _resolve_controller_pair(obj, pbn, prefix)
            if not pair:
                continue
            target, ctrl = pair
            if not target or not ctrl:
                continue
            if target.name in seen:
                continue
            seen.add(target.name)
            pairs.append((target, ctrl))

        if not pairs:
            self.report({'ERROR'}, "No bound controllers found to bake.")
            return {'CANCELLED'}

        scene = context.scene
        sf, ef = _get_frame_range(context)
        current_frame = scene.frame_current

        for frame in range(sf, ef + 1):
            scene.frame_set(frame)
            context.view_layer.update()
            for target, ctrl in pairs:
                target.matrix = ctrl.matrix.copy()
                _insert_pose_keys(target, frame)

        scene.frame_set(current_frame)
        context.view_layer.update()

        if sjps.controller_remove_bind:
            for target, ctrl in pairs:
                con = _find_bind_constraint(target)
                if con:
                    target.constraints.remove(con)
                if "sm_controller" in target:
                    del target["sm_controller"]
                if ctrl and "sm_controller_for" in ctrl:
                    del ctrl["sm_controller_for"]

        self.report({'INFO'}, f"Baked {len(pairs)} controller(s).")
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
            "collision_auto_register": sjps.collision_auto_register,
            "use_loop": sjps.use_loop,
            "use_chain": sjps.use_chain,
            "use_pose_match": sjps.use_pose_match,
            "pose_match_strength": sjps.pose_match_strength,
            "controller_prefix": sjps.controller_prefix,
            "controller_remove_bind": sjps.controller_remove_bind,
            "spring_bake_weight": sjps.spring_bake_weight,
            "spring_bake_mode": sjps.spring_bake_mode
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
            if wind_obj_name:
                wind_obj = bpy.data.objects.get(wind_obj_name)
                if wind_obj:
                    sjps.wind_object = wind_obj
                else:
                    sjps.wind_object = None
                    sjps.use_wind_object = False
                    self.report({'WARNING'}, f"Wind object '{wind_obj_name}' not found, disabled.")
            else:
                sjps.wind_object = None
            sjps.wind_min_strength = data.get("wind_min_strength", sjps.wind_min_strength)
            sjps.wind_max_strength = data.get("wind_max_strength", sjps.wind_max_strength)
            sjps.wind_frequency = data.get("wind_frequency", sjps.wind_frequency)
            sjps.use_collision = data.get("use_collision", False)
            sjps.collision_margin = data.get("collision_margin", sjps.collision_margin)
            sjps.collision_length_offset = data.get("collision_length_offset", sjps.collision_length_offset)
            sjps.use_collision_plane = data.get("use_collision_plane", False)
            plane_name = data.get("collision_plane_object", "")
            if plane_name:
                plane_obj = bpy.data.objects.get(plane_name)
                if plane_obj:
                    sjps.collision_plane_object = plane_obj
                else:
                    sjps.collision_plane_object = None
                    sjps.use_collision_plane = False
                    self.report({'WARNING'}, f"Collision plane '{plane_name}' not found, disabled.")
            else:
                sjps.collision_plane_object = None
            sjps.use_collision_collection = data.get("use_collision_collection", False)
            collection_name = data.get("collision_collection", "")
            if collection_name:
                coll = bpy.data.collections.get(collection_name)
                if coll:
                    sjps.collision_collection = coll
                else:
                    sjps.collision_collection = None
                    sjps.use_collision_collection = False
                    self.report({'WARNING'}, f"Collision collection '{collection_name}' not found, disabled.")
            else:
                sjps.collision_collection = None
            sjps.collision_auto_register = data.get("collision_auto_register", False)
            sjps.use_loop = data.get("use_loop", False)
            sjps.use_chain = data.get("use_chain", False)
            sjps.use_pose_match = data.get("use_pose_match", False)
            sjps.pose_match_strength = data.get("pose_match_strength", sjps.pose_match_strength)
            sjps.controller_prefix = data.get("controller_prefix", sjps.controller_prefix)
            sjps.controller_remove_bind = data.get("controller_remove_bind", sjps.controller_remove_bind)
            sjps.spring_bake_weight = data.get("spring_bake_weight", sjps.spring_bake_weight)
            sjps.spring_bake_mode = data.get("spring_bake_mode", sjps.spring_bake_mode)

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
        sjps.collision_auto_register = False
        sjps.use_loop = False
        sjps.use_chain = False
        sjps.use_pose_match = False
        sjps.pose_match_strength = 1.0
        sjps.controller_prefix = "SM_CTRL_"
        sjps.controller_remove_bind = True
        sjps.threshold = 0.001
        sjps.spring_bake_weight = 1.0
        sjps.spring_bake_mode = 'OVERRIDE'

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

        if isinstance(data, list) and len(data) > 0:
            # GitHub Tags API returns array of tags, get the first (latest) one
            version_str = data[0].get("name") if isinstance(data[0], dict) else None
            latest_version = _parse_version(version_str)
        elif isinstance(data, dict):
            # Support both "version" field and GitHub Releases API "tag_name" field
            version_str = data.get("version") or data.get("tag_name")
            latest_version = _parse_version(version_str)
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
