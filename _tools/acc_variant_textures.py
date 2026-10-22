"""Colour variants for the helmet attachments (python _tools/acc_variant_textures.py). User 2026-09-30: "i need variants of the
counter weights, AMPs, BRS, Comtacs"; AMP -> "Recolour to Black + RG", counterweight -> "Recolour Ops-Core pouch".

- PVS-31 BRS Coyote / OD and Comtac VII Grey / Green: the VENDOR colourways (same UV layout as the shipped textures), packed
  like pack_textures.py: BCR = base + roughness (A), NMO = DirectX normal (RG) + metalness (B) + AO (A). The BRS OD / Coyote
  sets ship only a BaseColor, so they take the MC set's roughness / metal / AO / normal (the OUTLAW BRS NMO = that normal).
- Ops-Core AMP Black / RG: only the painted tan housing is recoloured (HSV mask), keeping its own shading
  (colour = target * L / median L); cables, metal, rubber, cushions, alpha (roughness) and NMO stay vendor.
- Ops-Core counterweight MC / RG / Black: only the coyote fabric pouch is recoloured (GRS gear method: detail = L / blur(L),
  flattened to 0.72-1.35; MC = the graded OUTLAW helmet MultiCam tiled at the helmet's real-world scale, repeats from
  acc_texel_density.py); black hardware, alpha and NMO stay vendor.
MC camo goes on the fabric pouch only (connected fabric regions > 2 % of the map); the small tan plastic hooks / cord ends
stay coyote on MC and follow the colour on RG / Black. RG = the finished RG helmet texture (shell colour for the AMP housing,
nylon for the pouch), Black = (28, 28, 30) (GRS gear black). Writes _tools/work/acc_variants/tex/ + check sheets.
"""
import json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

Image.MAX_IMAGE_PIXELS = None
T = os.path.dirname(os.path.abspath(__file__))
ACC = os.path.join(T, "..", "SFHELMETS", "ASSETS", "Helmet Accessories") + "/"
W = os.path.join(T, "work", "acc_variants") + "/"
OUT = W + "tex/"
SW = os.path.join(T, "work", "painter", "swatches") + "/"
H = "D:/3D Source Library/Headgear/"
RES = 2048
os.makedirs(OUT, exist_ok=True)
BLACK = np.array([28, 28, 30], float)


def swatch(name):
    return np.asarray(Image.open(SW + name + ".png").convert("RGB"), float).reshape(-1, 3).mean(0)


def rendered(code, cls):
    """Median colour of a material class on the FINISHED helmet texture (the Painter stack darkens the raw swatch)."""
    b = np.asarray(Image.open(os.path.join(T, "..", "SFHELMETS", "ASSETS", "XP", f"XP {code}", "Data", f"{code}XP_XP1_BCR.png"))
                   .convert("RGB").resize((1024, 1024)), float)
    m = np.asarray(Image.open(os.path.join(T, "work", "xp", "painter", "masks", f"XP1_{cls}.png")).convert("L").resize((1024, 1024))) > 128
    return np.median(b[m], 0)


RG_FABRIC = rendered("RG", "nylon")
RG_HARD = rendered("RG", "shell")


def load(path, mode):
    im = Image.open(path)
    im = im.convert("RGB").convert("L") if mode == "L" else im.convert(mode)
    if im.size != (RES, RES):
        im = im.resize((RES, RES), Image.LANCZOS)
    return np.asarray(im)


def pack(stem, base, rough, metal, ao, normal):
    Image.fromarray(np.dstack([base, rough]).astype(np.uint8), "RGBA").save(OUT + stem + "_BCR.png")
    Image.fromarray(np.dstack([normal[..., 0], normal[..., 1], metal, ao]).astype(np.uint8), "RGBA").save(OUT + stem + "_NMO.png")


def lum(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def hsv_mask(rgb, hue=(15, 55), sat=(0.12, 0.85), val=0.12):
    f = rgb / 255.0
    mx, mn = f.max(2), f.min(2)
    s = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    m = (h >= hue[0]) & (h <= hue[1]) & (s >= sat[0]) & (s <= sat[1]) & (mx >= val)
    im = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.5))
    return np.asarray(im, float) / 255


def blur(a, r):
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(a.astype(float), r)


def tiled(img, repeats):
    src = Image.open(img).convert("RGB")
    size = max(8, int(RES / repeats))
    t = src.resize((size, int(size * src.height / src.width)), Image.LANCZOS)
    out = Image.new("RGB", (RES, RES))
    for y in range(0, RES, t.height):
        for x in range(0, RES, t.width):
            out.paste(t, (x, y))
    return np.asarray(out, float)


report = {}
# ------------------------------------------------ vendor colourways
BR = H + "NVG_PVS31_BRS/NVG_PVS31_BRS/Textures/"
mc = BR + "PBR_PVS31_BRS_MC_tx/PVS31_BRS_MC_"
for col in ("Coyote", "OD"):
    pack(f"PVS31_BRS_{col}", load(BR + f"PBR_PVS31_BRS_{col}_tx/PVS31_BRS_{col}_BaseColor.png", "RGB"), load(mc + "Roughness.png", "L"),
         load(mc + "Metalness.png", "L"), load(mc + "AO.png", "L"), load(mc + "Normal.png", "RGB"))
    report[f"BRS {col}"] = "vendor"
C7 = H + "EarPro_Comtac_VII/EarPro_Comtac_VII/Textures/PBR_PeltorComtac_VII_tx/PeltorComtac_7_"
for col in ("Grey", "Green"):
    pack(f"PeltorComtac_VII_{col}", load(C7 + f"{col}_BaseColor.png", "RGB"), load(C7 + "Roughness.png", "L"), load(C7 + "Metalness.png", "L"),
         load(C7 + "AO.png", "L"), load(C7 + "DirectX_Normal.png", "RGB"))
    report[f"Comtac VII {col}"] = "vendor"

# ------------------------------------------------ AMP housing recolour
amp = np.asarray(Image.open(ACC + "AMP/Data/OpsCore_AMP_BCR.png").convert("RGBA"), float)
m_amp = hsv_mask(amp[..., :3])
L = lum(amp[..., :3]); Lref = np.median(L[m_amp > 0.5])
detail = np.clip(L / Lref, 0.5, 1.7)[..., None]
for col, target in (("Black", BLACK), ("RG", RG_HARD)):
    rgb = amp[..., :3] * (1 - m_amp[..., None]) + np.clip(target * detail, 0, 255) * m_amp[..., None]
    Image.fromarray(np.dstack([rgb, amp[..., 3]]).astype(np.uint8), "RGBA").save(OUT + f"OpsCore_AMP_{col}_BCR.png")
    report[f"AMP {col}"] = {"target": target.round(1).tolist(), "masked_frac": round(float((m_amp > 0.5).mean()), 3)}
shutil_src_nmo = ACC + "AMP/Data/OpsCore_AMP_NMO.png"

# ------------------------------------------------ counterweight pouch recolour
cw = np.asarray(Image.open(ACC + "COUNTERWEIGHT/Data/OpsCoreCounterweight_Coyote_BCR.png").convert("RGBA"), float)
m_cw = hsv_mask(cw[..., :3], hue=(15, 60), sat=(0.15, 0.9), val=0.15)
Lc = lum(cw[..., :3])
fab = np.clip(Lc / np.maximum(blur(Lc, 40), 1), 0.72, 1.35)[..., None]
dens = json.load(open(W + "density.json"))
camo = tiled(SW + "MC1_camo.png", dens["counterweight_camo_repeats"])
from scipy.ndimage import label
lab, n = label(m_cw > 0.5)
sizes = np.bincount(lab.ravel()); sizes[0] = 0
pouch = np.isin(lab, np.where(sizes > 0.02 * RES * RES)[0])
m_pouch = np.clip(blur(pouch.astype(float), 1.5), 0, 1) * m_cw
for col, fill, m in (("MC", camo, m_pouch), ("RG", np.broadcast_to(RG_FABRIC, cw[..., :3].shape), m_cw),
                     ("Black", np.broadcast_to(BLACK, cw[..., :3].shape), m_cw)):
    rgb = cw[..., :3] * (1 - m[..., None]) + np.clip(fill * fab, 0, 255) * m[..., None]
    Image.fromarray(np.dstack([rgb, cw[..., 3]]).astype(np.uint8), "RGBA").save(OUT + f"OpsCoreCounterweight_{col}_BCR.png")
    report[f"Counterweight {col}"] = {"masked_frac": round(float((m_cw > 0.5).mean()), 3)}
report["camo_repeats"] = dens["counterweight_camo_repeats"]
report["RG_fabric"] = RG_FABRIC.round(1).tolist(); report["RG_hard"] = RG_HARD.round(1).tolist()
json.dump(report, open(W + "textures.json", "w"), indent=1)

# ------------------------------------------------ check sheets
tiles = [("AMP vendor", ACC + "AMP/Data/OpsCore_AMP_BCR.png"), ("AMP mask", m_amp), ("AMP Black", OUT + "OpsCore_AMP_Black_BCR.png"),
         ("AMP RG", OUT + "OpsCore_AMP_RG_BCR.png"), ("CW vendor", ACC + "COUNTERWEIGHT/Data/OpsCoreCounterweight_Coyote_BCR.png"),
         ("CW mask", m_cw), ("CW MC", OUT + "OpsCoreCounterweight_MC_BCR.png"), ("CW RG", OUT + "OpsCoreCounterweight_RG_BCR.png"),
         ("CW Black", OUT + "OpsCoreCounterweight_Black_BCR.png"), ("BRS Coyote", OUT + "PVS31_BRS_Coyote_BCR.png"),
         ("BRS OD", OUT + "PVS31_BRS_OD_BCR.png"), ("C7 Grey", OUT + "PeltorComtac_VII_Grey_BCR.png"), ("C7 Green", OUT + "PeltorComtac_VII_Green_BCR.png")]
sheet = Image.new("RGB", (5 * 400, 3 * 400), "white")
for i, (n, src) in enumerate(tiles):
    im = Image.fromarray((src * 255).astype(np.uint8)).convert("RGB") if isinstance(src, np.ndarray) else Image.open(src).convert("RGB")
    im = im.resize((400, 400)); ImageDraw.Draw(im).text((4, 4), n, fill=(255, 0, 0))
    sheet.paste(im, ((i % 5) * 400, (i // 5) * 400))
sheet.save(W + "check_textures.png")
for n, src, box in (("amp_zoom", ["AMP/Data/OpsCore_AMP_BCR.png", "OpsCore_AMP_Black_BCR.png", "OpsCore_AMP_RG_BCR.png"], (0, 1300, 800, 2048)),
                    ("cw_zoom", ["COUNTERWEIGHT/Data/OpsCoreCounterweight_Coyote_BCR.png", "OpsCoreCounterweight_MC_BCR.png", "OpsCoreCounterweight_RG_BCR.png", "OpsCoreCounterweight_Black_BCR.png"], (0, 400, 1100, 1250))):
    ims = [Image.open((ACC if "/" in s else OUT) + s).convert("RGB").crop(box) for s in src]
    w, h = ims[0].size; sc = 480 / w
    z = Image.new("RGB", (int(w * sc) * len(ims), int(h * sc)))
    for i, im in enumerate(ims):
        z.paste(im.resize((int(w * sc), int(h * sc))), (i * int(w * sc), 0))
    z.save(W + f"check_{n}.png")
print(json.dumps(report, indent=1))
