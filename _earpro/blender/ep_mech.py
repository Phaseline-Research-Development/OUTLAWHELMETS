"""Phaseline ear-pro mechanism lab (Blender, headless).

Loads an existing ear-pro worn FBX + the helmet it is worn on + the body, splits the ear-pro into rigid parts by
mesh island (no geometry is changed), poses the parts with the mount's joints and measures clearance.

  blender -b --factory-startup --python ep_mech.py -- <config.json>

config.json:
  {"earpro": "<fbx>", "helmet": ["<fbx>", ...], "out": "<dir>",
   "poses": {"name": {"L": {"splay":deg,"swing":deg,"spin":deg,"yaw":deg}, "R": {...}}, ...},
   "render": ["name", ...], "views": ["side_L","side_R","back","top","back34_L"], "classify_only": false}

Frames: Blender character model space, +X = character right, +Y = forward (face), +Z = up.
Joint model (per side, s = +1 right / -1 left):
  P   shoe pivot: midpoint of the two hinge-pin islands of the rail shoe
  splay  about the hinge-pin axis through P (positive = cup moves outward, away from the head)
  swing  about the lateral axis (+X) through P (positive = cup goes up and over towards the back)
  G   gimbal: centre of the gimbal disc island on the cup
  spin   about the gimbal axis (cup's outward normal) through G
  yaw    about the arm-frame vertical through G (folds the cup flat against the shell)
Arm = swing o splay ; Cup = Arm o (yaw o spin about G).
"""
import bpy, bmesh, sys, os, json, math
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ep_common as EC

argv = sys.argv[sys.argv.index("--") + 1:]
CFG = json.load(open(argv[0]))
OUT = CFG["out"]
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "mech_log.txt"), "w", encoding="utf-8")
sys.stdout = LOG
sys.stderr = LOG
BODY = r"C:\Users\tyler\OneDrive\Desktop\Blender\Punisherbody_skel.blend"


def log(*a):
    print(*a)
    LOG.flush()


# ------------------------------------------------------------------ load
bpy.ops.wm.open_mainfile(filepath=BODY)
body = [o for o in bpy.data.objects if o.type == 'MESH']
for o in bpy.data.objects:
    if o.type == 'ARMATURE':
        o.hide_render = True


SOLIDS = []      # closed trace / collision hulls shipped with the helmet FBX (UTM_*): used for the inside test


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    ms = []
    for o in new:
        if o.type == 'ARMATURE':
            o.hide_render = True
            o.hide_viewport = True
        elif o.type == 'MESH':
            if o.name.upper().startswith(("UCX", "UTM", "USP", "UBX")):
                o.hide_render = True
                if o.name.upper().startswith("UTM"):
                    SOLIDS.append(o)
                continue
            ms.append(o)
    return ms


helmet = []
for h in CFG["helmet"]:
    helmet += imp(h)
ear = imp(CFG["earpro"])
assert len(ear) == 1, [o.name for o in ear]
EAR = ear[0]


def baked_coords(o):
    """world-space vertex coords of the evaluated (skinned, rest pose) mesh"""
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    vs = [oe.matrix_world @ v.co for v in me.vertices]
    oe.to_mesh_clear()
    return vs


def bvh_of(objs):
    verts, polys = [], []
    for o in objs:
        dg = bpy.context.evaluated_depsgraph_get()
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        base = len(verts)
        verts += [oe.matrix_world @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        oe.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys), verts, polys


HEL_BVH, _, _ = bvh_of(helmet)
SOLID_BVH = bvh_of(SOLIDS)[0] if SOLIDS else None
# only the head/neck part of the body matters
BODY_BVH, _, _ = bvh_of(body)

# ------------------------------------------------------------------ islands
me = EAR.data
V = baked_coords(EAR)
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
comp = [-1] * len(bm.verts)
islands = []
for v in bm.verts:
    if comp[v.index] >= 0:
        continue
    cid = len(islands)
    st = [v]
    comp[v.index] = cid
    mem = []
    while st:
        x = st.pop()
        mem.append(x.index)
        for e in x.link_edges:
            y = e.other_vert(x)
            if comp[y.index] < 0:
                comp[y.index] = cid
                st.append(y)
    islands.append(mem)
bm.free()


def box(mem):
    pts = [V[i] for i in mem]
    mn = Vector([min(p[k] for p in pts) for k in range(3)])
    mx = Vector([max(p[k] for p in pts) for k in range(3)])
    return mn, mx, (mn + mx) / 2


info = []
for cid, mem in enumerate(islands):
    mn, mx, c = box(mem)
    info.append({"id": cid, "n": len(mem), "min": mn, "max": mx, "c": c})

# ------------------------------------------------------------------ classification
# Rules come from the colour-coded renders of the AMP (renders/amp_*): per side the rail SHOE sits inboard at the rear
# end of the ARC rail, the ARM runs forward from the shoe hinge to the gimbal, the CUP group is everything centred on the
# cup (shell, cushion, strap/yoke, gimbal disc, connector and cable stubs), the MIC (left cup only) runs to the mouth.
CL = CFG.get("classify", {})
SHOE_MAX_Y = CL.get("shoe_max_y", -0.0885)      # islands centred behind this (and inboard) are rail-shoe parts
SHOE_MAX_ABSX = CL.get("shoe_max_absx", 0.1095)
ARM_MIN_ABSX = CL.get("arm_min_absx", 0.1155)
part = {}
for d in info:
    c, n = d["c"], d["n"]
    s = 1 if c.x > 0 else -1
    ax = abs(c.x)
    if c.y > 0.0:
        part[d["id"]] = ("MIC", s)
    elif c.y < SHOE_MAX_Y and ax < SHOE_MAX_ABSX:
        part[d["id"]] = ("SHOE", s)
    elif c.y < -0.050 and ax > ARM_MIN_ABSX and c.z > 1.645:
        part[d["id"]] = ("ARM", s)
    elif c.y < SHOE_MAX_Y:
        part[d["id"]] = ("SHOE", s)
    else:
        part[d["id"]] = ("CUP", s)
# hinge pins of the shoe: the pair of equal islands stacked on the shoe/arm joint (AMP: 99 verts each)
PIN_N = CL.get("pin_verts", [95, 105])
for d in info:
    if PIN_N[0] <= d["n"] <= PIN_N[1] and d["c"].y < SHOE_MAX_Y + 0.002:
        part[d["id"]] = ("SHOE", 1 if d["c"].x > 0 else -1)
for k, v in CL.get("force", {}).items():
    part[int(k)] = (v[0], v[1])

# pivots per side
piv = {}
if CL.get("mount") == "comtac":
    _, part, piv_c, _ = EC.classify_comtac(V, islands, CL, log)
    for s in (1, -1):
        piv_c[s].setdefault("cup_id", piv_c[s]["arm_id"])
    piv = piv_c
for s in ((1, -1) if not piv else ()):
    shoe_pins = [d for d in info if part[d["id"]] == ("SHOE", s) and 90 <= d["n"] <= 110]
    arm_body = max((d for d in info if part[d["id"]] == ("ARM", s)), key=lambda d: d["n"])
    cup_shell = max((d for d in info if part[d["id"]] == ("CUP", s)), key=lambda d: d["n"])
    # gimbal disc = cup-group island furthest outboard near the cup's centre height
    gim = [d for d in info if part[d["id"]] == ("CUP", s) and abs(d["c"].z - cup_shell["c"].z) < 0.01
           and abs(d["c"].y - cup_shell["c"].y) < 0.01 and 40 <= d["n"] <= 200]
    gim = max(gim, key=lambda d: abs(d["c"].x)) if gim else cup_shell
    if len(shoe_pins) >= 2:
        shoe_pins.sort(key=lambda d: d["c"].z)
        a, b = shoe_pins[0]["c"], shoe_pins[-1]["c"]
        P = (a + b) / 2
        hinge = (b - a).normalized()
    else:
        P = Vector(CFG.get("pivot_" + ("R" if s > 0 else "L")))
        hinge = Vector((0, 0, 1))
    G = gim["c"].copy()
    piv[s] = {"P": P, "hinge": hinge, "G": G, "cup_c": cup_shell["c"].copy(), "arm_id": arm_body["id"],
              "cup_id": cup_shell["id"], "gim_id": gim["id"]}
    log(f"side {s:+d}: P {tuple(round(x, 4) for x in P)} hinge {tuple(round(x, 3) for x in hinge)} "
        f"G {tuple(round(x, 4) for x in G)} cup centre {tuple(round(x, 4) for x in cup_shell['c'])}")

summary = {}
for d in info:
    p = part[d["id"]]
    summary.setdefault(f"{p[0]}_{'R' if p[1] > 0 else 'L'}", []).append(d["id"])
log("parts:", json.dumps({k: sorted(v) for k, v in summary.items()}))

# vertex -> (part, side)
vpart = [part[comp[i]] for i in range(len(V))]


# ------------------------------------------------------------------ kinematics
def rot_about(point, axis, deg):
    return Matrix.Translation(point) @ Matrix.Rotation(math.radians(deg), 4, axis.normalized()) @ Matrix.Translation(-point)


def side_mats(s, p):
    """p: dict splay/swing/spin/yaw (deg). returns (arm_matrix, cup_matrix) in model space."""
    pv = piv[s]
    P, G = pv["P"], pv["G"]
    # splay: positive moves the cup away from the head -> sign by side (hinge axis points up; cup is forward of P)
    hinge = pv["hinge"]
    splay = rot_about(P, hinge, -s * p.get("splay", 0.0))
    swing = rot_about(P, Vector((1, 0, 0)), p.get("swing", 0.0))
    arm = swing @ splay
    # gimbal frame at rest: spin about the outward normal (s*X), yaw about vertical (Z), both through G
    spin = rot_about(G, Vector((s, 0, 0)), p.get("spin", 0.0))
    yaw = rot_about(G, Vector((0, 0, 1)), s * p.get("yaw", 0.0))
    cup = arm @ yaw @ spin
    return arm, cup


def posed_verts(pose):
    mats = {}
    for s in (1, -1):
        key = "R" if s > 0 else "L"
        mats[s] = side_mats(s, pose.get(key, {}))
    out = []
    for i, v in enumerate(V):
        kind, s = vpart[i]
        if kind == "SHOE":
            out.append(v.copy())
        elif kind == "ARM":
            out.append(mats[s][0] @ v)
        else:  # CUP, MIC (mic rides on its cup)
            out.append(mats[s][1] @ v)
    return out, mats


CUSH = {}
for s in (1, -1):
    # cushion = cup-group island with the most inboard centre (largest |x| decrease), big
    if "cushion_island" in piv[s]:
        CUSH[s] = piv[s]["cushion_island"]
        continue
    cand = [d for d in info if part[d["id"]] == ("CUP", s) and d["n"] > 300]
    CUSH[s] = min(cand, key=lambda d: abs(d["c"].x))["id"]


def clearance(pose, sample_every=3):
    pv, mats = posed_verts(pose)
    res = {}
    for s in (1, -1):
        key = "R" if s > 0 else "L"
        mov = [i for i in range(len(V)) if vpart[i][1] == s and vpart[i][0] != "SHOE"]
        hmin, bmin = 9.0, 9.0
        hcount, bcount = 0, 0
        for i in mov[::sample_every]:
            p = pv[i]
            loc, nrm, idx, dist = HEL_BVH.find_nearest(p, 0.2)
            if loc is not None:
                inside = (p - loc).dot(nrm) < 0
                dd = -dist if inside else dist
                if dd < hmin:
                    hmin = dd
                if dd < 0:
                    hcount += 1
            loc, nrm, idx, dist = BODY_BVH.find_nearest(p, 0.2)
            if loc is not None:
                inside = (p - loc).dot(nrm) < 0
                dd = -dist if inside else dist
                if dd < bmin:
                    bmin = dd
                if dd < 0:
                    bcount += 1
        # cushion to head gap (vent check)
        cus = [pv[i] for i in islands[CUSH[s]]][::2]
        gap = min((BODY_BVH.find_nearest(p, 0.3)[3] or 9) for p in cus)
        cup_c = mats[s][1] @ piv[s]["cup_c"]
        res[key] = {"helmet_min_mm": round(hmin * 1000, 1), "helmet_pen_verts": hcount,
                    "body_min_mm": round(bmin * 1000, 1), "body_pen_verts": bcount,
                    "cushion_gap_mm": round(gap * 1000, 1), "cup_centre": [round(x, 4) for x in cup_c]}
    return res, pv


# ------------------------------------------------------------------ stowed-pose search
RAY_DIRS = [Vector((0.267, 0.534, 0.802)).normalized(), Vector((-0.71, 0.31, -0.63)).normalized(),
            Vector((0.12, -0.93, 0.35)).normalized()]


def inside_helmet(q):
    """ray-parity inside test against the CLOSED shell hull (UTM_*), majority of 3 directions"""
    if SOLID_BVH is None:
        return False
    votes = 0
    for d in RAY_DIRS:
        o = q.copy()
        hits = 0
        for _ in range(16):
            loc, nrm, idx, dist = SOLID_BVH.ray_cast(o, d, 0.6)
            if loc is None:
                break
            hits += 1
            o = loc + d * 1e-5
        votes += hits % 2
    return votes >= 2


# vertices that already touch / sit inside the helmet in the authored (deployed) pose are part of the asset as it
# is fitted today (strap tabs against the rail etc.); they are excluded from the clearance test.
BASE_TOUCH = set()
DEBUG_PEN = [] if CFG.get("debug_pen") else None


def side_metrics(s, p, sample_every=4):
    """penetration / proximity of one side's moving parts against the helmet (+ extra accessories)."""
    arm_m, cup_m = side_mats(s, p)
    P = piv[s]["P"]
    hmin = 9.0
    pen = 0
    for i in MOV[s][::sample_every]:
        if i in BASE_TOUCH:
            continue
        kind = vpart[i][0]
        v = V[i]
        if kind == "ARM" and (v - P).length < CFG.get("hub_exclude", 0.028):
            continue                       # the arm knuckle lives in the rail slot by design
        q = (arm_m if kind == "ARM" else cup_m) @ v
        loc, nrm, idx, dist = HEL_BVH.find_nearest(q, 0.25)
        dd = dist if loc is not None else 0.25
        if SOLID_BVH is not None:
            sl, sn, si, sd = SOLID_BVH.find_nearest(q, 0.25)
            if sl is not None and sd < 0.05 and inside_helmet(q):
                dd = -sd
        hmin = min(hmin, dd)
        if dd < 0.0015:
            pen += 1
            if DEBUG_PEN is not None and len(DEBUG_PEN) < 400:
                DEBUG_PEN.append((s, kind, round((v - P).length * 1000), [round(x, 4) for x in v], round(dd * 1000, 1)))
    # cushion face proximity to the helmet (how flat the cup lies on the shell)
    cus = [cup_m @ V[i] for i in islands[CUSH[s]][::6]]
    d = sorted((HEL_BVH.find_nearest(q, 0.3)[3] or 0.3) for q in cus)
    near = d[len(d) // 4]                  # 25th percentile cushion-to-shell distance
    cc = cup_m @ piv[s]["cup_c"]
    bmin = 9.0
    for q in cus[::2]:
        loc, nrm, idx, dist = BODY_BVH.find_nearest(q, 0.25)
        if loc is not None:
            bmin = min(bmin, dist)
    return {"pen": pen, "hmin": hmin, "near": near, "cc": cc, "body": bmin}


def search_stow(s, cfg):
    best = None
    rng = cfg.get("ranges", {"splay": [10, 50, 5], "swing": [110, 190, 5], "spin": [-90, 90, 15], "yaw": [-45, 45, 15]})

    def frange(a):
        x, out = a[0], []
        while x <= a[1] + 1e-6:
            out.append(x)
            x += a[2]
        return out
    tgt_y = cfg.get("target_back_y", -0.13)
    n = 0
    for sp in frange(rng["splay"]):
        for sw in frange(rng["swing"]):
            for yw in frange(rng["yaw"]):
                for sn in frange(rng["spin"]):
                    p = {"splay": sp, "swing": sw, "spin": sn, "yaw": yw}
                    m = side_metrics(s, p, sample_every=7)
                    n += 1
                    if m["pen"] > 0:
                        continue
                    # lie close to the shell (cushion), sit at the back, keep low profile, prefer small splay
                    score = (abs(m["near"] - 0.004) * 400 + max(0.0, m["cc"].y - tgt_y) * 60
                             + abs(m["cc"].x) * 20 + sp * 0.01)
                    if best is None or score < best[0]:
                        best = (score, p, m)
    log(f"stow search side {s:+d}: {n} poses tried, best {best[1] if best else None} "
        f"{({k: (round(v, 4) if isinstance(v, float) else [round(x, 4) for x in v] if isinstance(v, Vector) else v) for k, v in best[2].items()} if best else '')}")
    if not best:
        return None
    # refine around the best (fine steps, full sampling)
    b = best[1]
    best2 = None
    for sp in [b["splay"] + d for d in (-4, -2, 0, 2, 4)]:
        for sw in [b["swing"] + d for d in (-4, -2, 0, 2, 4)]:
            for yw in [b["yaw"] + d for d in (-8, -4, 0, 4, 8)]:
                for sn in [b["spin"] + d for d in (-8, -4, 0, 4, 8)]:
                    p = {"splay": sp, "swing": sw, "spin": sn, "yaw": yw}
                    m = side_metrics(s, p, sample_every=2)
                    if m["pen"] > 0 or m["hmin"] < 0.002:
                        continue
                    score = (abs(m["near"] - 0.004) * 400 + max(0.0, m["cc"].y - tgt_y) * 60
                             + abs(m["cc"].x) * 20 + sp * 0.01)
                    if best2 is None or score < best2[0]:
                        best2 = (score, p, m)
    res = best2 or best
    log(f"   refined: {res[1]} hmin {res[2]['hmin']*1000:.1f} mm near {res[2]['near']*1000:.1f} mm cup centre "
        f"{tuple(round(x, 4) for x in res[2]['cc'])}")
    return res[1]


MOV = {s: [i for i in range(len(V)) if vpart[i][1] == s and vpart[i][0] != "SHOE"] for s in (1, -1)}
for s in (1, -1):
    for i in MOV[s]:
        loc, nrm, idx, dist = HEL_BVH.find_nearest(V[i], 0.25)
        if loc is not None and (dist < 0.0015 or inside_helmet(V[i])):
            BASE_TOUCH.add(i)
log(f"verts touching the helmet in the authored pose (excluded): {len(BASE_TOUCH)}")


# ------------------------------------------------------------------ render helpers
def make_view_mesh(pv, name):
    m = EAR.data.copy()
    m.name = name
    for i, v in enumerate(m.vertices):
        v.co = pv[i]
    o = bpy.data.objects.new(name, m)
    bpy.context.scene.collection.objects.link(o)
    return o


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'OBJECT'
    sc.render.resolution_x = CFG.get("res", [1000, 900])[0]
    sc.render.resolution_y = CFG.get("res", [1000, 900])[1]
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = 'ORTHO'
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam, cam_data


VIEWS = {
    "side_L": (Vector((-1.5, 0, 0)), 0.36),
    "side_R": (Vector((1.5, 0, 0)), 0.36),
    "back": (Vector((0, -1.5, 0.15)), 0.36),
    "front": (Vector((0, 1.5, 0.0)), 0.36),
    "top": (Vector((0, -0.0001, 1.5)), 0.36),
    "back34_L": (Vector((-1.05, -1.05, 0.45)), 0.36),
    "back34_R": (Vector((1.05, -1.05, 0.45)), 0.36),
    "front34_L": (Vector((-1.05, 1.05, 0.3)), 0.36),
}

# ------------------------------------------------------------------ main
for o in body:
    o.color = (0.78, 0.66, 0.58, 1)
for o in helmet:
    o.color = (0.52, 0.52, 0.48, 1)
EAR.hide_render = True
COLS = {"SHOE": (0.85, 0.2, 0.55, 1), "ARM": (0.75, 0.85, 0.2, 1), "CUP": (0.2, 0.45, 0.9, 1), "MIC": (0.6, 0.2, 0.85, 1)}

def search_stow_sym(cfg):
    """same joint values on both sides (mirror), scored on the worse side; targets from Tyler's reference photos."""
    rng = cfg["ranges"]
    zt, yt = cfg.get("target_z", 1.725), cfg.get("target_back_y", -0.125)

    def frange(a):
        x, out = a[0], []
        while x <= a[1] + 1e-6:
            out.append(x)
            x += a[2]
        return out

    def score_of(p, every):
        tot, worst = 0.0, None
        for s in (1, -1):
            m = side_metrics(s, p, sample_every=every)
            if m["pen"] > 0:
                return None, None
            sc = (abs(m["near"] - 0.004) * 400 + abs(m["cc"].z - zt) * 50 + max(0.0, m["cc"].y - yt) * 50
                  + max(0.0, abs(m["cc"].x) - 0.115) * 30)
            if worst is None or sc > worst[0]:
                worst = (sc, m)
        return worst[0] + p["splay"] * 0.004, worst[1]

    best = None
    for sp in frange(rng["splay"]):
        for sw in frange(rng["swing"]):
            for yw in frange(rng["yaw"]):
                for sn in frange(rng["spin"]):
                    p = {"splay": sp, "swing": sw, "spin": sn, "yaw": yw}
                    sc, m = score_of(p, 7)
                    if sc is not None and (best is None or sc < best[0]):
                        best = (sc, p, m)
    if not best:
        log("symmetric stow search: nothing collision-free")
        return None
    b = best[1]
    best2 = best
    for it in range(2):
        step = (3, 2) if it == 0 else (1.5, 1)
        cen = best2[1]
        for sp in [cen["splay"] + d * step[1] for d in (-2, -1, 0, 1, 2)]:
            for sw in [cen["swing"] + d * step[0] for d in (-2, -1, 0, 1, 2)]:
                for yw in [cen["yaw"] + d * step[0] for d in (-2, -1, 0, 1, 2)]:
                    for sn in [cen["spin"] + d * step[0] for d in (-2, -1, 0, 1, 2)]:
                        p = {"splay": sp, "swing": sw, "spin": sn, "yaw": yw}
                        sc, m = score_of(p, 2)
                        if sc is not None and m["hmin"] >= 0.002 and sc < best2[0]:
                            best2 = (sc, p, m)
    p, m = best2[1], best2[2]
    log(f"symmetric stow: {p} score {best2[0]:.3f} near {m['near']*1000:.1f} mm hmin {m['hmin']*1000:.1f} mm "
        f"cup centre {tuple(round(x, 4) for x in m['cc'])}")
    return p


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def key_value(keys, t):
    """keys = [[t, v], ...] sorted; smoothstep between neighbours, clamped at the ends"""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ease((t - t0) / max(1e-6, t1 - t0))
    return keys[-1][1]


def path_pose(frm, to, sched, t):
    """channel-wise eased interpolation. sched[ch] = [t0, t1] (frm -> to) or a key list [[t, v], ...]"""
    p = {}
    for ch in ("splay", "swing", "spin", "yaw"):
        sc = sched.get(ch, [0.0, 1.0])
        if sc and isinstance(sc[0], list):
            p[ch] = key_value(sc, t)
            continue
        a, b = frm.get(ch, 0.0), to.get(ch, 0.0)
        t0, t1 = sc
        u = ease((t - t0) / max(1e-6, (t1 - t0)))
        p[ch] = a + (b - a) * u
    return p


def check_path(name, spec, steps=40):
    worst = (9.0, None)
    rows = []
    for k in range(steps + 1):
        t = k / steps
        p = path_pose(spec["from"], spec["to"], spec["sched"], t)
        row = {"t": round(t, 3)}
        for s in (1, -1):
            m = side_metrics(s, p, sample_every=3)
            row["R" if s > 0 else "L"] = round(m["hmin"] * 1000, 1)
            row["pen" + ("R" if s > 0 else "L")] = m["pen"]
            row["body" + ("R" if s > 0 else "L")] = round(m["body"] * 1000, 1)
            if m["hmin"] < worst[0]:
                worst = (m["hmin"], (t, s, p))
        rows.append(row)
    log(f"path {name}: worst helmet clearance {worst[0]*1000:.1f} mm at {worst[1]}")
    for r in rows:
        if r["penL"] or r["penR"]:
            log("   PEN", r)
    json.dump(rows, open(os.path.join(OUT, f"path_{name}.json"), "w"), indent=0)
    return rows


def vent_table(cfg):
    for sp in cfg.get("splays", [6, 8, 10, 12, 14, 16, 18, 20]):
        for sw in cfg.get("swings", [0]):
            p = {"splay": sp, "swing": sw}
            line = f"vent splay {sp:4.1f} swing {sw:4.1f}:"
            for s in (-1, 1):
                _, cup_m = side_mats(s, p)
                cus = [cup_m @ V[i] for i in islands[CUSH[s]][::3]]
                g = sorted((BODY_BVH.find_nearest(q, 0.3)[3] or 0.3) for q in cus)
                m = side_metrics(s, p, sample_every=3)
                line += (f"  {'R' if s > 0 else 'L'} cushion gap min {g[0]*1000:5.1f} p25 {g[len(g)//4]*1000:5.1f} "
                         f"mean {sum(g)/len(g)*1000:5.1f} mm, helmet min {m['hmin']*1000:5.1f} pen {m['pen']}")
            log(line)


results = {}
if CFG.get("debug_pen"):
    for nm, p in CFG["debug_pen"].items():
        DEBUG_PEN.clear()
        for s_ in (1, -1):
            side_metrics(s_, p, sample_every=1)
        log(f"debug_pen {nm}: {len(DEBUG_PEN)} verts; dist-from-hub histogram (mm):",
            sorted(set(d[2] // 5 * 5 for d in DEBUG_PEN)))
        for d in DEBUG_PEN[:12]:
            log("   ", d)
if CFG.get("vent_table"):
    vent_table(CFG["vent_table"])
for nm, spec in CFG.get("paths", {}).items():
    rows = check_path(nm, spec)
    for t in spec.get("render_t", []):
        nm2 = f"{nm}_t{int(t*100):03d}"
        p = path_pose(spec["from"], spec["to"], spec["sched"], t)
        CFG.setdefault("poses", {})[nm2] = {"L": p, "R": p}
        CFG.setdefault("render", []).append(nm2)
if CFG.get("search_stow_sym"):
    p = search_stow_sym(CFG["search_stow_sym"])
    if p:
        CFG.setdefault("poses", {})["stow_sym"] = {"L": p, "R": p}
        CFG.setdefault("render", []).append("stow_sym")
        json.dump(p, open(os.path.join(OUT, "stow_sym.json"), "w"), indent=1)
if CFG.get("search_stow"):
    found = {}
    for s in (-1, 1):
        r = search_stow(s, CFG["search_stow"])
        if r:
            found["R" if s > 0 else "L"] = r
    CFG.setdefault("poses", {})["stow_found"] = found
    CFG.setdefault("render", []).append("stow_found")
    json.dump(found, open(os.path.join(OUT, "stow_found.json"), "w"), indent=1)
sc, cam, cam_data = setup_render()
C = Vector(CFG.get("centre", (0, -0.01, 1.69)))
for pname, pose in CFG.get("poses", {"rest": {}}).items():
    res, pv = clearance(pose)
    results[pname] = res
    log(pname, json.dumps(res))
    if pname not in CFG.get("render", []):
        continue
    # one object per part kind so colours separate
    objs = []
    for kind in COLS:
        idx = [i for i in range(len(V)) if vpart[i][0] == kind]
        if not idx:
            continue
        bm2 = bmesh.new()
        src = EAR.data
        bm2.from_mesh(src)
        bm2.verts.ensure_lookup_table()
        keep = set(idx)
        for v in bm2.verts:
            v.co = pv[v.index]
        kill = [v for v in bm2.verts if v.index not in keep]
        bmesh.ops.delete(bm2, geom=kill, context='VERTS')
        m = bpy.data.meshes.new(f"{pname}_{kind}")
        bm2.to_mesh(m)
        bm2.free()
        o = bpy.data.objects.new(m.name, m)
        o.color = COLS[kind] if CFG.get("part_colours", True) else (0.72, 0.62, 0.45, 1)
        sc.collection.objects.link(o)
        objs.append(o)
    for vname in CFG.get("views", ["side_L", "back"]):
        off, scale = VIEWS[vname]
        cam.location = C + off
        cam.rotation_euler = (C - cam.location).to_track_quat('-Z', 'Y').to_euler()
        cam_data.ortho_scale = scale
        sc.render.filepath = os.path.join(OUT, f"{pname}__{vname}.png")
        bpy.ops.render.render(write_still=True)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)

json.dump({"pivots": {("R" if s > 0 else "L"): {k: (list(v) if isinstance(v, Vector) else v) for k, v in pv.items()}
                      for s, pv in piv.items()},
           "parts": {k: sorted(v) for k, v in summary.items()}, "results": results},
          open(os.path.join(OUT, "mech_result.json"), "w"), indent=1)
log("DONE")
LOG.close()
