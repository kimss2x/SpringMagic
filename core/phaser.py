# -*- coding: utf-8 -*-
import mathutils
import copy
import math
import numpy as np
from .utils import math_utils

# Physics simulation constants
FORCE_FIELD_SCALE = 20.0      # Scale factor for Blender force field strength
SCENE_FORCE_SCALE = 0.01      # Scale factor for scene forces (tames raw physics values)
EPSILON = 0.000001            # Small value for floating point comparisons
AXIS_THRESHOLD = 0.0001       # Threshold for axis vector validity


class PhaserCore(object):
    r"""
    Core calculation module for SpringMagic Phaser.
    Handles the physics-like simulation for bone chains.
    """
    def __init__(self):
        self.delay = 5.0
        self.recursion = 5.0
        self.strength = 1.0
        self.twist = 0.0
        self.tension = 0.0
        self.inertia = 0.0
        self.extend = 0.0
        self.sub_steps = 1
        self.threshold = 0.001
        self.sf = 0
        self.ef = 10
        self.debug = False
        
        # New Force Properties
        self.use_force = False
        self.force_vector = mathutils.Vector((0, 0, -1))
        self.force_strength = 0.0
        
        # Scene Fields
        self.use_scene_fields = False
        self._cached_fields = []
        self.use_wind_object = False
        self.wind_object = None
        self.wind_min_strength = 0.0
        self.wind_max_strength = 1.0
        self.wind_frequency = 0.5

        # Collision
        self.use_collision = False
        self.collision_margin = 0.0
        self.collision_length_offset = 0.0
        self.use_collision_plane = False
        self.collision_plane_object = None
        self.use_collision_collection = False
        self.collision_collection = None
        self.collision_auto_register = False
        self._collision_bones = []
        self._collision_plane = None
        self._collection_colliders = []

        # Bake Blending
        self.bake_weight = 1.0
        self.bake_mode = 'OVERRIDE'
        self._existing_anim_cache = {}  # {bone_name: {frame: {loc, rot_quat, rot_euler, scale}}}
        self._base_pose_cache = {}  # For additive mode: rest/base pose at start frame

    def get_tree_list(self, context, selected_bones=None):
        r"""Get list of bone chains (trees) from selection"""
        tree_roots = []
        obj_trees = {}
        
        if selected_bones is None:
            try:
                selected = context.selected_pose_bones
            except AttributeError:
                # Fallback if context is not view_layer/pose specific
                import bpy
                if bpy.context.active_object and bpy.context.active_object.mode == 'POSE':
                    selected = bpy.context.selected_pose_bones
                else:
                    return {}
        else:
            selected = selected_bones

        if not selected:
            return {}

        for pbn in selected:
            if pbn.parent is None:
                continue
            
            is_root = False
            if pbn.parent not in selected:
                is_root = True
            elif pbn.parent.children[0] != pbn:
                is_root = True
            
            if is_root:
                tree_roots.append(pbn)

        t_cnt = 0
        for root_obj in tree_roots:
            depth_cnt = math_utils.get_hierarchy_depth(root_obj)
            tree = []
            t_name = "tree{}".format(t_cnt)
            
            if depth_cnt not in obj_trees:
                obj_trees[depth_cnt] = {}

            if len(root_obj.children) == 0:
                tree.append(root_obj)
                obj_trees[depth_cnt][t_name] = self._create_data_structure(tree)
                t_cnt += 1
                continue

            tree.append(root_obj)
            c_obj = root_obj.children[0]

            while c_obj in selected:
                tree.append(c_obj)
                if len(c_obj.children) == 0:
                    break
                c_obj = c_obj.children[0]

            obj_trees[depth_cnt][t_name] = self._create_data_structure(tree)
            t_cnt += 1

        return obj_trees

    def _get_unique_bones(self, obj_trees):
        bones = {}
        for k in obj_trees:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    bones[pbn.name] = pbn
        return list(bones.values())

    def cache_existing_animation(self, obj_trees, context):
        r"""Cache existing animation values before bake for blending."""
        self._existing_anim_cache = {}
        self._base_pose_cache = {}

        if self.bake_weight >= 0.999:
            return  # No blending needed, skip caching

        bones = self._get_unique_bones(obj_trees)
        if not bones:
            return

        current_frame = context.scene.frame_current

        # Pre-initialize cache dictionaries for all bones (avoid repeated dict lookups)
        for bone in bones:
            self._existing_anim_cache[bone.name] = {}

        # Cache base pose at start frame (for additive mode)
        context.scene.frame_set(self.sf)
        context.view_layer.update()
        for bone in bones:
            self._base_pose_cache[bone.name] = {
                'loc': bone.location.copy(),
                'rot_quat': bone.rotation_quaternion.copy(),
                'rot_euler': bone.rotation_euler.copy(),
                'scale': bone.scale.copy(),
            }

        # Cache existing animation at each frame
        # Note: frame_set + view_layer.update per frame is required for accurate evaluation
        for frame in range(self.sf, self.ef + 1):
            context.scene.frame_set(frame)
            context.view_layer.update()

            for bone in bones:
                # Direct assignment (dict already exists)
                self._existing_anim_cache[bone.name][frame] = {
                    'loc': bone.location.copy(),
                    'rot_quat': bone.rotation_quaternion.copy(),
                    'rot_euler': bone.rotation_euler.copy(),
                    'scale': bone.scale.copy(),
                }

        context.scene.frame_set(current_frame)
        context.view_layer.update()

    def _blend_override(self, existing, spring, weight):
        r"""Override blend: lerp/slerp between existing and spring pose."""
        loc = existing['loc'].lerp(spring['loc'], weight)
        rot_quat = existing['rot_quat'].slerp(spring['rot_quat'], weight)

        # For Euler, convert to quaternion, slerp, then convert back
        existing_euler_quat = existing['rot_euler'].to_quaternion()
        spring_euler_quat = spring['rot_euler'].to_quaternion()
        blended_euler_quat = existing_euler_quat.slerp(spring_euler_quat, weight)
        rot_euler = blended_euler_quat.to_euler(existing['rot_euler'].order)

        scale = existing['scale'].lerp(spring['scale'], weight)

        return {
            'loc': loc,
            'rot_quat': rot_quat,
            'rot_euler': rot_euler,
            'scale': scale,
        }

    def _blend_additive(self, existing, spring, base, weight):
        r"""Additive blend: apply weighted delta from base to existing pose."""
        # Location: delta = spring_loc - base_loc, new = existing + delta * weight
        delta_loc = spring['loc'] - base['loc']
        loc = existing['loc'] + delta_loc * weight

        # Rotation (quaternion): delta = spring * inverse(base), apply weighted
        base_quat_inv = base['rot_quat'].inverted()
        delta_quat = spring['rot_quat'] @ base_quat_inv
        # Slerp from identity to delta by weight, then apply to existing
        identity = mathutils.Quaternion((1.0, 0.0, 0.0, 0.0))
        weighted_delta = identity.slerp(delta_quat, weight)
        rot_quat = weighted_delta @ existing['rot_quat']
        rot_quat.normalize()

        # Euler: same approach via quaternion
        base_euler_quat = base['rot_euler'].to_quaternion()
        spring_euler_quat = spring['rot_euler'].to_quaternion()
        existing_euler_quat = existing['rot_euler'].to_quaternion()
        delta_euler_quat = spring_euler_quat @ base_euler_quat.inverted()
        weighted_euler_delta = identity.slerp(delta_euler_quat, weight)
        blended_euler_quat = weighted_euler_delta @ existing_euler_quat
        blended_euler_quat.normalize()
        rot_euler = blended_euler_quat.to_euler(existing['rot_euler'].order)

        # Scale: delta = spring_scale / base_scale, lerp(1, delta, weight), multiply
        delta_scale = mathutils.Vector((
            spring['scale'].x / base['scale'].x if base['scale'].x != 0 else 1.0,
            spring['scale'].y / base['scale'].y if base['scale'].y != 0 else 1.0,
            spring['scale'].z / base['scale'].z if base['scale'].z != 0 else 1.0,
        ))
        one_vec = mathutils.Vector((1.0, 1.0, 1.0))
        weighted_scale_factor = one_vec.lerp(delta_scale, weight)
        scale = mathutils.Vector((
            existing['scale'].x * weighted_scale_factor.x,
            existing['scale'].y * weighted_scale_factor.y,
            existing['scale'].z * weighted_scale_factor.z,
        ))

        return {
            'loc': loc,
            'rot_quat': rot_quat,
            'rot_euler': rot_euler,
            'scale': scale,
        }

    def _create_data_structure(self, tree):
        return {
            "obj_list": tree,
            "pre_mt": [],
            "obj_length": [],
            "old_vec": [],
            "old_tip": []
        }

    def get_bone_length_matrix(self, pbn, matrix_world):
        r"""Relative matrix calculation"""
        wmt = matrix_world @ pbn.matrix
        p_wmt = matrix_world @ pbn.parent.matrix
        len_mt = p_wmt.inverted() @ wmt
        return len_mt

    def get_end_pos_from_bonelength(self, pbn, matrix_world):
        wmt = matrix_world @ pbn.matrix
        local_tip = mathutils.Matrix.Translation((0, pbn.length, 0))
        tip_world = wmt @ local_tip
        return tip_world

    def set_pre_data(self, obj_trees, context):
        r"""Initialize matrices and vectors.

        Returns:
            tuple: (obj_trees, skipped_colliders list)
        """
        dct_k = sorted(obj_trees.keys())
        amt = context.active_object
        amt_world = amt.matrix_world
        skipped_colliders = []
        auto_registered = []

        # Cache fields once if enabled
        if self.use_scene_fields:
            self._cache_scene_fields(context)
        if self.use_collision:
            self._cache_collision_bones(obj_trees)
        if self.use_collision_plane:
            self._cache_collision_plane()
        if self.use_collision_collection:
            skipped_colliders, auto_registered = self._cache_collection_colliders(context)

        for k in dct_k:
            for t in obj_trees[k]:
                data = obj_trees[k][t]
                obj_list = data["obj_list"]
                
                for i, pbn in enumerate(obj_list):
                    wmt = amt_world @ pbn.matrix
                    data["pre_mt"].append(wmt)
                    
                    data["obj_length"].append(self.get_bone_length_matrix(pbn, amt_world))
                    data["old_vec"].append(mathutils.Vector((0.0, 0.0, 0.0)))
                    data["old_tip"].append(amt_world @ pbn.tail)

                    if i == len(obj_list) - 1:
                        end_mt = self.get_end_pos_from_bonelength(pbn, amt_world)
                        data["pre_mt"].append(end_mt)

                        wmt = amt_world @ pbn.matrix
                        len_mt = wmt.inverted() @ end_mt
                        data["obj_length"].append(len_mt)

        return obj_trees, skipped_colliders, auto_registered

    def _cache_scene_fields(self, context):
        r"""Find relevant force fields in the scene"""
        self._cached_fields = []
        for obj in context.scene.objects:
            if obj.field and obj.field.type in {'WIND', 'FORCE', 'VORTEX'}: # Support simplified types
                 self._cached_fields.append(obj)

    def _cache_collision_bones(self, obj_trees):
        r"""Collect bones used for collision checks"""
        self._collision_bones = self._get_unique_bones(obj_trees)

    def _cache_collision_plane(self):
        r"""Cache collision plane data from an object"""
        self._collision_plane = None
        obj = self.collision_plane_object
        if not obj:
            return
        normal = obj.matrix_world.to_3x3() @ mathutils.Vector((0.0, 0.0, 1.0))
        if normal.length == 0.0:
            return
        normal.normalize()
        point = obj.matrix_world.translation
        self._collision_plane = {
            "obj": obj,
            "normal": normal,
            "point": point
        }

    def _cache_collection_colliders(self, context=None):
        r"""Collect collection objects with rigid body collision shapes.

        Args:
            context: Blender context (required for auto-register)

        Returns:
            tuple: (skipped_colliders, auto_registered_names)
        """
        import bpy

        self._collection_colliders = []
        self._skipped_colliders = []  # Track objects without physics
        auto_registered = []  # Track auto-registered objects

        if not self.collision_collection:
            return [], []

        for obj in self.collision_collection.all_objects:
            # Skip non-mesh objects (Empty, Armature, Camera, etc.)
            if obj.type != 'MESH':
                self._skipped_colliders.append((obj.name, obj.type, "Not a mesh"))
                continue

            shape = None
            margin = 0.0
            skip_reason = None

            if obj.rigid_body:
                shape = obj.rigid_body.collision_shape
                margin = max(margin, obj.rigid_body.collision_margin)
            else:
                has_collision = False
                if hasattr(obj, "collision") and obj.collision:
                    has_collision = True
                if any(mod.type == 'COLLISION' for mod in obj.modifiers):
                    has_collision = True
                if has_collision:
                    shape = 'BOX'
                    if hasattr(obj, "collision") and obj.collision:
                        margin = max(margin, obj.collision.thickness_outer)
                elif self.collision_auto_register and context:
                    # Auto-register: Add Collision modifier (lightweight, no Rigid Body World needed)
                    try:
                        # Check if COLLISION modifier already exists
                        has_collision_mod = any(mod.type == 'COLLISION' for mod in obj.modifiers)
                        if not has_collision_mod:
                            obj.modifiers.new(name="Collision", type='COLLISION')
                            auto_registered.append(obj.name)

                        # Use BOX shape for collision detection
                        shape = 'BOX'
                        margin = obj.collision.thickness_outer if obj.collision else 0.0

                    except Exception as e:
                        skip_reason = f"Auto-register failed: {e}"
                else:
                    skip_reason = "No rigid body or collision"

            if not shape:
                self._skipped_colliders.append((obj.name, obj.type, skip_reason or "No collision shape"))
                continue

            if shape in {'CONVEX_HULL', 'MESH'}:
                shape = 'BOX'

            self._collection_colliders.append({
                "obj": obj,
                "shape": shape,
                "margin": margin
            })

        return self._skipped_colliders, auto_registered

    def _capsule_from_bone(self, pbn, amt_world):
        head = amt_world @ pbn.head
        tail = amt_world @ pbn.tail
        axis = tail - head
        if axis.length > 0.0 and self.collision_length_offset > 0.0:
            axis.normalize()
            half_offset = self.collision_length_offset * 0.5
            head = head - (axis * half_offset)
            tail = tail + (axis * half_offset)
        radius = max(pbn.bone.head_radius, pbn.bone.tail_radius, 0.001)
        radius = radius + self.collision_margin
        return head, tail, radius

    def _closest_point_on_segment(self, p, a, b):
        ab = b - a
        ab_len_sq = ab.length_squared
        if ab_len_sq == 0.0:
            return a
        t = (p - a).dot(ab) / ab_len_sq
        t = math_utils.clamp(t, 0.0, 1.0)
        return a + (ab * t)

    def _apply_capsule_collision(self, point, amt_world, exclude_names=None):
        corrected = point
        for bone in self._collision_bones:
            if exclude_names and bone.name in exclude_names:
                continue
            head, tail, radius = self._capsule_from_bone(bone, amt_world)
            closest = self._closest_point_on_segment(corrected, head, tail)
            delta = corrected - closest
            dist = delta.length
            if dist < radius:
                if dist < 0.000001:
                    axis = (tail - head).normalized()
                    delta = axis.cross(mathutils.Vector((1.0, 0.0, 0.0)))
                    if delta.length < 0.000001:
                        delta = axis.cross(mathutils.Vector((0.0, 1.0, 0.0)))
                    dist = delta.length
                if dist > 0.0:
                    delta.normalize()
                    corrected = closest + (delta * radius)
        return corrected

    def _apply_plane_collision(self, point):
        plane = self._collision_plane
        if not plane:
            return point
        n = plane["normal"]
        p0 = plane["point"]
        dist = (point - p0).dot(n)
        if dist < 0.0:
            return point - (n * dist)
        return point

    def _apply_collection_collision(self, point):
        corrected = point
        for col in self._collection_colliders:
            corrected = self._apply_object_collider(corrected, col)
        return corrected

    def _apply_object_collider(self, point, col):
        obj = col["obj"]
        shape = col["shape"]
        margin = col.get("margin", 0.0)
        if shape == 'SPHERE':
            return self._collide_sphere(point, obj, margin)
        if shape in {'CAPSULE', 'CYLINDER'}:
            return self._collide_capsule(point, obj, margin)
        return self._collide_box(point, obj, margin)

    def _collide_sphere(self, point, obj, margin):
        center = obj.matrix_world.translation
        radius = max(obj.dimensions.x, obj.dimensions.y, obj.dimensions.z) * 0.5 + margin
        if radius <= 0.0:
            return point
        delta = point - center
        dist = delta.length
        if dist < radius:
            if dist < 0.000001:
                delta = mathutils.Vector((1.0, 0.0, 0.0))
                dist = delta.length
            delta.normalize()
            return center + (delta * radius)
        return point

    def _collide_box(self, point, obj, margin):
        inv = obj.matrix_world.inverted_safe()
        local = inv @ point
        bounds = obj.bound_box
        min_x = min(v[0] for v in bounds)
        max_x = max(v[0] for v in bounds)
        min_y = min(v[1] for v in bounds)
        max_y = max(v[1] for v in bounds)
        min_z = min(v[2] for v in bounds)
        max_z = max(v[2] for v in bounds)
        if min_x == max_x:
            expand = max(0.0001, margin)
            min_x -= expand
            max_x += expand
        else:
            min_x -= margin
            max_x += margin
        if min_y == max_y:
            expand = max(0.0001, margin)
            min_y -= expand
            max_y += expand
        else:
            min_y -= margin
            max_y += margin
        if min_z == max_z:
            expand = max(0.0001, margin)
            min_z -= expand
            max_z += expand
        else:
            min_z -= margin
            max_z += margin
        if (min_x <= local.x <= max_x and min_y <= local.y <= max_y and min_z <= local.z <= max_z):
            dx = min(local.x - min_x, max_x - local.x)
            dy = min(local.y - min_y, max_y - local.y)
            dz = min(local.z - min_z, max_z - local.z)
            if dx <= dy and dx <= dz:
                local.x = min_x if (local.x - min_x) < (max_x - local.x) else max_x
            elif dy <= dz:
                local.y = min_y if (local.y - min_y) < (max_y - local.y) else max_y
            else:
                local.z = min_z if (local.z - min_z) < (max_z - local.z) else max_z
            return obj.matrix_world @ local
        return point

    def _collide_capsule(self, point, obj, margin):
        dims = obj.dimensions
        base_radius = max(dims.x, dims.y) * 0.5
        radius = base_radius + margin
        if radius <= 0.0:
            return point
        half_height = max(0.0, (dims.z * 0.5) - base_radius)
        half_height = half_height + margin

        axis = obj.matrix_world.to_3x3() @ mathutils.Vector((0.0, 0.0, 1.0))
        if axis.length == 0.0:
            return point
        axis.normalize()

        center = obj.matrix_world.translation
        p0 = center - (axis * half_height)
        p1 = center + (axis * half_height)
        closest = self._closest_point_on_segment(point, p0, p1)
        delta = point - closest
        dist = delta.length
        if dist < radius:
            if dist < 0.000001:
                delta = axis.cross(mathutils.Vector((1.0, 0.0, 0.0)))
                if delta.length < 0.000001:
                    delta = axis.cross(mathutils.Vector((0.0, 1.0, 0.0)))
                dist = delta.length
            if dist > 0.0:
                delta.normalize()
                return closest + (delta * radius)
        return point

    def calculate_scene_forces(self, position):
        r"""Calculate summed force vector from scene fields at a position"""
        total_force = mathutils.Vector((0.0, 0.0, 0.0))
        
        for f_obj in self._cached_fields:
            field = f_obj.field
            strength = field.strength
            if strength == 0: continue

            # Field Transform
            f_mat = f_obj.matrix_world
            f_loc = f_mat.translation
            
            # 1. WIND: Directional, along local Z
            if field.type == 'WIND':
                # Local Z axis in World Space
                wind_dir = f_mat.to_3x3().col[2].normalized()
                
                # Simple falloff (Planar)? Blender wind usually implies infinite plane unless confined
                # We'll treat it as global directional for simplicity or check distance if needed
                # For now: Apply vector * strength
                force_vec = wind_dir * strength
                
                # Check noise/flow? Too complex for python loop, keep it simple
                total_force += force_vec
            
            # 2. FORCE (Point): Radial
            elif field.type == 'FORCE':
                # Vector from source to object
                direction = position - f_loc
                dist = direction.length
                
                # Avoid division by zero
                if dist < 0.001: dist = 0.001
                
                direction.normalize()
                
                # Apply Power Law Falloff (simplified)
                # Blender uses 'Power' (default 2)
                falloff = 1.0
                if field.use_max_distance and dist > field.distance_max:
                    falloff = 0.0
                elif field.use_min_distance and dist < field.distance_min:
                    # Constant force inside min distance? or capped? usually smoothed
                    pass
                else:
                    # Simple Inverse Square approximation if not strictly specified
                    # Actually standard physics is 1/r^2
                    falloff = 1.0 / (dist ** 2)
                
                # Force is Repulsive (Positive) or Attractive (Negative)
                # Field strength in Blender: Positive blows away
                force_vec = direction * (strength * falloff * FORCE_FIELD_SCALE)
                total_force += force_vec
                
        return total_force

    def _get_scene_fps(self, scene):
        fps_base = scene.render.fps_base or 1.0
        fps = scene.render.fps / fps_base
        if fps <= 0.0:
            return 24.0
        return fps

    def _calculate_wind_vector(self, context):
        obj = self.wind_object
        if not obj:
            return mathutils.Vector((0.0, 0.0, 0.0))
        direction = obj.matrix_world.to_3x3() @ mathutils.Vector((0.0, 0.0, 1.0))
        if direction.length == 0.0:
            return mathutils.Vector((0.0, 0.0, 0.0))
        direction.normalize()

        min_strength = self.wind_min_strength
        max_strength = self.wind_max_strength
        if min_strength > max_strength:
            min_strength, max_strength = max_strength, min_strength

        if self.wind_frequency <= 0.0:
            strength = max_strength
        else:
            scene_fps = self._get_scene_fps(context.scene)
            time = context.scene.frame_current / scene_fps
            phase = time * self.wind_frequency * math.pi * 2.0
            strength = min_strength + ((max_strength - min_strength) * (0.5 + 0.5 * math.sin(phase)))

        return direction * strength

    def calculate_step(self, obj_data, context, dt_scale=1.0, insert_key=True):
        r"""Perform single step calculation"""
        amt = context.active_object
        amt_world = amt.matrix_world
        
        first_bone = obj_data["obj_list"][0]
        if first_bone.parent:
            cur_p_mt = amt_world @ first_bone.parent.matrix
        else:
            cur_p_mt = amt_world

        strgh = self.strength
        trshd = self.threshold
        twst = self.twist
        tens = self.tension
        inrt = self.inertia
        ext_scale = 1.0 + self.extend
        
        # Base Constant Force
        force_vec_world = self.force_vector.normalized() * self.force_strength if self.use_force else mathutils.Vector((0,0,0))
        wind_vec_world = self._calculate_wind_vector(context) if self.use_wind_object else mathutils.Vector((0,0,0))
        
        for i in range(len(obj_data["obj_list"])):
            obj = obj_data["obj_list"][i]
            
            tag_mt = cur_p_mt @ obj_data["obj_length"][i]

            # Use pre_mt directly for reading (no need to copy since we only read from it)
            pre_mt = obj_data["pre_mt"][i]
            new_mt = copy.copy(pre_mt)
            tag_pos = tag_mt.translation

            # Align Y
            pre_y_vec = pre_mt.to_3x3().col[1].normalized()
            tag_y_vec = tag_mt.to_3x3().col[1].normalized()
            
            dot_prod = math_utils.clamp(pre_y_vec.dot(tag_y_vec), -1.0, 1.0)
            y_diff = math.acos(dot_prod)
            
            axis_vec = pre_y_vec.cross(tag_y_vec)
            if axis_vec.length > AXIS_THRESHOLD:
                axis_vec.normalize()
                rot_fix = mathutils.Matrix.Rotation(y_diff, 4, axis_vec)
                new_mt = math_utils.rotate_matrix_by_component(new_mt, rot_fix)
            
            new_mt.translation = tag_pos

            # Phase 2: Roll
            new_x_vec = new_mt.to_3x3().col[0].normalized()
            tag_x_vec = tag_mt.to_3x3().col[0].normalized()
            
            dot_val = math_utils.clamp(new_x_vec.dot(tag_x_vec), -1.0, 1.0)
            roll = math.acos(dot_val)
            
            if self.delay > 0:
                roll = roll / self.delay
            else:
                roll = 0
            roll = roll * (1.0 - twst) * dt_scale

            check_vec = new_x_vec.cross(tag_x_vec)
            if check_vec.dot(tag_y_vec) < 0.0:
                roll = -roll

            axis_vec = new_mt.to_3x3().col[1].normalized()
            rot_roll = mathutils.Matrix.Rotation(roll, 4, axis_vec)
            new_mt = math_utils.rotate_matrix_by_component(new_mt, rot_roll)
            new_mt.translation = tag_pos

            # Phase 3: Elasticity
            c_pos = obj_data["pre_mt"][i+1].translation # Current tip pos (from previous frame calculation)
            y_diff = c_pos - tag_pos
            if y_diff.length > 0.000001:
                y_vec = y_diff.normalized()
            else:
                y_vec = new_mt.to_3x3().col[1].normalized()  # Fallback to current Y axis
            new_y_vec = new_mt.to_3x3().col[1].normalized()
            rcs_vec = obj_data["old_vec"][i] * self.recursion

            base_phase = (new_y_vec - (y_vec * strgh))
            # Protect against division by zero (delay min is 1.0, but be safe)
            safe_delay = max(self.delay, 0.001)
            phase_vec = (base_phase / safe_delay) + rcs_vec
            if inrt > 0.0:
                prev_tip = obj_data["old_tip"][i]
                phase_vec += (c_pos - prev_tip) * inrt
            
            # Apply Base Force
            if self.use_force:
                phase_vec += force_vec_world * (1.0 / max(self.delay, 1.0))

            # Apply Wind Object
            if self.use_wind_object and wind_vec_world.length > 0.0:
                phase_vec += wind_vec_world * (1.0 / max(self.delay, 1.0))
            
            # Apply Scene Fields
            if self.use_scene_fields:
                scene_force = self.calculate_scene_forces(tag_pos)
                phase_vec += scene_force * SCENE_FORCE_SCALE * (1.0 / max(self.delay, 1.0))

            phase_vec = phase_vec * dt_scale
            if tens > 0.0:
                phase_vec = phase_vec * (1.0 - tens)

            if phase_vec.length < trshd:
                phase_vec = mathutils.Vector((0.0, 0.0, 0.0))

            y_vec = y_vec + phase_vec
            obj_data["old_vec"][i] = phase_vec

            y_vec.normalize()
            if ((self.use_collision and self._collision_bones) or
                (self.use_collision_plane and self._collision_plane) or
                (self.use_collision_collection and self._collection_colliders)):
                bone_len = obj_data["obj_length"][i+1].translation.length * ext_scale
                if bone_len > 0.0:
                    tip_pos = tag_pos + (y_vec * bone_len)
                    corrected_tip = tip_pos
                    if self.use_collision and self._collision_bones:
                        exclude_names = {obj.name}
                        if obj.parent:
                            exclude_names.add(obj.parent.name)
                        for child in obj.children:
                            exclude_names.add(child.name)
                        corrected_tip = self._apply_capsule_collision(tip_pos, amt_world, exclude_names)
                    if self.use_collision_collection and self._collection_colliders:
                        corrected_tip = self._apply_collection_collision(corrected_tip)
                    if self.use_collision_plane and self._collision_plane:
                        corrected_tip = self._apply_plane_collision(corrected_tip)
                    if (corrected_tip - tag_pos).length > 0.000001:
                        y_vec = (corrected_tip - tag_pos).normalized()
            new_z_vec = new_mt.to_3x3().col[2].normalized()
            x_vec = y_vec.cross(new_z_vec).normalized()
            z_vec = x_vec.cross(y_vec).normalized()
            
            final_rot = mathutils.Matrix((x_vec, y_vec * ext_scale, z_vec)).transposed().to_4x4()
            final_rot.translation = tag_pos
            new_mt = final_rot

            # Apply
            obj.matrix = amt_world.inverted() @ new_mt
            
            context.view_layer.update()
            if insert_key:
                self.set_animkey(obj, context)

            obj_data["pre_mt"][i] = copy.copy(new_mt)
            cur_p_mt = copy.copy(new_mt)
            
            next_start_mt = cur_p_mt @ obj_data["obj_length"][i+1]
            obj_data["pre_mt"][i+1].translation = next_start_mt.translation
            obj_data["old_tip"][i] = c_pos.copy()

    def set_animkey(self, obj, context):
        f = context.scene.frame_current
        bone_name = obj.name

        # Apply blending if weight < 1.0 and we have cached data
        if self.bake_weight < 0.999 and bone_name in self._existing_anim_cache:
            existing_data = self._existing_anim_cache.get(bone_name, {}).get(f)
            if existing_data:
                # Get current spring result
                spring_data = {
                    'loc': obj.location.copy(),
                    'rot_quat': obj.rotation_quaternion.copy(),
                    'rot_euler': obj.rotation_euler.copy(),
                    'scale': obj.scale.copy(),
                }

                # Blend based on mode
                if self.bake_mode == 'ADDITIVE':
                    base_data = self._base_pose_cache.get(bone_name)
                    if base_data:
                        blended = self._blend_additive(existing_data, spring_data, base_data, self.bake_weight)
                    else:
                        blended = self._blend_override(existing_data, spring_data, self.bake_weight)
                else:  # OVERRIDE
                    blended = self._blend_override(existing_data, spring_data, self.bake_weight)

                # Apply blended values
                obj.location = blended['loc']
                obj.rotation_quaternion = blended['rot_quat']
                obj.rotation_euler = blended['rot_euler']
                obj.scale = blended['scale']

        obj.keyframe_insert(data_path='location', frame=f)
        obj.keyframe_insert(data_path='rotation_euler', frame=f)
        obj.keyframe_insert(data_path='rotation_quaternion', frame=f)
        obj.keyframe_insert(data_path='scale', frame=f)

    def delete_anim_keys(self, obj_trees, context, force_delete=False):
        r"""Delete animation keys. When weight < 1.0, keys are preserved for blending."""
        # When blending is active (weight < 1.0), we cache first, then delete
        # The blended result will be written back in set_animkey()
        if not force_delete and self.bake_weight < 0.999:
            # Keys will be overwritten with blended values, no need to delete
            return

        dct_k = sorted(obj_trees.keys())
        for k in dct_k:
            for t in obj_trees[k]:
                for pbn in obj_trees[k][t]["obj_list"]:
                    for f in range(self.sf - 1, self.ef + 1):
                        try:
                            pbn.keyframe_delete(data_path="location", frame=f)
                            pbn.keyframe_delete(data_path="rotation_euler", frame=f)
                            pbn.keyframe_delete(data_path="rotation_quaternion", frame=f)
                            pbn.keyframe_delete(data_path="scale", frame=f)
                        except RuntimeError:
                            # Keyframe doesn't exist at this frame, skip
                            pass
        context.view_layer.update()

    def execute_simulation(self, obj_trees, context, progress_callback=None):
        r"""Execute spring simulation.

        Args:
            obj_trees: Bone chain data structures
            context: Blender context
            progress_callback: Optional callback(current, total) for progress updates
        """
        dct_k = sorted(obj_trees.keys())
        sub_steps = max(1, int(self.sub_steps))
        dt_scale = 1.0 / sub_steps

        total_frames = self.ef - self.sf
        for idx, f in enumerate(range(self.sf + 1, self.ef + 1)):
            context.scene.frame_set(f)
            for s in range(sub_steps):
                insert_key = (s == sub_steps - 1)
                for k in dct_k:
                    for t in obj_trees[k]:
                        self.calculate_step(obj_trees[k][t], context, dt_scale, insert_key)

            # Report progress
            if progress_callback and total_frames > 0:
                progress_callback(idx + 1, total_frames)

        return True

    def match_end_to_start(self, obj_trees, context):
        r"""Set end frame pose to match start frame for seamless loops."""
        if not obj_trees:
            return

        bones = self._get_unique_bones(obj_trees)
        if not bones:
            return

        context.scene.frame_set(self.sf)
        context.view_layer.update()
        start_mats = {b.name: b.matrix.copy() for b in bones}

        context.scene.frame_set(self.ef)
        for bone in bones:
            start_mt = start_mats.get(bone.name)
            if start_mt is None:
                continue
            bone.matrix = start_mt
            self.set_animkey(bone, context)

        context.view_layer.update()
