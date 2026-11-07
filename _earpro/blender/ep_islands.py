"""Dump the mesh islands of an ear-pro worn model (no changes) and render them colour-coded with the helmet.

  blender -b --factory-startup --python ep_islands.py -- <config.json>
  {"earpro": "<fbx>", "helmet": ["<fbx>", ...], "out": "<dir>", "tag": "comtac", "views": ["side_L", "back", "front", "top"]}

Frame: Punisherbody model space (+X character right, +Y forward, +Z up), same as ep_mech / ep_rig_export.
"""
import bpy, sys, os, json, random
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ep_common as EC

argv = sys.argv[sys.argv.index("--") + 1:]
CFG = json.load(open(argv[0]))
OUT = CFG["out"]
os.makedirs(OUT, exist_ok=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = []
    for o in new:
        if o.type == 'MESH' and not o.name.upper().startswith(("UCX", "UTM", "USP", "UBX")):
            meshes.append(o)
        elif o.type == 'MESH':
            o.hide_render = True
    return meshes


def baked(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(oe)
    me.transform(o.matrix_world)
    n = bpy.data.objects.new(o.name + "_baked", me)
    bpy.context.scene.collection.objects.link(n)
    o.hide_render = True
    return n


helm = [baked(o) for h in CFG.get("helmet", []) for o in imp(h)]
for h in helm:
    h.color = (0.35, 0.35, 0.33, 1)
ears = [baked(o) for o in imp(CFG["earpro"])]
rep = {"objects": []}
random.seed(3)
for e in ears:
    isl, _ = EC.islands_of(e.data)
    infos = []
    vcol = e.data.color_attributes.new("isl", 'BYTE_COLOR', 'POINT')
    for cid, mem in enumerate(isl):
        pts = [e.data.vertices[i].co for i in mem]
        mn = Vector([min(p[k] for p in pts) for k in range(3)])
        mx = Vector([max(p[k] for p in pts) for k in range(3)])
        col = (random.random(), random.random(), random.random(), 1)
        for i in mem:
            vcol.data[i].color = col
        infos.append({"id": cid, "n": len(mem), "c": [round(v, 4) for v in (mn + mx) / 2], "min": [round(v, 4) for v in mn],
                      "max": [round(v, 4) for v in mx], "col": [round(c, 2) for c in col[:3]]})
    infos.sort(key=lambda d: -d["n"])
    rep["objects"].append({"name": e.name, "verts": len(e.data.vertices), "islands": infos})
json.dump(rep, open(os.path.join(OUT, CFG.get("tag", "ear") + "_islands.json"), "w"), indent=1)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'
sc.render.resolution_x, sc.render.resolution_y = CFG.get("res", [700, 700])
cd = bpy.data.cameras.new("cam")
cd.type = 'ORTHO'
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
C = Vector(CFG.get("centre", (0, -0.02, 1.66)))
views = {"side_L": Vector((-1, 0, 0)), "side_R": Vector((1, 0, 0)), "back": Vector((0, -1, 0.1)), "front": Vector((0, 1, 0.1)),
         "top": Vector((0, -0.05, 1)), "back34_L": Vector((-0.8, -0.8, 0.4))}
for vn in CFG.get("views", ["side_L", "back", "front", "top"]):
    d = views[vn].normalized()
    cam.location = C + d * 1.5
    cam.rotation_euler = (C - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cd.ortho_scale = CFG.get("scale", 0.42)
    # pass 1: islands coloured (vertex colours), helmet grey
    sc.display.shading.color_type = 'VERTEX'
    for h in helm:
        h.hide_render = True
    sc.render.filepath = os.path.join(OUT, f"{CFG.get('tag', 'ear')}_{vn}_islands.png")
    bpy.ops.render.render(write_still=True)
    for h in helm:
        h.hide_render = False
    sc.display.shading.color_type = 'OBJECT'
    for e in ears:
        e.color = (0.75, 0.62, 0.42, 1)
    sc.render.filepath = os.path.join(OUT, f"{CFG.get('tag', 'ear')}_{vn}_helmet.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
