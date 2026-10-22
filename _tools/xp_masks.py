"""Layer masks for the user's MCB HELMET.spp stack on the Ops-Core FAST XP / XP Carbon (derived from maritime_masks.py), in the Maritime's own UV layout (Blender 4.5).

  blender -b --python _tools/maritime_masks.py

Every Maritime island that is the same piece as an SF_V2 "Base" island (harness, pads, liner, shroud: same vertex count within 2,
centroid within 6 mm after the Shadows fast_survey alignment) takes, face by face, the layer that covers the matching SF face in
the user's MCB texture (layer_regions.npz = which stack layer is on top at each SF texel, measured from the .spp). Everything
else: the outer shell -> Plastic Grainy Soft (shell paint), KitA loop panels -> Bebra_Velcro, rails/other hardware ->
Plastic Composite. Writes 4096 masks _tools/work/maritime/painter/masks/mt_<class>.png (MT texture set) - the KitA texture
set is velcro everywhere.
"""
import bpy, bmesh, os, json
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw

TOOLS = os.path.dirname(os.path.abspath(__file__))
SRC = "D:/3D Source Library/Headgear/"
OUT = os.path.join(TOOLS, "work", "xp", "painter", "masks")
REG = np.load(os.path.join(TOOLS, "work", "painter", "layer_regions.npz"))
LAYER_CLASS = {"04_Rubber_Raw": "rubber", "05_Plastic_Composite": "composite", "06_Plastic_Base_Grain": "grain",
               "07_Nylon_Webbing": "nylon", "08_Plastic_Grainy_Soft": "shell", "09_Bebra_Velcro": "velcro"}
CLASSES = ["shell", "composite", "nylon", "velcro", "grain", "rubber"]
RES = 4096
# loop panels (user 2026-09-30: "the boxes and bands ... are velcro"): separate sheets lying on the outer shell - the top band
# with the tab and the rear band. Islands whose median gap to the shell is under PANEL_D and whose area is over PANEL_A.
PANEL_D, PANEL_A = 0.002, 0.005

sv = json.load(open("C:/Users/lebea/Documents/Github/Shadows-Helmets/_tools/work/fast_survey.json"))["XP"]
R_mt, t_mt = np.array(sv["R"]), np.array(sv["t"])


def imp(path):
    b = set(bpy.data.objects); bpy.ops.import_scene.fbx(filepath=path)
    out = {}
    for o in [x for x in bpy.data.objects if x not in b]:
        if o.type == 'MESH':
            o.data.transform(o.matrix_world); o.matrix_world.identity(); out[o.name.split(".")[0]] = o
    return out


def islands_faces(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    comp = [-1] * len(bm.verts); k = 0
    for v in bm.verts:
        if comp[v.index] >= 0:
            continue
        st = [v]; comp[v.index] = k
        while st:
            x = st.pop()
            for e in x.link_edges:
                w = e.other_vert(x)
                if comp[w.index] < 0:
                    comp[w.index] = k; st.append(w)
        k += 1
    bm.free()
    comp = np.array(comp)
    return comp, k


import sys
for OBJ, TSET in (("XP 3 Hole", "XP1"), ("Carbon 3 Hole", "Carbon1")):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    base = imp(SRC + "SF_V2/SF_V2/Opscore SF-FTHS.fbx")["Base"]
    mt = imp(SRC + "OpscoreXP_Carbon/OpscoreXP_Carbon/xp_carbon.fbx")[OBJ]
    BV = np.array([v.co[:] for v in base.data.vertices])
    MV = (R_mt @ np.array([v.co[:] for v in mt.data.vertices]).T).T + t_mt
    bcomp, bn = islands_faces(base)
    mcomp, mn = islands_faces(mt)
    b_isl = [np.where(bcomp == i)[0] for i in range(bn)]
    b_cent = np.array([BV[g].mean(0) for g in b_isl]); b_cnt = np.array([len(g) for g in b_isl])
    buv = base.data.uv_layers[0].data
    b_face_uv = np.array([np.mean([buv[li].uv[:] for li in p.loop_indices], 0) for p in base.data.polygons])
    b_face_of_vert = {}
    for p in base.data.polygons:
        for v in p.vertices:
            b_face_of_vert.setdefault(v, p.index)
    kd_b = {}
    
    
    def sf_class_at(uv):
        x = min(1023, max(0, int(uv[0] * 1024))); y = min(1023, max(0, int((1 - uv[1]) * 1024)))
        for layer, cls in LAYER_CLASS.items():
            if REG[layer][y, x]:
                return cls
        return None
    
    
    # island match MT -> Base
    m_to_b = {}
    for i in range(mn):
        g = np.where(mcomp == i)[0]; c = MV[g].mean(0)
        cand = np.where(np.abs(b_cnt - len(g)) <= 2)[0]
        if len(cand):
            d = np.linalg.norm(b_cent[cand] - c, axis=1); j = int(np.argmin(d))
            if d[j] < 0.006:
                m_to_b[i] = int(cand[j])
    print("MT islands", mn, "matched to SF Base islands", len(m_to_b))
    
    mats = [m.name.split(".")[0] for m in mt.data.materials]
    muv = mt.data.uv_layers[0].data
    sizes = {i: int((mcomp == i).sum()) for i in range(mn)}
    shell_island = max((i for i in sizes if any(mats[p.material_index] == TSET for p in mt.data.polygons if mcomp[p.vertices[0]] == i)), key=sizes.get)
    SHELL_C = MV[np.where(mcomp == shell_island)[0]].mean(0) - np.array([0.0, 0.0, 0.03])
    _sv = MV[np.where(mcomp == shell_island)[0]]
    r_shell = np.linalg.norm(_sv - SHELL_C, axis=1).mean()
    inside = set(i for i in range(mn) if i != shell_island and i not in m_to_b and
                 np.linalg.norm(MV[np.where(mcomp == i)[0]] - SHELL_C, axis=1).mean() < r_shell - 0.006)
    print("islands inside the shell (liner)", len(inside))
    sbm = bmesh.new(); sbm.from_mesh(mt.data); sbm.faces.ensure_lookup_table()
    bmesh.ops.delete(sbm, geom=[f for f in sbm.faces if mcomp[f.verts[0].index] != shell_island], context='FACES')
    for v in sbm.verts:
        v.co = Vector((R_mt @ np.array(v.co[:])) + t_mt)
    shell_tree = BVHTree.FromBMesh(sbm); sbm.free()
    isl_area = np.zeros(mn)
    for p in mt.data.polygons:
        isl_area[mcomp[p.vertices[0]]] += p.area
    velcro = set()
    for i in range(mn):
        if i == shell_island or i in m_to_b or i in inside:
            continue
        g = np.where(mcomp == i)[0]
        d = np.median([shell_tree.find_nearest(Vector(MV[j]))[3] for j in g])
        if d < PANEL_D and isl_area[i] > PANEL_A:
            velcro.add(i)
            print("loop panel island", i, "verts", len(g), "median gap %.4f" % d, "area %.1f" % isl_area[i], "centre", np.round(MV[g].mean(0), 3))
    face_cls = []
    for p in mt.data.polygons:
        isl = mcomp[p.vertices[0]]
        cls = None
        if mats[p.material_index] != TSET:
            cls = None
        elif isl in m_to_b:
            bi = m_to_b[isl]
            if bi not in kd_b:
                g = b_isl[bi]; kd = KDTree(len(g))
                for j, vi in enumerate(g):
                    kd.insert(BV[vi], int(vi))
                kd.balance(); kd_b[bi] = kd
            c = MV[list(p.vertices)].mean(0)
            _, bv, _ = kd_b[bi].find(Vector(c))
            cls = sf_class_at(b_face_uv[b_face_of_vert[bv]])
        elif isl == shell_island:
            n = np.cross(MV[p.vertices[1]] - MV[p.vertices[0]], MV[p.vertices[2]] - MV[p.vertices[0]])
            fc = MV[list(p.vertices)].mean(0)
            cls = "shell" if np.dot(n, fc - SHELL_C) > 0 else None       # outer face = shell paint, inner liner keeps the base (as on the SF)
        elif isl in inside:
            cls = None                                            # liner / pads inside the shell keep the vendor base (as on the SF)
        elif isl in velcro:
            cls = "velcro"
        else:
            cls = "composite"
        face_cls.append(cls)
    from collections import Counter
    print("face classes", Counter(face_cls))
    
    os.makedirs(OUT, exist_ok=True)
    imgs = {c: Image.new("L", (RES, RES), 0) for c in CLASSES}
    draws = {c: ImageDraw.Draw(imgs[c]) for c in CLASSES}
    for p, cls in zip(mt.data.polygons, face_cls):
        if cls is None or mats[p.material_index] != TSET:
            continue
        pts = [(muv[li].uv[0] * RES, (1 - muv[li].uv[1]) * RES) for li in p.loop_indices]
        draws[cls].polygon(pts, fill=255, outline=255)
    from PIL import ImageFilter
    for c in CLASSES:
        im = imgs[c].filter(ImageFilter.MaxFilter(9))
        im.save(os.path.join(OUT, f"{TSET}_{c}.png"))
        print(c, round((np.asarray(im) > 0).mean() * 100, 2), "%")
    