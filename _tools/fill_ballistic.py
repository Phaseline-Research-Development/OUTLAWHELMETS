"""Fill the Ballistic shell's own atlas islands in every colour's SF_BCR / SF_NMO (python _tools/fill_ballistic.py).

Only texels listed in ballistic_map.npz (Ballistic-only islands NOT used by any Bump/rails triangle) are written, plus a
4 px bleed into other unused texels; everything the Bump uses stays byte-identical. Originals go to work/tex_backup.
  BCR RGB : the Bump's painted colour at the matching Bump point
  NMO R,G : vendor SF_V2 normal at the texel's own UV (it is laid out for the Ballistic), in the NMO's convention
  NMO B   : the Bump's value at the matching Bump point
"""
import os, shutil
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
A = ROOT + "SFHELMETS/ASSETS/"
WORK = ROOT + "_tools/work/"
VN = "D:/3D Source Library/Headgear/SF_V2/SF_V2/tex/aor1/SF_normal.png"
SETS = {"HELMET AOR1": ("AOR1SF_BCR.tif", "AOR1SF_NMO.tif"), "HELMET BLACK": ("mcbSF_BCR.tif", "mcbSF_NMO.tif"),
        "HELMET GREEN": ("grSF_BCR.tif", "grSF_NMO.tif"), "HELMET MC": ("SF_BCR.tif", "SF_NMO.tif"),
        "HELMET RG": ("RGSF_BCR.tif", "RGSF_NMO.tif"), "HELMET TAN": ("tanSF_BCR.tif", "tanSF_NMO.tif")}

m = np.load(WORK + "ballistic_map.npz")
x, y, uv, used = m["x"], m["y"], m["uv"], m["used"]
P, N, gap, SH, HOLE = m["p"], m["n"], m["gap"], m["shell"], m["hole"]
RES = used.shape[0]

# Ghost-vent removal: the Bump's paint carries the shading around its vent holes. Texels over a vent (vent_mask.py
# ray test) seed a vent zone; inside R_IN the colour comes from a clean donor texel (same helmet, point rotated
# away from the vents), blended back to the direct copy by R_OUT.
from scipy.spatial import cKDTree
R_IN, R_OUT = 0.006, 0.011
print("gap percentiles mm", np.percentile(gap, [50, 90, 99, 99.9]).round(4) * 1000)
seeds = P[HOLE & SH & (P[:, 2] > 0.045)]             # vent_mask.py ray test; z cut drops the bottom rims
dz = cKDTree(seeds).query(P)[0] if len(seeds) else np.full(len(P), 1.0)
clean = (dz > R_OUT) & SH
tree = cKDTree(P[clean]); cuv = uv[clean]; cn = N[clean]
zone = np.where((dz < R_OUT) & SH)[0]
C = np.array([0.0, 0.0, -0.08])


def rot(axis, deg):
    a = np.radians(deg); c, s_ = np.cos(a), np.sin(a)
    if axis == "z":
        return np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
    return np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]])


donor = np.full(len(zone), -1)
for R in [rot("z", a) for a in (35, -35, 70, -70, 110, -110, 150, -150)] + [rot("x", a) for a in (20, -20, 30, -30, 45, -45, 55, -55)]:
    todo = np.where(donor < 0)[0]
    if not len(todo):
        break
    q = (P[zone[todo]] - C) @ R.T + C
    qn = N[zone[todo]] @ R.T
    d, i = tree.query(q)
    ok = (d < 0.008) & (np.einsum("ij,ij->i", cn[i], qn) > 0.6)
    donor[todo[ok]] = i[ok]
todo = np.where(donor < 0)[0]
if len(todo):
    d, i = tree.query(P[zone[todo]])
    donor[todo] = i
w = np.clip((dz[zone] - R_IN) / (R_OUT - R_IN), 0, 1)
has = donor >= 0
print("vent seeds", len(seeds), "zone texels", len(zone), "without donor", int((~has).sum()))

# Velcro panels: nearest-point copy smears the Bump panel's border across the bigger Ballistic panels. Instead tile a
# clean square from the interior of the Bump velcro those panel texels matched, mirror-repeated in atlas space.
from scipy import ndimage
pan = ~SH
hit = np.zeros((RES, RES), bool)
hx = np.clip((uv[pan, 0] * RES).astype(int), 0, RES - 1); hy = np.clip(((1 - uv[pan, 1]) * RES).astype(int), 0, RES - 1)
hit[hy, hx] = True
hit = ndimage.binary_closing(hit, iterations=3)
lab, nl = ndimage.label(hit)
big = np.argmax(ndimage.sum(hit, lab, range(1, nl + 1))) + 1
dist = ndimage.distance_transform_edt(lab == big)
cy, cx = np.unravel_index(np.argmax(dist), dist.shape)
half = int(dist[cy, cx] / 1.5) - 4
TY0, TX0, TS = cy - half, cx - half, 2 * half
print("velcro tile at", (TX0, TY0), "size", TS)


def tile_lookup(img, xs, ys):
    def mirror(v):
        v = v % (2 * TS)
        return np.where(v < TS, v, 2 * TS - 1 - v)
    return img[TY0 + mirror(ys), TX0 + mirror(xs)]


def bilinear(img, uv):
    h, w = img.shape[:2]
    fx = np.clip(uv[:, 0] * w - 0.5, 0, w - 1.001)
    fy = np.clip((1 - uv[:, 1]) * h - 0.5, 0, h - 1.001)
    x0, y0 = fx.astype(int), fy.astype(int)
    ax, ay = (fx - x0)[:, None], (fy - y0)[:, None]
    return ((img[y0, x0] * (1 - ax) + img[y0, x0 + 1] * ax) * (1 - ay)
            + (img[y0 + 1, x0] * (1 - ax) + img[y0 + 1, x0 + 1] * ax) * ay)


def bleed(img, filled, free, n=4):
    img = img.astype(np.float32)
    for _ in range(n):
        acc = np.zeros_like(img); cnt = np.zeros(filled.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sf = np.roll(filled, (dy, dx), (0, 1)); si = np.roll(img, (dy, dx), (0, 1))
            acc += si * sf[..., None]; cnt += sf
        grow = free & ~filled & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
    return img


vn = np.asarray(Image.open(VN).convert("RGB").resize((RES, RES), Image.LANCZOS)).astype(np.float32)
target = np.zeros((RES, RES), bool); target[y, x] = True
free = ~used
os.makedirs(WORK + "tex_backup", exist_ok=True)

for folder, (bcr_n, nmo_n) in SETS.items():
    for n in (bcr_n, nmo_n):
        bk = f"{WORK}tex_backup/{folder}_{n}"
        if not os.path.exists(bk):
            shutil.copyfile(f"{A}{folder}/Data/{n}", bk)
    bcr_src = np.asarray(Image.open(f"{WORK}tex_backup/{folder}_{bcr_n}").convert("RGB")).astype(np.float32)
    nmo_src = np.asarray(Image.open(f"{WORK}tex_backup/{folder}_{nmo_n}").convert("RGB")).astype(np.float32)

    if folder == "HELMET AOR1":
        um = used & ~target
        corr = np.corrcoef(nmo_src[um][:, 1], vn[um][:, 1])[0, 1]
        flip_g = corr < 0
        print("NMO vs vendor normal G correlation on Bump texels %.3f -> flip G: %s" % (corr, flip_g))
    vg = 255 - vn[..., 1] if flip_g else vn[..., 1]

    bcr = bcr_src.copy()
    col = bilinear(bcr_src, uv)
    zc = bilinear(bcr_src, cuv[donor[has]])
    zi = zone[has]
    col[zi] = col[zi] * w[has, None] + zc * (1 - w[has, None])
    col[pan] = tile_lookup(bcr_src, x[pan], y[pan])
    bcr[y, x] = col
    bcr = bleed(bcr, target.copy(), free)
    nmo = nmo_src.copy()
    nmo[y, x, 0] = vn[y, x, 0]
    nmo[y, x, 1] = vg[y, x]
    mb = bilinear(nmo_src, uv)[:, 2]
    mb[zi] = mb[zi] * w[has] + bilinear(nmo_src, cuv[donor[has]])[:, 2] * (1 - w[has])
    mb[pan] = tile_lookup(nmo_src, x[pan], y[pan])[:, 2]
    nmo[y, x, 2] = mb
    nmo = bleed(nmo, target.copy(), free)
    assert np.array_equal(bcr[used].round(), bcr_src[used]) and np.array_equal(nmo[used].round(), nmo_src[used])
    Image.fromarray(np.clip(bcr, 0, 255).round().astype(np.uint8), "RGB").save(f"{A}{folder}/Data/{bcr_n}", compression="tiff_lzw")
    Image.fromarray(np.clip(nmo, 0, 255).round().astype(np.uint8), "RGB").save(f"{A}{folder}/Data/{nmo_n}", compression="tiff_lzw")
    print(folder, "filled", len(x), "texels")
