"""Drive Painter (bridge 127.0.0.1:60043) to texture the Ballistic in each colourway with the user's MCB stack.

  python _tools/calibrate_ballistic.py AOR1 MC OD RG TAN

Per colourway: vendor base atlas + shell camo/colour as the matching Bump uses it, then every colour-bearing material
layer (velcro, webbing, composite, grain, rubber, and the solid shell) is tuned with swatch PNGs until its region in the
export matches the same region of that colour's ORIGINAL Bump texture (the Bump layout is shared, so the texels are the
same parts). Final 4K BCR/NMO export -> _tools/work/painter/export/<TAG>_BCR.png / _NMO.png.
"""
import json, os, socket, sys
import numpy as np
from PIL import Image

ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
WORK = ROOT + "_tools/work/"
PW = WORK + "painter/"
V = "D:/3D Source Library/Headgear/SF_V2/SF_V2/tex/"
CAMO = "C:/Users/lebea/Downloads/camopk/"
REGIONS = np.load(PW + "layer_regions.npz")
BUMP = {"AOR1": "HELMET AOR1_AOR1SF_BCR.tif", "MCB": "HELMET BLACK_mcbSF_BCR.tif", "OD": "HELMET GREEN_grSF_BCR.tif",
        "MC": "HELMET MC_SF_BCR.tif", "RG": "HELMET RG_RGSF_BCR.tif", "TAN": "HELMET TAN_tanSF_BCR.tif"}
LAYERS = {"velcro": "09_Bebra_Velcro", "nylon": "07_Nylon_Webbing", "composite": "05_Plastic_Composite",
          "grain": "06_Plastic_Base_Grain", "rubber": "04_Rubber_Raw", "shell": "08_Plastic_Grainy_Soft"}
COLOURS = {
    "AOR1": {"base": V + "aor1/SF_aor1.png", "shell": ("bitmap", V + "aor1/SF_aor1.png", True)},
    "MC": {"base": V + "mc/SF_mc.png", "shell": ("bitmap", CAMO + "MultiCambetter.png", False)},
    "OD": {"base": V + "gray/SF_gray.png", "shell": ("swatch",)},
    "RG": {"base": V + "gray/SF_gray.png", "shell": ("swatch",)},
    "TAN": {"base": V + "SF_tan.png", "shell": ("swatch",)},
}


def painter(code):
    s = socket.create_connection(("127.0.0.1", 60043), timeout=600)
    s.sendall((json.dumps({"id": 1, "op": "python.exec", "params": {"code": code}}) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        buf += s.recv(1 << 20)
    r = json.loads(buf.split(b"\n")[0])
    if not r.get("ok"):
        raise RuntimeError(r)
    return r["result"]


def to_lin(c):
    c = np.asarray(c, float) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255


def swatch(tag, name, rgb):
    os.makedirs(PW + "swatches", exist_ok=True)
    p = f"{PW}swatches/{tag}_{name}.png"
    Image.new("RGB", (32, 32), tuple(int(round(v)) for v in rgb)).save(p)
    return p


def region_means(png, keys):
    a = np.asarray(Image.open(png).convert("RGB").resize((1024, 1024))).astype(float)
    return {k: a[REGIONS[LAYERS[k]]].mean(0) for k in keys}


painter(f"exec(open(r'{ROOT}_tools/painter_ballistic.py').read(), globals()); import builtins; builtins.PB = {{k: v for k, v in globals().items()}}\nresult='loaded'")

for tag in sys.argv[1:]:
    cfg = COLOURS[tag]
    bump = np.asarray(Image.open(WORK + "tex_backup/" + BUMP[tag]).convert("RGB").resize((1024, 1024))).astype(float)
    camo = cfg["shell"][0] == "bitmap"
    keys = list(LAYERS)
    target = {k: bump[REGIONS[LAYERS[k]]].mean(0) for k in keys}
    guess = {k: target[k].copy() for k in keys}
    gain = np.ones(3)
    if camo:
        src_img = np.asarray(Image.open(cfg["shell"][1]).convert("RGB")).astype(np.float32)
    for it in range(5):
        sw = {k: swatch(f"{tag}{it}", k, guess[k]) for k in keys if k != "shell" or not camo}
        if camo:
            graded = PW + f"swatches/{tag}{it}_camo.png"
            Image.fromarray(to_srgb(to_lin(src_img) * gain).round().astype(np.uint8), "RGB").save(graded)
            shell = ("bitmap", graded, cfg["shell"][2])
        else:
            shell = ("swatch", sw["shell"])
        c = {"base": cfg["base"], "shell": list(shell), "swatches": {k: sw[k] for k in keys if k != "shell"}}
        out = painter("import builtins\nPB = builtins.PB\nPB['apply'](" + repr(c) + ")\nresult = PB['export']('cal_" + tag + "', 10, False)")
        meas = region_means(PW + f"export/cal_{tag}_BCR.png", keys)
        err = {k: float(np.abs(meas[k] - target[k]).mean()) for k in keys}
        print(tag, "iter", it, {k: round(v, 1) for k, v in err.items()}, out)
        if max(err.values()) < 2.0:
            break
        for k in keys:
            ratio = (to_lin(target[k]) + 1e-4) / (to_lin(meas[k]) + 1e-4)
            if k == "shell" and camo:
                gain = gain * np.clip(ratio, 0.2, 5.0)
            else:
                guess[k] = to_srgb(to_lin(guess[k]) * np.clip(ratio, 0.2, 5.0))
    print(tag, "shell target", target["shell"].round(1), "got", meas["shell"].round(1), "camo gain" if camo else "", gain.round(3) if camo else "")
    print(tag, "final export", painter("import builtins\nresult = builtins.PB['export']('" + tag + "', 12, True)"))
