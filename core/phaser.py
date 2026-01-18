# -*- coding: utf-8 -*-
import mathutils
import copy
import math
import numpy as np
from .utils import math_utils

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

        # Collision
        self.use_collision = False
        self.collision_margin = 0.0
        self.collision_length_offset = 0.0
        self.use_collision_collection = False
        self.collision_collection = None
        self._collision_bones = []
        self._collection_colliders = []

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
        r"""Initialize matrices and vectors"""
        dct_k = sorted(obj_trees.keys())
        amt = context.active_object
        amt_world = amt.matrix_world

        # Cache fields once if enabled
        if self.use_scene_fields:
            self._cache_scene_fields(context)
        if self.use_collision:
            self._cache_collision_bones(obj_trees)
        if self.use_collision_collection:
            self._cache_collection_colliders()

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

        return obj_trees

    def _cache_scene_fields(self, context):
        r"""Find relevant force fields in the scene"""
        self._cached_fields = []
        for obj in context.scene.objects:
            if obj.field and obj.field.type in {'WIND', 'FORCE', 'VORTEX'}: # Support simplified types
                 self._cached_fields.append(obj)

    def _cache_collision_bones(self, obj_trees):
        r"""Collect bones used for collision checks"""
        self._collision_bones = self._get_unique_bones(obj_trees)

    def _cache_collection_colliders(self):
        r"""Collect collection objects with rigid body collision shapes"""
        self._collection_colliders = []
        if not self.collision_collection:
            return
        for obj in self.collision_collection.all_objects:
            if obj.type != 'MESH':
                continue
            shape = None
            margin = 0.0
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
            if not shape:
                continue
            if shape in {'CONVEX_HULL', 'MESH'}:
                shape = 'BOX'
            self._collection_colliders.append({
                "obj": obj,
                "shape": shape,
                "margin": margin
            })

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
                force_vec = direction * (strength * falloff * 20.0) # Scale factor to match Blender feeling roughly
                total_force += force_vec
                
        return total_force

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
        
        for i in range(len(obj_data["obj_list"])):
            obj = obj_data["obj_list"][i]
            
            tag_mt = cur_p_mt @ obj_data["obj_length"][i]
            
            pre_mt = copy.copy(obj_data["pre_mt"][i])
            new_mt = copy.copy(obj_data["pre_mt"][i])
            tag_pos = tag_mt.translation

            # Align Y
            pre_y_vec = pre_mt.to_3x3().col[1].normalized()
            tag_y_vec = tag_mt.to_3x3().col[1].normalized()
            
            dot_prod = math_utils.clamp(pre_y_vec.dot(tag_y_vec), -1.0, 1.0)
            y_diff = math.acos(dot_prod)
            
            axis_vec = pre_y_vec.cross(tag_y_vec)
            if axis_vec.length > 0.0001:
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
            y_vec = (c_pos - tag_pos).normalized()
            new_y_vec = new_mt.to_3x3().col[1].normalized()
            rcs_vec = obj_data["old_vec"][i] * self.recursion
            
            base_phase = (new_y_vec - (y_vec * strgh))
            phase_vec = (base_phase / self.delay) + rcs_vec
            if inrt > 0.0:
                prev_tip = obj_data["old_tip"][i]
                phase_vec += (c_pos - prev_tip) * inrt
            
            # Apply Base Force
            if self.use_force:
                phase_vec += force_vec_world * (1.0 / max(self.delay, 1.0))
            
            # Apply Scene Fields
            if self.use_scene_fields:
                # Calculate effect at the bone root (tag_pos)
                scene_force = self.calculate_scene_forces(tag_pos)
                # Apply to phase
                # Scene forces can be strong, we might want to scale them or let user adjust strength
                # Using 0.01 factor to tame raw values typically returned by physics engines
                phase_vec += scene_force * 0.01 * (1.0 / max(self.delay, 1.0))

            phase_vec = phase_vec * dt_scale
            if tens > 0.0:
                phase_vec = phase_vec * (1.0 - tens)

            if phase_vec.length < trshd:
                phase_vec = mathutils.Vector((0.0, 0.0, 0.0))

            y_vec = y_vec + phase_vec
            obj_data["old_vec"][i] = phase_vec

            y_vec.normalize()
            if ((self.use_collision and self._collision_bones) or
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
        obj.keyframe_insert(data_path='location', frame=f)
        obj.keyframe_insert(data_path='rotation_euler', frame=f)
        obj.keyframe_insert(data_path='rotation_quaternion', frame=f)
        obj.keyframe_insert(data_path='scale', frame=f)

    def delete_anim_keys(self, obj_trees, context):
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
                        except:
                            pass
        context.view_layer.update()

    def execute_simulation(self, obj_trees, context):
        dct_k = sorted(obj_trees.keys())
        sub_steps = max(1, int(self.sub_steps))
        dt_scale = 1.0 / sub_steps

        for f in range(self.sf + 1, self.ef + 1):
            context.scene.frame_set(f)
            for s in range(sub_steps):
                insert_key = (s == sub_steps - 1)
                for k in dct_k:
                    for t in obj_trees[k]:
                        self.calculate_step(obj_trees[k][t], context, dt_scale, insert_key)
        
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
