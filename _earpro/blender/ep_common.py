"""Shared helpers for the Phaseline ear-pro tools (Blender side).

Frames
  Blender character model space: +X = character right, +Y = forward (face), +Z = up (bind pose).
  Head pivot (Enfusion PivotID "Head"): Blender matrix = Rz(180 deg) at HEAD_T. Verified 2026-11-06 with the SF V2 NVG
  slot offset (lands on the shroud). Head-local Blender coords: v_local = Rz180 @ (v - HEAD_T).
"""
import bmesh, math
from mathutils import Matrix, Vector

HEAD_T = Vector((0.0, -0.03199, 1.61842))
HEAD_M = Matrix.Translation(HEAD_T) @ Matrix.Rotation(math.pi, 4, 'Z')
HEAD_INV = HEAD_M.inverted()

# AMP-style classification defaults (from the colour-coded renders of OpsCore_AMP, 2026-11-06)
DEFAULT_CLASSIFY = {"shoe_max_y": -0.0885, "shoe_max_absx": 0.1095, "arm_min_absx": 0.1155, "pin_verts": [95, 105]}


def evaluated_coords(obj, depsgraph):
    oe = obj.evaluated_get(depsgraph)
    me = oe.to_mesh()
    vs = [oe.matrix_world @ v.co for v in me.vertices]
    oe.to_mesh_clear()
    return vs


def islands_of(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    comp = [-1] * len(bm.verts)
    out = []
    for v in bm.verts:
        if comp[v.index] >= 0:
            continue
        cid = len(out)
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
        out.append(mem)
    bm.free()
    return out, comp


def classify(V, islands, cl=None, log=print):
    """returns info list, part dict island->(kind, side), pivots per side, vertex->(kind, side)"""
    if (cl or {}).get("mount") == "comtac":
        return classify_comtac(V, islands, cl, log)
    cl = dict(DEFAULT_CLASSIFY, **(cl or {}))
    info = []
    for cid, mem in enumerate(islands):
        pts = [V[i] for i in mem]
        mn = Vector([min(p[k] for p in pts) for k in range(3)])
        mx = Vector([max(p[k] for p in pts) for k in range(3)])
        info.append({"id": cid, "n": len(mem), "min": mn, "max": mx, "c": (mn + mx) / 2})
    part = {}
    for d in info:
        c = d["c"]
        s = 1 if c.x > 0 else -1
        ax = abs(c.x)
        if c.y > 0.0:
            part[d["id"]] = ("MIC", s)
        elif c.y < cl["shoe_max_y"] and ax < cl["shoe_max_absx"]:
            part[d["id"]] = ("SHOE", s)
        elif c.y < -0.050 and ax > cl["arm_min_absx"] and c.z > 1.645:
            part[d["id"]] = ("ARM", s)
        elif c.y < cl["shoe_max_y"]:
            part[d["id"]] = ("SHOE", s)
        else:
            part[d["id"]] = ("CUP", s)
    for d in info:
        if cl["pin_verts"][0] <= d["n"] <= cl["pin_verts"][1] and d["c"].y < cl["shoe_max_y"] + 0.002:
            part[d["id"]] = ("SHOE", 1 if d["c"].x > 0 else -1)
    for k, v in cl.get("force", {}).items():
        part[int(k)] = (v[0], v[1])
    piv = {}
    for s in (1, -1):
        pins = sorted((d for d in info if part[d["id"]] == ("SHOE", s) and cl["pin_verts"][0] <= d["n"] <= cl["pin_verts"][1]),
                      key=lambda d: d["c"].z)
        cup_shell = max((d for d in info if part[d["id"]] == ("CUP", s)), key=lambda d: d["n"])
        gim = [d for d in info if part[d["id"]] == ("CUP", s) and abs(d["c"].z - cup_shell["c"].z) < 0.01
               and abs(d["c"].y - cup_shell["c"].y) < 0.01 and 40 <= d["n"] <= 200]
        gim = max(gim, key=lambda d: abs(d["c"].x)) if gim else cup_shell
        a, b = pins[0]["c"], pins[-1]["c"]
        cush = min((d for d in info if part[d["id"]] == ("CUP", s) and d["n"] > 300), key=lambda d: abs(d["c"].x))
        piv[s] = {"P": (a + b) / 2, "hinge": (b - a).normalized(), "G": gim["c"].copy(), "cup_c": cup_shell["c"].copy(),
                  "cushion_island": cush["id"]}
        log(f"side {s:+d}: P {tuple(round(x, 4) for x in piv[s]['P'])} hinge {tuple(round(x, 3) for x in piv[s]['hinge'])} "
            f"G {tuple(round(x, 4) for x in piv[s]['G'])}")
    comp_part = [None] * len(V)
    for cid, mem in enumerate(islands):
        for i in mem:
            comp_part[i] = part[cid]
    return info, part, piv, comp_part


BONES = {("ARM", -1): "EP_Arm_L", ("ARM", 1): "EP_Arm_R", ("CUP", -1): "EP_Cup_L", ("CUP", 1): "EP_Cup_R",
         ("MIC", -1): "EP_Cup_L", ("MIC", 1): "EP_Cup_R"}


# ------------------------------------------------------------------ 3M Peltor ComTac on the ARC rail adapter
# From the colour-coded renders (build/comtac, 2026-11-06): per side the ARC ADAPTER sits on the rail at the top
# (z ~1.747, fixed = "SHOE"); a wire stirrup runs from the adapter hub down to the front and back of the cup; the cup,
# its stirrup, the mic (left) and cable stubs move rigidly together about the adapter hub.
#   splay: about the fore-aft axis through the hub (3M "pull the earcups up and outwards" = ventilation position)
#   swing: about the lateral axis through the hub; NEGATIVE = cup goes back and up (rear fold, Tyler's photo 184811)
COMTAC_CLASSIFY = {"adapter_band": 0.012, "hinge": [0.0, 1.0, 0.0]}


def classify_comtac(V, islands, cl=None, log=print):
    cl = dict(COMTAC_CLASSIFY, **(cl or {}))
    info = []
    for cid, mem in enumerate(islands):
        pts = [V[i] for i in mem]
        mn = Vector([min(p[k] for p in pts) for k in range(3)])
        mx = Vector([max(p[k] for p in pts) for k in range(3)])
        info.append({"id": cid, "n": len(mem), "min": mn, "max": mx, "c": (mn + mx) / 2})
    # the adapters are the top-most real islands of the model (relative, so XP / Maritime placements work too)
    top_z = max(d["c"].z for d in info if d["n"] > 20)
    zmin = cl.get("adapter_min_z", top_z - cl["adapter_band"])
    part = {}
    for d in info:
        s = 1 if d["c"].x > 0 else -1
        if d["c"].z >= zmin and d["n"] > 2:
            part[d["id"]] = ("SHOE", s)
        elif d["c"].y > 0.045 and s < 0:
            part[d["id"]] = ("MIC", s)
        else:
            part[d["id"]] = ("ARM", s)
    for k, v in cl.get("force", {}).items():
        part[int(k)] = (v[0], v[1])
    piv = {}
    for s in (1, -1):
        adapter = max((d for d in info if part[d["id"]] == ("SHOE", s)), key=lambda d: d["n"])
        cup = max((d for d in info if part[d["id"]] == ("ARM", s)), key=lambda d: d["n"])
        P = adapter["c"].copy()
        hinge = Vector(cl["hinge"]).normalized()
        piv[s] = {"P": P, "hinge": hinge, "G": P.copy(), "cup_c": cup["c"].copy(), "cushion_island": cup["id"],
                  "arm_id": cup["id"], "cup_id": cup["id"], "gim_id": cup["id"], "adapter_id": adapter["id"]}
        log(f"comtac side {s:+d}: hub P {tuple(round(x, 4) for x in P)} cup centre {tuple(round(x, 4) for x in cup['c'])} "
            f"cup outer x {round(cup['max'].x if s > 0 else cup['min'].x, 4)}")
    comp_part = [None] * len(V)
    for cid, mem in enumerate(islands):
        for i in mem:
            comp_part[i] = part[cid]
    return info, part, piv, comp_part
