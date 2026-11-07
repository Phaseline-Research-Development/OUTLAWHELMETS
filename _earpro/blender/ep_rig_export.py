"""Re-rig an existing ear-pro worn model for articulation. NO geometry, UV or material change: vertices are only
re-weighted (and, for the OWN variant, rigidly expressed in the Head-pivot frame).

  blender -b --factory-startup --python ep_rig_export.py -- <config.json>

config: {"earpro": "<worn fbx>", "out_dir": "<dir>", "base_name": "OpsCore_AMP", "variants": ["INH", "OWN"],
         "classify": {...optional overrides...}, "report": "<json>"}

INH  full character skeleton (as today, skinned to Head) + EP_Arm_L/R, EP_Cup_L/R parented to Head.
     For a slot with InheritParentSkeleton 1 (no prefab change).
OWN  own skeleton EP_Root (the Head pivot) -> EP_Arm_* -> EP_Cup_*; mesh in Head-pivot space.
     For a slot with PivotID "Head" (the pattern NVG Systems uses for its own-skeleton NVG mounts).
Bones: root points +Z, articulated bones point +Y (Blender), roll 0 - the directions proven on the CRRC.
"""
import bpy, sys, os, json, math
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ep_common as EC

argv = sys.argv[sys.argv.index("--") + 1:]
CFG = json.load(open(argv[0]))
OUTD = CFG["out_dir"]
BASE = CFG.get("base_name", "OpsCore_AMP")
REPORT = {"variants": {}}
LOGF = open(CFG.get("log", os.path.join(OUTD, BASE + "_rig_log.txt")), "w", encoding="utf-8")
sys.stdout = LOGF
sys.stderr = LOGF


def log(*a):
    print(*a)
    LOGF.flush()


FBX_KW = dict(use_selection=True, use_visible=False, use_active_collection=False, global_scale=1.0,
              apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', use_space_transform=True,
              bake_space_transform=False, object_types={'ARMATURE', 'MESH'}, use_mesh_modifiers=True,
              use_mesh_modifiers_render=True, mesh_smooth_type='OFF', colors_type='NONE', use_subsurf=False,
              use_mesh_edges=False, use_tspace=False, use_triangles=False, use_custom_props=False,
              add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X', use_armature_deform_only=False,
              armature_nodetype='NULL', bake_anim=False, path_mode='AUTO', embed_textures=False, batch_mode='OFF',
              axis_forward='-Z', axis_up='Y')


def fresh_import(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    arm = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    ms = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.upper().startswith(("UCX", "UTM"))]
    return (arm[0] if arm else None), ms


def uv_signature(mesh):
    sig = []
    for uvl in mesh.uv_layers:
        sig.append(sorted((round(d.uv.x, 5), round(d.uv.y, 5)) for d in uvl.data))
    return sig


def rest_world(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    return EC.evaluated_coords(obj, dg)


# ------------------------------------------------------------------ source
arm0, ms0 = fresh_import(CFG["earpro"])
assert len(ms0) == 1, [m.name for m in ms0]
SRC = ms0[0]
V = rest_world(SRC)
ISL, COMP = EC.islands_of(SRC.data)
info, part, piv, vpart = EC.classify(V, ISL, CFG.get("classify"), log)
SRC_UV = uv_signature(SRC.data)
SRC_COUNTS = (len(SRC.data.vertices), len(SRC.data.polygons), len(SRC.data.loops))
log("source", CFG["earpro"], "verts/polys/loops", SRC_COUNTS, "materials", [m.name for m in SRC.data.materials])
REPORT["pivots_model_space"] = {("R" if s > 0 else "L"): {k: list(v) for k, v in p.items() if isinstance(v, Vector)}
                                for s, p in piv.items()}
REPORT["parts"] = {}
for cid, (kind, s) in part.items():
    REPORT["parts"].setdefault(f"{kind}_{'R' if s > 0 else 'L'}", []).append(cid)


def set_weights(mesh_obj, bone_of_vertex):
    for g in list(mesh_obj.vertex_groups):
        mesh_obj.vertex_groups.remove(g)
    groups = {}
    by_bone = {}
    for i, b in enumerate(bone_of_vertex):
        by_bone.setdefault(b, []).append(i)
    for b, idx in by_bone.items():
        g = mesh_obj.vertex_groups.new(name=b)
        g.add(idx, 1.0, 'REPLACE')
        groups[b] = len(idx)
    return groups


def export(objs, path):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=path, **FBX_KW)
    log("exported", path)


def verify(path, to_model):
    """re-import, compare rest positions (mapped back to model space) and UVs with the source"""
    arm, ms = fresh_import(path)
    m = [o for o in ms if o.name.startswith(BASE)] or ms
    m = m[0]
    W = [to_model @ v for v in rest_world(m)]
    kd = KDTree(len(V))
    for i, v in enumerate(V):
        kd.insert(v, i)
    kd.balance()
    dev = max(kd.find(w)[2] for w in W)
    counts = (len(m.data.vertices), len(m.data.polygons), len(m.data.loops))
    uv_same = uv_signature(m.data) == SRC_UV
    bones = [b.name for b in arm.data.bones] if arm else []
    mats = [x.name for x in m.data.materials]
    res = {"max_vertex_deviation_mm": round(dev * 1000, 4), "counts": counts, "source_counts": SRC_COUNTS,
           "uv_identical": uv_same, "materials": mats, "bones": len(bones),
           "ep_bones": [b for b in bones if b.startswith("EP_")]}
    log("verify", os.path.basename(path), json.dumps(res))
    return res


# ------------------------------------------------------------------ INH
if "INH" in CFG.get("variants", ["INH", "OWN"]):
    arm, ms = fresh_import(CFG["earpro"])
    mesh = ms[0]
    aw_inv = arm.matrix_world.inverted()
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    head = eb["Head"]
    made = {}
    for s in (-1, 1):
        sd = "L" if s < 0 else "R"
        for kind, pt in (("Arm", piv[s]["P"]), ("Cup", piv[s]["G"])):
            nm = f"EP_{kind}_{sd}"
            b = eb.new(nm)
            b.head = aw_inv @ pt
            b.tail = aw_inv @ (pt + Vector((0, 0.03, 0)))
            b.roll = 0.0
            b.parent = head if kind == "Arm" else made[f"EP_Arm_{sd}"]
            b.use_connect = False
            made[nm] = b
    bpy.ops.object.mode_set(mode='OBJECT')
    bone_of = []
    for i in range(len(V)):
        kind, s = vpart[i]
        bone_of.append("Head" if kind == "SHOE" else EC.BONES[(kind, s)])
    groups = set_weights(mesh, bone_of)
    log("INH groups", groups)
    p = os.path.join(OUTD, BASE + "_RigInh.fbx")
    export([arm, mesh], p)
    REPORT["variants"]["INH"] = {"fbx": p, "groups": groups, "verify": verify(p, Matrix.Identity(4))}

# ------------------------------------------------------------------ OWN
if "OWN" in CFG.get("variants", ["INH", "OWN"]):
    arm, ms = fresh_import(CFG["earpro"])
    src = ms[0]
    Vw = rest_world(src)
    newme = src.data.copy()
    newme.name = BASE
    for i, v in enumerate(newme.vertices):
        v.co = EC.HEAD_INV @ Vw[i]
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    ad = bpy.data.armatures.new(BASE + "_Skeleton")
    ao = bpy.data.objects.new(BASE + "_Skeleton", ad)
    bpy.context.scene.collection.objects.link(ao)
    bpy.context.view_layer.objects.active = ao
    bpy.ops.object.mode_set(mode='EDIT')
    root = ad.edit_bones.new("EP_Root")
    root.head = (0, 0, 0)
    root.tail = (0, 0, 0.05)
    made = {}
    for s in (-1, 1):
        sd = "L" if s < 0 else "R"
        for kind, pt in (("Arm", piv[s]["P"]), ("Cup", piv[s]["G"])):
            nm = f"EP_{kind}_{sd}"
            b = ad.edit_bones.new(nm)
            lp = EC.HEAD_INV @ pt
            b.head = lp
            b.tail = lp + Vector((0, 0.03, 0))
            b.roll = 0.0
            b.parent = root if kind == "Arm" else made[f"EP_Arm_{sd}"]
            made[nm] = b
    bpy.ops.object.mode_set(mode='OBJECT')
    mo = bpy.data.objects.new(BASE, newme)
    bpy.context.scene.collection.objects.link(mo)
    mo.parent = ao
    mod = mo.modifiers.new("Armature", 'ARMATURE')
    mod.object = ao
    bone_of = []
    for i in range(len(Vw)):
        kind, s = vpart[i]
        bone_of.append("EP_Root" if kind == "SHOE" else EC.BONES[(kind, s)])
    groups = set_weights(mo, bone_of)
    log("OWN groups", groups)
    p = os.path.join(OUTD, BASE + "_RigOwn.fbx")
    export([ao, mo], p)
    REPORT["variants"]["OWN"] = {"fbx": p, "groups": groups, "verify": verify(p, EC.HEAD_M),
                                 "bone_rest_head_local": {k: list(EC.HEAD_INV @ (piv[-1 if k.endswith("L") else 1]["P" if "Arm" in k else "G"]))
                                                          for k in ("EP_Arm_L", "EP_Arm_R", "EP_Cup_L", "EP_Cup_R")}}

json.dump(REPORT, open(CFG.get("report", os.path.join(OUTD, BASE + "_rig_report.json")), "w"), indent=1)
log("DONE")
LOGF.close()
