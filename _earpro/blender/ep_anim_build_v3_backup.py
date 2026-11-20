"""Phaseline ear-pro character clips (hand reach / grab / manipulate / release / return), Blender headless.

  blender -b <Character_AnimationRig_Example.blend> --python ep_anim_build.py -- <config.json>

The SAME mechanism model and channel keys drive (1) the hand targets here and (2) the in-game cup bones (timeline JSON
-> Enforce config), so the hand stays on the cup grip point for the whole manipulation by construction.

Frames: BI rig (this blend): character faces -Y, +X = character LEFT, Z up. Ear-pro data (rig report / ep_mech) are in
the Punisherbody frame (faces +Y, +X right) = rig frame rotated 180 deg about Z  ->  rig = (-x, -y, z).
Arm chain (BI skeleton): Shoulder -> Arm -> ArmTwist -> ForeArm -> ForeArmTwist -> Hand.
TXA convention (write_crrc_txa.py, verified vs EBT): key = pose matrix relative to parent bone, t (x, z, y),
q (-x, -z, -y, w).
"""
import bpy, sys, os, json, math
from mathutils import Matrix, Vector, Quaternion

argv = sys.argv[sys.argv.index("--") + 1:]
CFG = json.load(open(argv[0]))
OUT = CFG["out_dir"]
os.makedirs(OUT, exist_ok=True)
LOGF = open(os.path.join(OUT, "anim_build_log.txt"), "w", encoding="utf-8")
sys.stdout = LOGF
sys.stderr = LOGF
FPS = 30


def log(*a):
    print(*a)
    LOGF.flush()


ARM = bpy.data.objects["Character"]
for pb in ARM.pose.bones:                       # drive the deform skeleton directly (the control rig is ignored)
    for c in list(pb.constraints):
        pb.constraints.remove(c)
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()

S4 = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
BASE = CFG.get("base_pose_enf", {})          # bone -> {"t": [...], "x": [...], "y": [...], "z": [...]} (engine local)
BASE_ORDER = [b for b in ("Spine1", "Spine2", "Spine3", "Spine4", "Spine5", "Neck1", "Neck2", "Neck3", "Head") if b in BASE]


def apply_base_pose():
    """reset to rest, then set the spine/neck/head chain to the in-game stance (engine local -> Blender local)"""
    for b in ARM.pose.bones:
        b.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for name in BASE_ORDER:
        e = BASE[name]
        Le = Matrix.Identity(4)
        for i, ax in enumerate(("x", "y", "z")):
            for r in range(3):
                Le[r][i] = e[ax][r]
        for r in range(3):
            Le[r][3] = e["t"][r]
        Lb = S4 @ Le @ S4
        pbn = ARM.pose.bones[name]
        pbn.matrix = pbn.parent.matrix @ Lb
        bpy.context.view_layer.update()


apply_base_pose()
# everything head-borne (helmet, ear-pro, grip targets) follows the posed Head bone
HEAD_DELTA = (ARM.matrix_world @ ARM.pose.bones["Head"].matrix) @ (ARM.matrix_world @ ARM.data.bones["Head"].matrix_local).inverted()

REP = json.load(open(CFG["rig_report"]))
PIV = REP["pivots_model_space"]


def pb2rig(v):
    return Vector((-v[0], -v[1], v[2]))


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def key_value(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ease((t - t0) / max(1e-6, t1 - t0))
    return keys[-1][1]


# ------------------------------------------------------------------ mechanism (rig frame)
SIDES = {"L": -1, "R": 1}         # s in the Punisherbody convention (-1 = character left)


def rot_about(point, axis, deg):
    return Matrix.Translation(point) @ Matrix.Rotation(math.radians(deg), 4, axis.normalized()) @ Matrix.Translation(-point)


PB2RIG = Matrix(((-1, 0, 0, 0), (0, -1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))


def side_mats_pb(side, ch):
    """(arm, cup) motion matrices in the Punisherbody frame for joint values ch (same model as ep_mech / the game)"""
    s = SIDES[side]
    p = PIV[side]
    P, G, hinge = Vector(p["P"]), Vector(p["G"]), Vector(p["hinge"])
    splay = rot_about(P, hinge, -s * ch.get("splay", 0.0))
    swing = rot_about(P, Vector((1, 0, 0)), ch.get("swing", 0.0))
    arm = swing @ splay
    spin = rot_about(G, Vector((s, 0, 0)), ch.get("spin", 0.0))
    yaw = rot_about(G, Vector((0, 0, 1)), s * ch.get("yaw", 0.0))
    return arm, arm @ yaw @ spin


def cup_matrix(side, ch):
    """cup motion mapped to the rig frame"""
    return PB2RIG @ side_mats_pb(side, ch)[1] @ PB2RIG.inverted()


def channels_at(spec, side, t):
    ch = {}
    for name in ("splay", "swing", "spin", "yaw"):
        k = spec["cup_keys"][side].get(name)
        ch[name] = key_value(k, t) if k else 0.0
    return ch


# ------------------------------------------------------------------ skeleton helpers
def bone(n):
    return ARM.pose.bones[n]


def rest_mat(n):
    return ARM.matrix_world @ ARM.data.bones[n].matrix_local


def head_rest(n):
    return ARM.matrix_world @ ARM.data.bones[n].head_local


def align2(a1, b1, a2, b2):
    """rotation taking direction a1 -> a2 and (the part of b1 perpendicular to a1) -> (part of b2 perpendicular to a2)"""
    def basis(a, b):
        x = a.normalized()
        y = (b - x * b.dot(x)).normalized()
        z = x.cross(y)
        m = Matrix.Identity(3)
        m.col[0], m.col[1], m.col[2] = x, y, z
        return m
    return basis(a2, b2) @ basis(a1, b1).transposed()


def frame_from(y_axis, ref_x, rest_m):
    """rotation with bone y = y_axis, x as close as possible to ref_x"""
    y = y_axis.normalized()
    x = (ref_x - y * ref_x.dot(y)).normalized()
    z = x.cross(y)
    m = Matrix.Identity(3)
    m.col[0], m.col[1], m.col[2] = x, y, z
    return m


SIDE_BONES = {s: {k: (("Left" if s == "L" else "Right") + k) for k in
                  ("Shoulder", "Arm", "ArmTwist", "ForeArm", "ForeArmTwist", "Hand", "HandMiddle1", "HandThumb1",
                   "HandIndex1", "HandRing1")} for s in ("L", "R")}


class ArmModel:
    def __init__(self, side):
        b = SIDE_BONES[side]
        self.side = side
        self.sgn = 1 if side == "L" else -1          # rig: +X = left
        self.b = b
        S, E, W = head_rest(b["Arm"]), head_rest(b["ForeArm"]), head_rest(b["Hand"])
        self.la, self.lb = (E - S).length, (W - E).length
        # rest limb directions + hinge (arm plane) normal, armature space
        self.dir_up_rest = (E - S).normalized()
        self.dir_fore_rest = (W - E).normalized()
        self.pn_rest = (E - S).cross(W - E).normalized()
        # hand: fingers direction, thumb direction, palm normal at rest (armature space)
        Hm = rest_mat(b["Hand"]).to_3x3()
        F = (head_rest(b["HandMiddle1"]) - W).normalized()
        T = (head_rest(b["HandThumb1"]) - head_rest(b["HandRing1"])).normalized()
        N = F.cross(T).normalized() if side == "L" else T.cross(F).normalized()   # palm normal (palm side)
        T = N.cross(F).normalized() if side == "L" else F.cross(N).normalized()
        self.hand_rest_basis = Matrix((F, N, T)).transposed()                  # columns F, N, T
        self.hand_rest_rot = Hm
        # BI skeleton: HandMiddle1 is the metacarpal (2.9 cm from the wrist); the knuckle is HandMiddle2.
        knuckle = head_rest(("Left" if side == "L" else "Right") + "HandMiddle2")
        palm = (W + knuckle) * 0.5 + N * CFG.get("palm_skin", 0.013)
        self.palm_off_rest = palm - W                                          # wrist -> palm centre
        log(f"arm {side}: upper {self.la:.3f} fore {self.lb:.3f} palm offset {tuple(round(x, 3) for x in self.palm_off_rest)}")

    def hand_rot_for(self, F, N):
        """armature rotation for the hand bone giving fingers F and palm normal N"""
        F = F.normalized()
        N = (N - F * N.dot(F)).normalized()
        T = N.cross(F) if self.side == "L" else F.cross(N)
        target = Matrix((F, N, T.normalized())).transposed()
        R = target @ self.hand_rest_basis.inverted()            # rotation taking rest basis to target
        return R @ self.hand_rest_rot

    def solve(self, palm, F, N, pole, clav_up_deg=0.0):
        """pose the chain: palm centre at 'palm', fingers F, palm normal N, elbow towards 'pole' (direction)"""
        b = self.b
        # clavicle lift: rotate the shoulder about the forward axis (rig -Y) raising the arm side
        sh = bone(b["Shoulder"])
        sh_rest = rest_mat(b["Shoulder"])
        lift = Matrix.Rotation(math.radians(clav_up_deg) * self.sgn, 4, Vector((0, -1, 0)))
        sh_pivot = sh_rest.to_translation()
        sh.matrix = Matrix.Translation(sh_pivot) @ lift @ Matrix.Translation(-sh_pivot) @ sh_rest
        bpy.context.view_layer.update()
        S = (ARM.matrix_world @ bone(b["Arm"]).matrix).to_translation()
        hand_rot = self.hand_rot_for(F, N)
        R = hand_rot @ self.hand_rest_rot.inverted()
        W = palm - R @ self.palm_off_rest
        d_vec = W - S
        d = min(d_vec.length, self.la + self.lb - 1e-4)
        u = d_vec.normalized()
        v = (pole - u * pole.dot(u))
        if v.length < 1e-6:
            v = Vector((0, 0, -1)) - u * (-u.z)
        v.normalize()
        cosA = (self.la ** 2 + d ** 2 - self.lb ** 2) / (2 * self.la * d)
        cosA = max(-1.0, min(1.0, cosA))
        sinA = math.sqrt(1 - cosA * cosA)
        E = S + (u * cosA + v * sinA) * self.la
        Wc = S + u * d
        pn = (E - S).cross(Wc - E).normalized()
        # orientation-agnostic: rotate each segment so its REST limb direction + REST hinge normal land on the new ones
        Q1 = align2(self.dir_up_rest, self.pn_rest, (E - S).normalized(), pn)
        Q2 = align2(self.dir_fore_rest, self.pn_rest, (Wc - E).normalized(), pn)
        self._set(b["Arm"], Q1 @ rest_mat(b["Arm"]).to_3x3(), S)
        self._set(b["ArmTwist"], Q1 @ rest_mat(b["ArmTwist"]).to_3x3(), None)
        self._set(b["ForeArm"], Q2 @ rest_mat(b["ForeArm"]).to_3x3(), None)
        # share half of the hand's roll about the forearm axis with the forearm-twist bone
        hand_delta = hand_rot @ rest_mat(b["Hand"]).to_3x3().inverted()        # world delta of the hand
        rel = (Q2.inverted() @ hand_delta).to_quaternion()                      # relative to the forearm, rest frame
        a = self.dir_fore_rest
        proj = Vector((rel.x, rel.y, rel.z)).dot(a)
        tw = Quaternion((rel.w, a.x * proj, a.y * proj, a.z * proj))
        if tw.magnitude > 1e-6:
            tw.normalize()
            half = Quaternion(a, tw.angle * 0.5 * (1 if Vector((tw.x, tw.y, tw.z)).dot(a) >= 0 else -1))
        else:
            half = Quaternion()
        self._set(b["ForeArmTwist"], Q2 @ half.to_matrix() @ rest_mat(b["ForeArmTwist"]).to_3x3(), None)
        self._set(b["Hand"], hand_rot, None)
        bpy.context.view_layer.update()
        reach_err = (Wc - W).length
        return E, Wc, reach_err

    def _set(self, name, rot3, head_world):
        pbn = bone(name)
        bpy.context.view_layer.update()
        cur = ARM.matrix_world @ pbn.matrix
        pos = head_world if head_world is not None else cur.to_translation()
        if head_world is None:
            # keep the bone attached to its parent (position follows the parent's pose)
            par = pbn.parent
            rel = (ARM.matrix_world @ ARM.data.bones[par.name].matrix_local).inverted() @ (ARM.matrix_world @ ARM.data.bones[name].matrix_local)
            pos = (ARM.matrix_world @ par.matrix @ rel).to_translation()
        m = rot3.to_4x4()
        m.translation = pos
        pbn.matrix = ARM.matrix_world.inverted() @ m
        bpy.context.view_layer.update()


ARMS = {"L": ArmModel("L"), "R": ArmModel("R")}


def set_fingers(side, open_amt, curl_extra=0.0):
    """open_amt 0 = BI rest half-fist, 1 = straight; curl_extra (deg) closes every joint a bit more (grip)"""
    pre = "Left" if side == "L" else "Right"
    for fng in ("Index", "Middle", "Ring", "Pinky"):
        for k in (2, 3, 4):
            n = f"{pre}Hand{fng}{k}"
            par = f"{pre}Hand{fng}{k - 1}"
            bpy.context.view_layer.update()
            hp = (ARM.matrix_world @ bone(par).matrix).to_translation()
            hk = (ARM.matrix_world @ bone(n).matrix).to_translation()
            nxt = f"{pre}Hand{fng}{k + 1}"
            if k < 4 or nxt in ARM.pose.bones:
                hn = (ARM.matrix_world @ bone(nxt).matrix).to_translation() if nxt in ARM.pose.bones else None
            else:
                hn = None
            if hn is None:
                tl = ARM.matrix_world @ bone(n).tail
                hn = tl
            d0 = (hk - hp)
            d1 = (hn - hk)
            if d0.length < 1e-5 or d1.length < 1e-5:
                continue
            ang = d0.angle(d1)
            ax = d0.cross(d1)
            if ax.length < 1e-6:
                continue
            ax.normalize()
            rot_deg = -math.degrees(ang) * open_amt + curl_extra
            R = Matrix.Translation(hk) @ Matrix.Rotation(math.radians(rot_deg), 4, ax) @ Matrix.Translation(-hk)
            m = ARM.matrix_world @ bone(n).matrix
            bone(n).matrix = ARM.matrix_world.inverted() @ (R @ m)
    bpy.context.view_layer.update()


def neutral_palm(side):
    """clip start/end: hand in front of the lower chest (close to a low-ready support-hand position)"""
    sx = 1 if side == "L" else -1
    n = CFG.get("neutral", (0.22, -0.16, 1.18))
    return Vector((n[0] * sx, n[1], n[2]))


def grip_point(side, cupM, spec):
    g = spec.get("grip", {})
    s = SIDES[side]
    # cup-rest grip point on the outer shell, Punisherbody frame: lower-front quarter of the outer face
    gp_pb = Vector((s * g.get("out", 0.121), g.get("fwd", -0.020), g.get("z", 1.636)))
    n_pb = Vector((s * 1.0, 0, 0))
    gp = HEAD_DELTA @ (cupM @ pb2rig(gp_pb))
    n = (HEAD_DELTA.to_3x3() @ (cupM.to_3x3() @ pb2rig(n_pb))).normalized()
    return gp, n


def hand_frame(side, gp, n_out, fingers_pref):
    palm = gp + n_out * g_palm_gap
    N = -n_out                                     # palm faces the cup
    F = fingers_pref - N * fingers_pref.dot(N)
    if F.length < 1e-4:
        F = Vector((0, 0, 1)) - N * N.z
    return palm, F.normalized(), N


g_palm_gap = CFG.get("palm_gap", 0.004)


def lerp(a, b, t):
    return a + (b - a) * t


def slerp_dir(a, b, t):
    qa = Vector((0, 0, 1)).rotation_difference(a.normalized())
    qb = Vector((0, 0, 1)).rotation_difference(b.normalized())
    return (qa.slerp(qb, t) @ Vector((0, 0, 1))).normalized()


# ------------------------------------------------------------------ clip evaluation
def evaluate_clip(spec):
    """returns per-frame list of (bone matrices dict) + diagnostics"""
    nfr = int(round(spec["duration"] * FPS))
    sides = spec["sides"]                      # e.g. ["L"] or ["L", "R"]
    frames = []
    diag = []
    for f in range(nfr + 1):
        t = f / FPS
        apply_base_pose()
        row = {"t": round(t, 3)}
        for side in sides:
            off = spec.get("side_delay", {}).get(side, 0.0)
            tt = max(0.0, t - off)
            ph = spec["phases"]                 # times (s): reach_end, release_start, release_end, return_end
            ch = channels_at(spec, side, tt)
            cupM = cup_matrix(side, ch)
            gp, n_out = grip_point(side, cupM, spec)
            # preferred finger direction: up and a little back (+Y rig = back) at the ear, pointing back as the cup
            # goes over the top to the rear of the helmet
            swing01 = max(0.0, min(1.0, ch.get("swing", 0.0) / 160.0))
            pref = slerp_dir(Vector(CFG.get("fingers_ear", (0, 0.35, 1))), Vector(CFG.get("fingers_back", (0, 1, 0.25))), swing01)
            palm_g, F_g, N_g = hand_frame(side, gp, n_out, pref)
            sx = 1 if side == "L" else -1
            pl = CFG.get("pole_low", (0.6, -0.7, -0.5))
            ph_ = CFG.get("pole_high", (1.0, 0.1, 0.6))
            pole_low = Vector((sx * pl[0], pl[1], pl[2]))
            pole_high = Vector((sx * ph_[0], ph_[1], ph_[2]))
            pole_g = slerp_dir(pole_low, pole_high, swing01)
            pole_rest = Vector((sx * 0.4, -0.6, -1.0))
            np_ = neutral_palm(side)
            Fn = Vector((0, -1, 0.35)).normalized()
            Nn = Vector((-sx * 1.0, 0, 0))
            if tt < ph["reach_end"]:
                u = ease(tt / ph["reach_end"])
                # approach from outside: lateral bulge mid-reach
                bulge = n_out * (CFG.get('reach_bulge', 0.09) * math.sin(math.pi * u))
                palm = lerp(np_, palm_g, u) + bulge
                F = slerp_dir(Fn, F_g, u)
                N = slerp_dir(Nn, N_g, u)
                pole = slerp_dir(pole_rest, pole_g, u)
                phase = "reach"
                fopen, fcurl = 0.6 * u, 0.0
            elif tt < ph["release_start"]:
                palm, F, N, pole, phase = palm_g, F_g, N_g, pole_g, "grip"
                fopen, fcurl = CFG.get("grip_open", 0.45), 0.0
            elif tt < ph["release_end"]:
                u = ease((tt - ph["release_start"]) / (ph["release_end"] - ph["release_start"]))
                palm, F, N, pole, phase = palm_g + n_out * (0.045 * u), F_g, N_g, pole_g, "release"
                fopen, fcurl = CFG.get("grip_open", 0.45) + 0.25 * u, 0.0
            else:
                u = ease((tt - ph["release_end"]) / max(1e-3, (ph["return_end"] - ph["release_end"])))
                rel = palm_g + n_out * 0.045
                palm = lerp(rel, np_, u)
                F = slerp_dir(F_g, Fn, u)
                N = slerp_dir(N_g, Nn, u)
                pole = slerp_dir(pole_g, pole_rest, u)
                phase = "return"
                fopen, fcurl = (CFG.get("grip_open", 0.45) + 0.25) * (1 - u), 0.0
            clav = 14.0 * max(0.0, min(1.0, (palm.z - 1.40) / 0.30))
            E, Wc, err = ARMS[side].solve(palm, F, N, pole, clav)
            set_fingers(side, fopen, fcurl)
            # contact check: palm centre after solving vs grip target
            hb = ARM.matrix_world @ bone(SIDE_BONES[side]["Hand"]).matrix
            palm_now = hb.to_translation() + (hb.to_3x3() @ ARMS[side].hand_rest_rot.inverted()) @ ARMS[side].palm_off_rest
            if CFG.get("debug_frame") is not None and f == CFG["debug_frame"]:
                pre = "Left" if side == "L" else "Right"
                log(f"DEBUG f{f} t{t:.2f} side {side} target palm {tuple(round(x, 3) for x in palm)} grip {tuple(round(x, 3) for x in gp)} pole {tuple(round(x, 2) for x in pole)}")
                for nm in ("Shoulder", "Arm", "ArmTwist", "ForeArm", "ForeArmTwist", "Hand", "HandMiddle1", "HandMiddle4", "HandThumb4"):
                    bb = bone(pre + nm)
                    hw = (ARM.matrix_world @ bb.matrix).to_translation()
                    log(f"   {pre + nm:22s} head {tuple(round(x, 3) for x in hw)}  E {tuple(round(x, 3) for x in E)} Wc {tuple(round(x, 3) for x in Wc)}")
                for o in bpy.data.objects:
                    if o.type == 'MESH' and o.name.startswith("Hands"):
                        dg2 = bpy.context.evaluated_depsgraph_get()
                        oe = o.evaluated_get(dg2)
                        me2 = oe.to_mesh()
                        vs = [oe.matrix_world @ v.co for v in me2.vertices]
                        oe.to_mesh_clear()
                        left = [v for v in vs if v.x > 0.0]
                        if left:
                            c = sum(left, Vector()) / len(left)
                            log(f"   Hands mesh left-half centroid {tuple(round(x, 3) for x in c)} n={len(left)}")
                        mods = [(m.type, getattr(m, 'object', None) and m.object.name) for m in o.modifiers]
                        log(f"   Hands modifiers {mods}")
            row[side] = {"phase": phase, "reach_err_mm": round(err * 1000, 1),
                         "palm_to_grip_mm": round((palm_now - (palm_g if phase == "grip" else palm)).length * 1000, 1),
                         "ch": {k: round(v, 2) for k, v in ch.items()}}
        frames.append(capture_locals(sides))
        diag.append(row)
    return frames, diag


def track_bones(sides):
    out = []
    for side in sides:
        pre = "Left" if side == "L" else "Right"
        for n in ("Shoulder", "Arm", "ArmTwist", "ForeArm", "ForeArmTwist", "Hand"):
            out.append(pre + n)
    return out


def capture_locals(sides):
    data = {}
    for side in ("L", "R"):
        pre = "Left" if side == "L" else "Right"
        names = [b.name for b in ARM.data.bones if b.name.startswith(pre + "Shoulder") or b.name.startswith(pre + "Arm")
                 or b.name.startswith(pre + "ForeArm") or b.name.startswith(pre + "Hand")]
        for n in names:
            pbn = bone(n)
            m = (pbn.parent.matrix.inverted() @ pbn.matrix) if pbn.parent else pbn.matrix
            data[n] = m.copy()
    return data


# ------------------------------------------------------------------ TXA writer (arm-only profile)
def num(v, nd):
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "", "-") else s


ARM_TREE = {}            # parent -> children (profile parents)


def profile_tracks(side):
    pre = "Left" if side == "L" else "Right"
    t = [(pre + "Shoulder", "Spine5", "RA"), (pre + "Arm", pre + "Shoulder", "RA"), (pre + "ArmVolume", pre + "Arm", "RA"),
         (pre + "ArmTwist", pre + "Arm", "RA"), (pre + "ForeArm", pre + "ArmTwist", "RA"),
         (pre + "ForeArmVolume", pre + "ForeArm", "RA"), (pre + "ForeArmTwist", pre + "ForeArm", "RA"),
         (pre + "HandUpperVolume", pre + "ForeArmTwist", "RA"), (pre + "Hand", pre + "ForeArmTwist", "RA")]
    for fng in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        par = pre + "Hand"
        for k in range(1, 5):
            t.append((f"{pre}Hand{fng}{k}", par, "RA"))
            par = f"{pre}Hand{fng}{k}"
    t += [(pre + "HandInbetween", pre + "Hand", "TRA"), (pre + "HandProp", pre + "Hand", "TRA")]
    return t


def write_profile(path, sides):
    lines = ["$animExportProfile {", " #trackCount 152", ' #defaultFn ""', " $tracks {", '\t"Spine5"\t\t\t\t\t""\t\t\t\t\t""']
    for side in sides:
        for n, p, fl in profile_tracks(side):
            lines.append(f'\t"{n}"\t\t\t\t"{p}"\t\t\t\t"{fl}"')
    lines += [" }", "}"]
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def write_txa(path, frames, sides):
    nf = len(frames) - 1
    tracks = []
    for side in sides:
        tracks += profile_tracks(side)
    present = set(frames[0].keys())
    children = {}
    for n, p, fl in tracks:
        children.setdefault(p, []).append((n, fl))
    out = ['$animation "" {', " #version 2", f" #fps {FPS}", f" #numFrames {nf}"]

    def emit(name, fl, ind):
        out.append(f'{ind}$node "{name}" {{')
        # untracked profile root (Spine5): node only. An empty '$keys' block was imported as an identity track and
        # collapsed Spine5 in game (POSE_GRIP log 2026-11-06 20:10).
        if name in present and fl:
            out.append(f"{ind} $keys t q {{")
            for f, fr in enumerate(frames):
                m = fr[name]
                t, q = m.to_translation(), m.to_quaternion()
                out.append(f"{ind}  $frame {f} {{")
                # always write the local translation: the importer zeroed missing #t on RA tracks (bones collapsed
                # onto their parents in game, 2026-11-06 hand_unarmed2)
                out.append(f"{ind}   #t {num(t.x, 7)} {num(t.z, 7)} {num(t.y, 7)}")
                out.append(f"{ind}   #q {num(-q.x, 8)} {num(-q.z, 8)} {num(-q.y, 8)} {num(q.w, 8)}")
                out.append(f"{ind}  }}")
            out.append(f"{ind} }}")
        for c, cfl in children.get(name, []):
            emit(c, cfl, ind + " ")
        out.append(f"{ind}}}")

    # no Spine5 node: a keyless node shifted every track up one bone and an empty key block became an identity
    # Spine5 track (both seen in game 2026-11-06). The arm roots (shoulders) are the top-level nodes.
    for c, cfl in children.get("Spine5", []):
        emit(c, cfl, " ")
    out.append("}")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")


# ------------------------------------------------------------------ review rendering (optional)
REVIEW = CFG.get("review")
EAR_OBJ, EAR_V, EAR_PART = None, None, None
if REVIEW:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ep_common as EC

    def _imp(path):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        ms = []
        for o in new:
            if o.type == 'ARMATURE' or o.name.upper().startswith(("UCX", "UTM", "USP")):
                o.hide_render = True
                o.hide_viewport = True
            elif o.type == 'MESH':
                ms.append(o)
        return ms

    def _bake_rig(o):
        """freeze an imported (bind-pose) mesh into the rig frame as a plain mesh object"""
        dg = bpy.context.evaluated_depsgraph_get()
        oe = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(oe)
        me.transform(PB2RIG @ o.matrix_world)
        n = bpy.data.objects.new(o.name + "_rig", me)
        bpy.context.scene.collection.objects.link(n)
        n.matrix_world = HEAD_DELTA
        o.hide_render = True
        o.hide_viewport = True
        return n

    for o in bpy.data.objects:                      # keep body, head, hands, jacket; hide the rest of the sample kit
        if o.type == 'MESH':
            keep = o.name.split("_")[0] in ("Head", "Hands", "Jacket", "Pants", "eyeLeft", "eyeRight")
            o.hide_render = not keep
            o.color = (0.75, 0.62, 0.52, 1) if o.name.startswith(("Head", "Hands")) else (0.35, 0.38, 0.30, 1)
    helm = []
    for h in REVIEW["helmet"]:
        for o in _imp(h):
            r = _bake_rig(o)
            r.color = (0.45, 0.45, 0.42, 1)
            helm.append(r)
    eo = _imp(REVIEW["earpro"])[0]
    EAR_OBJ = _bake_rig(eo)
    EAR_OBJ.color = (0.72, 0.62, 0.45, 1)
    dg = bpy.context.evaluated_depsgraph_get()
    # rest coordinates in the Punisherbody frame for classification (same rules as the in-game rig)
    pbV = [PB2RIG.inverted() @ v.co for v in EAR_OBJ.data.vertices]
    isl, _ = EC.islands_of(EAR_OBJ.data)
    _, _, _, EAR_PART = EC.classify(pbV, isl, None, log)
    EAR_V = pbV


def pose_earpro(chs):
    """chs: side -> channels; poses the review ear-pro mesh (rig frame)"""
    if not EAR_OBJ:
        return
    mats = {}
    for side, s in SIDES.items():
        arm, cup = side_mats_pb(side, chs.get(side, {}))
        mats[s] = (arm, cup)
    me = EAR_OBJ.data
    for i, v in enumerate(me.vertices):
        kind, s = EAR_PART[i]
        p = EAR_V[i]
        if kind == "ARM":
            p = mats[s][0] @ p
        elif kind in ("CUP", "MIC"):
            p = mats[s][1] @ p
        v.co = PB2RIG @ p
    me.update()


def render_frame(tag, spec, t):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'OBJECT'
    sc.render.resolution_x, sc.render.resolution_y = REVIEW.get("res", [640, 640])
    cam = bpy.data.objects.get("PLHM_cam")
    if not cam:
        cd = bpy.data.cameras.new("PLHM_cam")
        cd.type = 'ORTHO'
        cam = bpy.data.objects.new("PLHM_cam", cd)
        sc.collection.objects.link(cam)
    sc.camera = cam
    C = Vector((0, 0.0, 1.55))
    for vname, (off, scale) in {"left": (Vector((1.6, 0, 0)), 0.75), "front34": (Vector((1.1, -1.1, 0.2)), 0.75),
                                "back34": (Vector((1.0, 1.1, 0.35)), 0.75)}.items():
        if vname not in REVIEW.get("views", ["left", "front34", "back34"]):
            continue
        cam.location = C + off
        cam.rotation_euler = (C - cam.location).to_track_quat('-Z', 'Y').to_euler()
        cam.data.ortho_scale = scale
        sc.render.filepath = os.path.join(OUT, "review", f"{tag}_t{int(t * 100):03d}_{vname}.png")
        bpy.ops.render.render(write_still=True)


# ------------------------------------------------------------------ main
summary = {}
_orig_eval = evaluate_clip


def evaluate_clip(spec):
    frames, diag = _orig_eval(spec)
    return frames, diag


for name, spec in CFG["clips"].items():
    frames, diag = evaluate_clip(spec)
    if REVIEW and name in REVIEW.get("clips", []):
        # re-pose selected times and render (re-solves the arm at that time)
        for t in REVIEW.get("times", [0.3, 0.6, 1.0, 1.4, 1.8]):
            sub = dict(spec)
            sub["duration"] = t
            fr, dg_ = _orig_eval(sub)                  # leaves the skeleton posed at time t
            chs = {}
            for side in spec["sides"]:
                off = spec.get("side_delay", {}).get(side, 0.0)
                chs[side] = channels_at(spec, side, max(0.0, t - off))
            pose_earpro(chs)
            bpy.context.view_layer.update()
            render_frame(name, spec, t)
    sides = spec["sides"]
    write_txa(os.path.join(OUT, name + ".txa"), frames, sides)
    worst = max((r[s]["palm_to_grip_mm"] for r in diag for s in sides if r[s]["phase"] == "grip"), default=0)
    reach = max((r[s]["reach_err_mm"] for r in diag for s in sides), default=0)
    summary[name] = {"frames": len(frames) - 1, "worst_grip_contact_mm": worst, "worst_reach_shortfall_mm": reach,
                     "sides": sides, "duration": spec["duration"]}
    json.dump(diag, open(os.path.join(OUT, name + "_diag.json"), "w"), indent=0)
    log(name, json.dumps(summary[name]))
    # timeline for the game: cup channel keys per side in CLIP seconds (+ side delays baked in)
    tl = {}
    for side in sides:
        off = spec.get("side_delay", {}).get(side, 0.0)
        tl[side] = {k: [[round(t + off, 4), v] for t, v in keys] for k, keys in spec["cup_keys"][side].items()}
    json.dump({"clip": name, "duration": spec["duration"], "phases": spec["phases"], "cup_keys": tl},
              open(os.path.join(OUT, name + "_timeline.json"), "w"), indent=1)
for prof, sides in CFG.get("profiles", {}).items():
    write_profile(os.path.join(OUT, prof + ".apr"), sides)
json.dump(summary, open(os.path.join(OUT, "clips_summary.json"), "w"), indent=1)

# review: optional pose snapshots saved as a .blend for rendering
if CFG.get("save_blend"):
    bpy.ops.wm.save_as_mainfile(filepath=CFG["save_blend"], copy=True)
log("DONE")
LOGF.close()
