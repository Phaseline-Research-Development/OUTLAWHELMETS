"""Build the Ops-Core Maritime for OUTLAWHELMETS (Blender 4.5 headless, run on the user's SF .blend).

  blender -b "<Fast SF v2 BUMP AND BALLISTIC HELMET.blend>" --python _tools/build_maritime.py

Source: Documents/Assets/Headgear/OpscoreMaritime/.../MT.fbx - same Arma-3-style FAST family as SF_V2, identical harness islands.
1. Placement = the transform the user's SF has: SF_V2 source "SF" shell -> the .blend's "SF" object (UV-matched Kabsch), applied
   to the Maritime after aligning it onto SF_V2 (Shadows-Helmets fast_survey.json "MT").
2. Chin strap (user: "make sure the chin strap is sculpted correctly like the sf helmets"): every Maritime harness vertex takes
   the position of the matching vertex of the SF's harness in the .blend (islands matched by size/centroid, vertices by nearest
   in the source frame). The Maritime keeps its own UVs/textures.
3. Split: rails (Maritime rails, removable part) vs everything else (shell + liner + shroud + KitA velcro + harness).
Writes worn/_Item FBX (skinned to Head, OUTLAW armature) to _tools/work/maritime/fbx and a check render.
"""
import bpy, bmesh, os, json, math
import numpy as np
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

TOOLS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(TOOLS, "work", "maritime", "fbx")
TEMPLATE = os.path.join(TOOLS, "template", "SF V2 Bump (Rigged).fbx")
SRC = "D:/3D Source Library/Headgear/"
SURVEY = "C:/Users/lebea/Documents/Github/Shadows-Helmets/_tools/work/fast_survey.json"
ITEM_SHIFT = (0.0, 0.02, -1.70)
UCX_MAT = "plastic_5EAA7FB0A83F90CF"
UTM_MAT = "hard_aramid_CF50027087BA3402"


def imp(path, prefix):
    b = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    out = {}
    for o in [x for x in bpy.data.objects if x not in b]:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        me = o.data
        me.transform(o.matrix_world); o.matrix_world = Matrix.Identity(4); o.parent = None
        out[o.name.split(".")[0]] = o
        o.name = prefix + o.name.split(".")[0]
    return out


def verts(o):
    return np.array([v.co[:] for v in o.data.vertices])


def uv_of_verts(o):
    uv = o.data.uv_layers[0].data
    res = {}
    for li, l in enumerate(o.data.loops):
        res.setdefault(l.vertex_index, (round(uv[li].uv[0], 5), round(uv[li].uv[1], 5)))
    return res


def kabsch(A, B):
    ca, cb = A.mean(0), B.mean(0)
    H = (A - ca).T @ (B - cb)
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return R, cb - R @ ca


def islands(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.verts.ensure_lookup_table()
    seen = [False] * len(bm.verts); out = []
    for v in bm.verts:
        if seen[v.index]:
            continue
        st = [v]; seen[v.index] = True; g = []
        while st:
            x = st.pop(); g.append(x.index)
            for e in x.link_edges:
                w = e.other_vert(x)
                if not seen[w.index]:
                    seen[w.index] = True; st.append(w)
        out.append(g)
    bm.free()
    return out


def split(o, groups, names):
    res = []
    for g, n in zip(groups, names):
        c = o.copy(); c.data = o.data.copy(); c.name = n
        bpy.context.scene.collection.objects.link(c)
        keep = set(g)
        bm = bmesh.new(); bm.from_mesh(c.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context='VERTS')
        bm.to_mesh(c.data); bm.free()
        res.append(c)
    return res


def import_template():
    ua = bpy.data.objects.get("Armature")
    if ua:
        ua.name = "UserArmature"
    b = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=TEMPLATE)
    new = [o for o in bpy.data.objects if o not in b]
    arm = next(o for o in new if o.type == 'ARMATURE')
    for o in new:
        if o.type == 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    arm.name = "Armature"
    return arm


def skin(o, arm):
    o.vertex_groups.clear()
    g = o.vertex_groups.new(name="Head"); g.add(list(range(len(o.data.vertices))), 1.0, 'REPLACE')
    mw = o.matrix_world.copy(); o.parent = arm; o.parent_type = 'OBJECT'; o.matrix_world = mw
    o.modifiers.new("Armature", 'ARMATURE').object = arm


def utm_of(src):
    me = src.data.copy(); u = bpy.data.objects.new("UTM_Helmet", me); bpy.context.scene.collection.objects.link(u)
    d = u.modifiers.new("dec", 'DECIMATE'); d.ratio = min(1.0, 2400.0 / max(1, len(me.polygons)))
    dg = bpy.context.evaluated_depsgraph_get(); me2 = bpy.data.meshes.new_from_object(u.evaluated_get(dg))
    u.modifiers.clear(); u.data = me2; me2.materials.clear()
    me2.materials.append(bpy.data.materials.get(UTM_MAT) or bpy.data.materials.new(UTM_MAT))
    while len(me2.uv_layers):
        me2.uv_layers.remove(me2.uv_layers[0])
    return u


def ucx(obj, name):
    pts = np.array([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    b0 = bmesh.new()
    for p in pts:
        b0.verts.new(p)
    bmesh.ops.convex_hull(b0, input=b0.verts)
    hv = np.array([tuple(v.co) for v in b0.verts if v.link_faces]); b0.free()
    idx = [int(np.argmax(np.linalg.norm(hv - hv.mean(0), axis=1)))]
    dd = np.linalg.norm(hv - hv[idx[0]], axis=1)
    for _ in range(min(64, len(hv)) - 1):
        i = int(np.argmax(dd)); idx.append(i); dd = np.minimum(dd, np.linalg.norm(hv - hv[i], axis=1))
    bm = bmesh.new()
    for p in hv[idx]:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    me.materials.append(bpy.data.materials.get(UCX_MAT) or bpy.data.materials.new(UCX_MAT))
    return o


def export(path, objs, active, types):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = active
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types=types, add_leaf_bones=False, bake_anim=False,
                             use_armature_deform_only=False, mesh_smooth_type='FACE', apply_unit_scale=True, use_space_transform=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    user_sf = bpy.data.objects["SF"]
    U = np.array([tuple(user_sf.matrix_world @ v.co) for v in user_sf.data.vertices])
    sfv2 = imp(SRC + "SF_V2/SF_V2/Opscore SF-FTHS.fbx", "S_")
    mt = imp(SRC + "OpscoreMaritime/OpscoreMaritime/MT.fbx", "M_")["MT"]

    # 1. source SF_V2 -> the user's export placement (UV-matched Kabsch on the SF shell)
    src_shell = sfv2["SF"]
    uv_src = uv_of_verts(src_shell); uv_usr = {}
    for vi, uv in uv_of_verts(user_sf).items():
        uv_usr.setdefault(uv, vi)
    pairs = [(vi, uv_usr[uv]) for vi, uv in uv_src.items() if uv in uv_usr]
    A = verts(src_shell)[[p[0] for p in pairs]]; B = U[[p[1] for p in pairs]]
    R, t = kabsch(A, B)
    res = np.linalg.norm((R @ A.T).T + t - B, axis=1)
    print("USER TRANSFORM pairs", len(pairs), "rms %.5f max %.5f" % (np.sqrt((res ** 2).mean()), res.max()))
    T_user = np.eye(4); T_user[:3, :3] = R; T_user[:3, 3] = t
    sv = json.load(open(SURVEY))["MT"]
    M_mt = np.eye(4); M_mt[:3, :3] = np.array(sv["R"]); M_mt[:3, 3] = np.array(sv["t"])

    # 2. the SF harness as the user has it: SF_V2 Base islands (harness = small islands, not the shroud), located in the user's SF
    base = sfv2["Base"]; BV = verts(base)
    kd_user = KDTree(len(U))
    for i, p in enumerate(U):
        kd_user.insert(p, i)
    kd_user.balance()
    uvb = uv_of_verts(base)
    base_to_user = {}
    for vi, uv in uvb.items():
        if uv in uv_usr:
            base_to_user[vi] = uv_usr[uv]
    harness_islands = []
    for g in islands(base):
        c = BV[g].mean(0)
        if len(g) < 1000 and not (c[1] < -0.09 and c[2] > 0.74):
            harness_islands.append(g)
    print("SF harness islands", len(harness_islands), "verts", sum(len(g) for g in harness_islands),
          "mapped to user SF", sum(1 for g in harness_islands for v in g if v in base_to_user))

    # 3. Maritime: into the SF_V2 source frame, match harness islands, copy the user's harness positions
    MV_src = (M_mt[:3, :3] @ verts(mt).T).T + M_mt[:3, 3]
    mt_isl = islands(mt)
    hv = np.array([BV[g].mean(0) for g in harness_islands]); hn = [len(g) for g in harness_islands]
    new_pos = (T_user[:3, :3] @ MV_src.T).T + T_user[:3, 3]
    orig_pos = new_pos.copy()
    harness_mt, used = [], set()
    for g in mt_isl:
        c = MV_src[g].mean(0)
        best = None
        for k, (hc, n) in enumerate(zip(hv, hn)):
            if k in used or abs(n - len(g)) > 2:
                continue
            d = np.linalg.norm(hc - c)
            if d < 0.006 and (best is None or d < best[1]):
                best = (k, d)
        if best is None:
            continue
        used.add(best[0]); harness_mt.extend(g)
        bg = harness_islands[best[0]]
        kd = KDTree(len(bg))
        for j, bi in enumerate(bg):
            kd.insert(BV[bi], j)
        kd.balance()
        for vi in g:
            _, j, _ = kd.find(Vector(MV_src[vi]))
            bi = bg[j]
            if bi in base_to_user:
                new_pos[vi] = U[base_to_user[bi]]
    moved = np.linalg.norm(new_pos[harness_mt] - orig_pos[harness_mt], axis=1)
    print("MT harness islands matched", len(used), "of", len(harness_islands), "verts", len(harness_mt),
          "moved to SF strap: max %.4f m, verts moved >1mm %d" % (moved.max() if len(moved) else 0, int((moved > 0.001).sum())))
    for i, v in enumerate(mt.data.vertices):
        v.co = Vector(new_pos[i])

    # 4. split: rails vs the rest (Shadows fast_rule, in the SF_V2 source frame)
    hs = set(harness_mt); rails, rest = [], []
    for g in mt_isl:
        c = MV_src[g].mean(0); n = len(g)
        is_rail = not (set(g) & hs) and ((n >= 1000 and abs(c[0]) > 0.06) or (70 <= n <= 76 and abs(c[0]) > 0.078))
        (rails if is_rail else rest).extend(g)
    shell, rail = split(mt, [rest, rails], ["MT_Shell", "MT_Rails"])
    print("SPLIT shell verts", len(shell.data.vertices), "rails verts", len(rail.data.vertices))
    bpy.data.objects.remove(mt, do_unlink=True)

    arm = import_template()
    for part, o, utm in (("MT_Shell", shell, True), ("MT_Rails", rail, False)):
        V = verts(o)
        print("PART", part, [m.name for m in o.data.materials], V.min(0).round(4).tolist(), V.max(0).round(4).tolist())
        preview = o.copy(); preview.data = o.data.copy(); preview.name = part + "_preview"
        bpy.context.scene.collection.objects.link(preview)
        item = o.copy(); item.data = o.data.copy(); item.name = part + "_it"
        bpy.context.scene.collection.objects.link(item)
        o.name = part
        worn = [o]; skin(o, arm)
        if utm:
            u = utm_of(o); u.matrix_world = Matrix.Identity(4); skin(u, arm); worn.append(u)
        export(os.path.join(OUT, part + ".fbx"), [arm] + worn, arm, {'ARMATURE', 'MESH', 'EMPTY'})
        for x in worn:
            bpy.data.objects.remove(x, do_unlink=True)
        item.data.transform(Matrix.Translation(Vector(ITEM_SHIFT))); item.name = part
        h = ucx(item, "UCX_Item")
        export(os.path.join(OUT, part + "_Item.fbx"), [item, h], item, {'MESH'})
        bpy.data.objects.remove(item, do_unlink=True); bpy.data.objects.remove(h, do_unlink=True)

    # check render: Maritime vs the user's SF on the body
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.hide_render = True
    bpy.data.objects["Body_LOD0"].hide_render = False
    sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'SINGLE'
    sc.render.resolution_x = 600; sc.render.resolution_y = 600
    cd = bpy.data.cameras.new('c'); cd.type = 'ORTHO'; cd.ortho_scale = 0.42
    cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
    tgt = Vector((0, 0.0, 1.64))
    for label, objs in (("sf", [bpy.data.objects["SF"], bpy.data.objects["Rails"]]), ("mt", [bpy.data.objects["MT_Shell_preview"], bpy.data.objects["MT_Rails_preview"]])):
        for o in bpy.data.objects:
            if o.type == 'MESH' and o.name != "Body_LOD0":
                o.hide_render = o not in objs
        for view, d in (("front", Vector((0, 1, 0))), ("side", Vector((1, 0, 0))), ("q", Vector((0.6, 0.7, -0.1)))):
            cam.location = tgt + d.normalized() * 1.2
            cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = os.path.join(TOOLS, "work", "maritime", f"check_{label}_{view}.png")
            bpy.ops.render.render(write_still=True)


main()
