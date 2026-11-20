"""Generate clips_v5.json: the 16-clip set for every placement family (AMP SF/Maritime, AMP XP, ComTac no-strap SF/XP,
ComTac VI SF/XP). Same hand choreography; cup channel keys per mount type; grip points from each family's rig report."""
import json, copy, os
HERE = os.path.dirname(os.path.abspath(__file__))
E = os.path.dirname(HERE)
v4 = json.load(open(os.path.join(HERE, "clips_v4.json")))
base = {k: v for k, v in v4.items() if k != "clips"}
R = E.replace("\\", "/") + "/build/rig"
FAMILIES = [
    # code, rig report, mount
    ("amp", HERE.replace("\\", "/") + "/data/amp_rig_report.json", "amp"),
    ("ampxp", R + "/amp_xp/OpsCore_AMP_XP_rig_report.json", "amp"),
    ("ctns", R + "/ct_ns/comtacviinostrap_rig_report.json", "comtac"),
    ("ctnsxp", R + "/ct_ns_xp/comtacviinostrap_XP_rig_report.json", "comtac"),
    ("ctvi", R + "/ct_vi/comtacvi_rig_report.json", "comtac"),
    ("ctvixp", R + "/ct_vi_xp/comtacvi_XP_rig_report.json", "comtac"),
]
AMP_SF_CUP = json.load(open(FAMILIES[0][1]))["pivots_model_space"]["R"]["cup_c"]


def grips(rep, mount):
    c = rep["pivots_model_space"]["R"]["cup_c"]
    if mount == "amp":       # the proven AMP grip, moved rigidly with the family's placement
        dy, dz = c[1] - AMP_SF_CUP[1], c[2] - AMP_SF_CUP[2]
        return ({"out": 0.121, "fwd": -0.025 + dy, "z": 1.642 + dz}, {"out": 0.121, "fwd": -0.02 + dy, "z": 1.655 + dz})
    out = abs(c[0]) + 0.0245  # ComTac: outer face of the cup, lower-front quarter (same offsets as the AMP grip)
    return ({"out": out, "fwd": c[1] + 0.0136, "z": c[2] - 0.0217}, {"out": out, "fwd": c[1] + 0.018, "z": c[2] - 0.009})


AMP = {
    "raise": {"splay": [[0.45, 0], [0.736, 44], [1.36, 44], [1.698, 24]], "swing": [[0.645, 0], [1.516, 161.5]],
              "yaw": [[1.256, 0], [1.698, 46.5]], "spin": [[1.256, 0], [1.698, -4.5]]},
    "lower": {"splay": [[0.602, 24], [0.94, 44], [1.564, 44], [1.85, 0]], "swing": [[0.784, 161.5], [1.655, 0]],
              "yaw": [[0.602, 46.5], [1.044, 0]], "spin": [[0.602, -4.5], [1.044, 0]]},
    "vent": {"splay": [[0.45, 0], [0.8, 14]]}, "unvent": {"splay": [[0.45, 14], [0.8, 0]]},
    "raiseX": {"splay": [[0.7, 0], [0.98, 44], [1.6, 44], [1.94, 24]], "swing": [[0.88, 0], [1.75, 161.5]],
               "yaw": [[1.5, 0], [1.94, 46.5]], "spin": [[1.5, 0], [1.94, -4.5]]},
    "lowerX": {"splay": [[0.85, 24], [1.19, 44], [1.81, 44], [2.1, 0]], "swing": [[1.03, 161.5], [1.9, 0]],
               "yaw": [[0.85, 46.5], [1.29, 0]], "spin": [[0.85, -4.5], [1.29, 0]]},
    "ventX": {"splay": [[0.65, 0], [1.0, 14]]}, "unventX": {"splay": [[0.65, 14], [1.0, 0]]},
}
# ComTac on the ARC adapter: out, swing back about the hub to the rear fold (Tyler's photo 184811), settle; the ARC
# detent holds it there, so the hand carries the cup the whole way (no early release as on the AMP)
CT = {
    "raise": {"splay": [[0.45, 0], [0.7, 22], [1.3, 22], [1.6, 18]], "swing": [[0.6, 0], [1.45, -90]]},
    "lower": {"splay": [[0.6, 18], [0.82, 22], [1.45, 22], [1.8, 0]], "swing": [[0.75, -90], [1.6, 0]]},
    "vent": {"splay": [[0.45, 0], [0.8, 16]]}, "unvent": {"splay": [[0.45, 16], [0.8, 0]]},
    "raiseX": {"splay": [[0.7, 0], [0.95, 22], [1.55, 22], [1.85, 18]], "swing": [[0.88, 0], [1.75, -90]]},
    "lowerX": {"splay": [[0.85, 18], [1.07, 22], [1.7, 22], [2.05, 0]], "swing": [[1.0, -90], [1.85, 0]]},
    "ventX": {"splay": [[0.65, 0], [1.0, 16]]}, "unventX": {"splay": [[0.65, 16], [1.0, 0]]},
}
PH = {"raise": (2.3, {"reach_end": 0.45, "release_start": 1.75, "release_end": 1.92, "return_end": 2.3}),
      "lower": (2.5, {"reach_end": 0.6, "release_start": 1.95, "release_end": 2.12, "return_end": 2.5}),
      "vent": (1.3, {"reach_end": 0.45, "release_start": 0.85, "release_end": 0.97, "return_end": 1.3}),
      "unvent": (1.3, {"reach_end": 0.45, "release_start": 0.85, "release_end": 0.97, "return_end": 1.3})}
PHX = {"amp": {"raise": (2.5, {"reach_end": 0.7, "release_start": 1.45, "release_end": 1.58, "return_end": 2.5}),
               "lower": (2.8, {"reach_end": 0.85, "release_start": 2.2, "release_end": 2.33, "return_end": 2.8})},
       "comtac": {"raise": (2.6, {"reach_end": 0.7, "release_start": 1.95, "release_end": 2.08, "return_end": 2.6}),
                  "lower": (2.8, {"reach_end": 0.85, "release_start": 2.2, "release_end": 2.33, "return_end": 2.8})}}
VX = (1.6, {"reach_end": 0.65, "release_start": 1.05, "release_end": 1.17, "return_end": 1.6})
D = 0.08


def full(k):
    out = {"splay": [[0, 0]], "swing": [[0, 0]], "yaw": [[0, 0]], "spin": [[0, 0]]}
    out.update(copy.deepcopy(k))
    return out


clips = {}
for fam, rr, mount in FAMILIES:
    rep = json.load(open(rr))
    g, xg = grips(rep, mount)
    K = AMP if mount == "amp" else CT
    swing_full = 160.0 if mount == "amp" else 90.0
    def mk(name, sides, dur, phases, keys, **kw):
        c = {"sides": sides, "duration": round(dur, 3), "phases": phases, "grip": g, "rig_report": rr, "swing_full": swing_full,
             "cup_keys": {sd: full(keys) for sd in sides}}
        c.update(kw)
        clips[f"plhm_{fam}_{name}"] = c
    for a in ("raise", "lower", "vent", "unvent"):
        dur, ph = PH[a]
        for sd in ("L", "R"):
            mk(f"{a}_{sd}", [sd], dur, ph, K[a])
        mk(f"{a}_B", ["L", "R"], dur + D, ph, K[a], side_delay={"R": D})
base["clips"] = clips
json.dump(base, open(os.path.join(HERE, "clips_v5.json"), "w"), indent=1)
print(len(clips), "clips;", "families", [f[0] for f in FAMILIES])
# the AMP SF family must reproduce the in-game-verified v4 clips exactly
for k, v in v4["clips"].items():
    if k not in clips:
        continue
    n = clips[k]
    for f in ("sides", "phases", "grip", "cup_keys"):
        a = json.dumps(v.get(f), sort_keys=True)
        b = json.dumps({sd: {ch: n["cup_keys"][sd][ch] for ch in v["cup_keys"][sd]} for sd in v["cup_keys"]} if f == "cup_keys" else n.get(f), sort_keys=True)
        if a != b:
            print("DIFF", k, f, a[:120], "|", b[:120])
