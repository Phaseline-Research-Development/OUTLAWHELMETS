"""Re-export every colourway of a helmet from its 4096 Painter project at 2048 (user rule: project 4096, export 2048).

  python _tools/export_helmet_colours.py ballistic
  python _tools/export_helmet_colours.py airframe
  python _tools/export_helmet_colours.py xp | xp4     (xp4 = XP1 of the 4-hole bake, XP4_texturing.spp -> XP1H4_<TAG>)

Opens the saved Painter project (its saved state is the user's MCB stack with this helmet's masks), exports MCB as-is, then
applies each colourway's FINAL tuned inputs (swatches / graded camo written by calibrate_ballistic.py / airframe_colours.py,
no re-tuning) and exports. Output: _tools/work/painter/export/<PREFIX><TAG>_BCR.png / _NMO.png, 2048, straight from Painter.
"""
import glob, json, os, re, socket, sys, time

ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
PW = ROOT + "_tools/work/painter/"
SW = PW + "swatches/"
V = "D:/3D Source Library/Headgear/SF_V2/SF_V2/tex/"
AFT = "C:/Users/lebea/OneDrive/Desktop/Cars/Helmet_CRYE_Airframe_v03/Helmet_CRYE_Airframe_v03/Textures/PBR_Helmet_CRYE_Airframe_tx/"
KEYS = ("velcro", "nylon", "composite", "grain", "rubber")

HELMETS = {
    "ballistic": {
        "spp": PW + "SF_Ballistic_texturing.spp", "prefix": "", "tset": "SF",
        "uids": {"base": 839, "shell_base": 1393, "shell_fill": 1569, "velcro": 890, "nylon_fill": 2195,
                 "composite_fill": 4265, "rubber": 4562, "grain": 2309},
        "base": {"AOR1": V + "aor1/SF_aor1.png", "MC": V + "mc/SF_mc.png", "OD": V + "gray/SF_gray.png",
                 "RG": V + "gray/SF_gray.png", "TAN": V + "SF_tan.png"},
        "camo": {"AOR1": ("AOR1", True), "MC": ("MC", False)},
    },
    "airframe": {
        "spp": ROOT + "_tools/work/airframe/painter/AF_texturing.spp", "prefix": "AF_", "tset": "MI_Helmet_CRYE_Airframe_Tan",
        "uids": {"base": 40, "shell_base": 384, "shell_fill": 399, "velcro": 556, "nylon_fill": 372,
                 "composite_fill": 149, "rubber": 62, "grain": 153},
        "base": {k: AFT + ("Helmet_CRYE_Airframe_OCP_BaseColor.png" if k == "MC" else "Helmet_CRYE_Airframe_Tan_BaseColor.png")
                 for k in ("AOR1", "MC", "OD", "RG", "TAN")},
        "camo": {"AOR1": ("AF_AOR1", False), "MC": ("MC", False)},
    },
}


def painter(code, timeout=900):
    s = socket.create_connection(("127.0.0.1", 60043), timeout=timeout)
    s.sendall((json.dumps({"id": 1, "op": "python.exec", "params": {"code": code}}) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        buf += s.recv(1 << 20)
    r = json.loads(buf.split(b"\n")[0])
    if not r.get("ok"):
        raise RuntimeError(r)
    return r["result"]["result"]


def wait():
    time.sleep(2)
    while painter("import substance_painter.project as pj\nresult = pj.is_busy()"):
        time.sleep(2)
    time.sleep(2)


def last(tag, key):
    files = glob.glob(f"{SW}{tag}[0-9]_{key}.png")
    return max(files, key=lambda f: int(re.search(rf"{re.escape(tag)}(\d)_", os.path.basename(f)).group(1)))


MS = "D:/3D Source Library/Headgear/OpscoreMaritime/OpscoreMaritime/"
MUIDS = json.load(open(ROOT + "_tools/work/maritime/painter/uids.json")) if os.path.exists(ROOT + "_tools/work/maritime/painter/uids.json") else {}
HELMETS["maritime"] = {
    "spp": ROOT + "_tools/work/maritime/painter/MT_texturing.spp", "prefix": "", "sets": MUIDS,
    "base": {"MT": {k: MS + ("MC/MT_mc.png" if k in ("MC", "MCB") else "AOR1/MT_aor1.png") for k in ("AOR1", "MC", "OD", "RG", "TAN")},
             "KitA": {k: MS + "KitAVelcro/KitA_co.png" for k in ("AOR1", "MC", "OD", "RG", "TAN")}},
    "camo": {"AOR1": ("MT_AOR1", True), "MC": ("MC", False)},
}
XS = "D:/3D Source Library/Headgear/OpscoreXP_Carbon/OpscoreXP_Carbon/"
XUIDS = json.load(open(ROOT + "_tools/work/xp/painter/uids.json")) if os.path.exists(ROOT + "_tools/work/xp/painter/uids.json") else {}
_xpb = {k: XS + ("XP/pbr/xp_low_XP_BaseColor.png" if k in ("MC", "MCB") else "XP/Tan/pbr/xp_tan_XP_BaseColor.png") for k in ("AOR1", "MC", "OD", "RG", "TAN")}
HELMETS["xp"] = {
    "spp": ROOT + "_tools/work/xp/painter/XP_texturing.spp", "prefix": "", "sets": XUIDS,
    "base": {"XP1": _xpb, "XP4M": _xpb, "Carbon1": {k: XS + "Carbon/PBR/Carbon_baseColor.jpg" for k in _xpb}},
    "camo": {"AOR1": ("AF_AOR1", False), "MC": ("MC", False)},
}
HELMETS["xp4"] = {**HELMETS["xp"], "spp": ROOT + "_tools/work/xp/painter/XP4_texturing.spp",
                  "sets": {"XP1": XUIDS.get("XP1")}, "set_prefix": {"XP1": "XP1H4_"}}
h = HELMETS[sys.argv[1]]
painter(f"import substance_painter.project as pj\nif pj.is_open(): pj.close()\npj.open(r'{h['spp']}')\nresult = 'ok'")
wait()
painter("exec(open(r'" + ROOT + "_tools/painter_ballistic.py').read(), globals())\n"
        "import builtins; builtins.PB = {k: v for k, v in globals().items()}\nresult = 'ok'")
SETS = h["sets"] if "sets" in h else {h["tset"]: h["uids"]}
for tset, u in SETS.items():
    pre = h.get("set_prefix", {}).get(tset, tset + "_") if "sets" in h else h["prefix"]
    painter(f"import builtins\nbuiltins.PB['configure']({u!r}, {tset!r})\nresult = 'ok'")
    print(tset, "MCB", painter(f"import builtins\nresult = builtins.PB['export']('{pre}MCB', 11, True)"))
for tag in ("AOR1", "MC", "OD", "RG", "TAN"):
    sw = {k: last(tag, k) for k in KEYS}
    if tag in h["camo"]:
        src, identity = h["camo"][tag]
        shell = ["bitmap", last(src, "camo"), identity]
    else:
        shell = ["swatch", last(tag, "shell")]
    for tset, u in SETS.items():
        pre = h.get("set_prefix", {}).get(tset, tset + "_") if "sets" in h else h["prefix"]
        base = h["base"][tset][tag] if "sets" in h else h["base"][tag]
        cfg = {"base": base, "shell": shell, "swatches": sw}
        print(tag, tset, painter(f"import builtins\nPB = builtins.PB\nPB['configure']({u!r}, {tset!r})\nPB['apply'](" + repr(cfg) + f")\nresult = PB['export']('{pre}{tag}', 11, True)"))
