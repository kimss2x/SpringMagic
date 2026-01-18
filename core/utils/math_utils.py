import mathutils
import math

def clamp(n, minn=0.0, maxn=1.0):
    """Clamp a value between min and max"""
    return max(min(maxn, n), minn)

def rotate_matrix_by_component(mtx, rot_mt):
    r"""
    Apply a rotation matrix to a transform matrix, preserving location and scale.
    mtx: Source Matrix (4x4)
    rot_mt: Rotation Matrix (4x4) or (3x3)
    """
    loc, r_mt, s_mt = mtx.decompose()
    
    pos = mathutils.Matrix.Translation(loc)
    rot = r_mt.to_matrix().to_4x4()
    scl = mathutils.Matrix.Diagonal(s_mt).to_4x4()
    
    # Ensure rot_mt is 4x4
    if len(rot_mt.col) == 3:
        rot_mt = rot_mt.to_4x4()
        
    return pos @ rot_mt @ rot @ scl

def get_hierarchy_depth(obj):
    r"""Get depth of object in hierarchy"""
    # 0 for root, 1 for child...
    # obj should be a PoseBone
    cnt = 0
    parent = obj.parent
    while parent is not None:
        parent = parent.parent
        cnt += 1
    return cnt
