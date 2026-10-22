"""SF Ballistic RG: black NVG shroud (user 2026-10-09: "the nvg mount on the shell needs to be black").

Runs after rg_velcro.py (its RG velcro swatch is the latest RG swatch, picked up here). Opens SF_Ballistic_texturing.spp,
applies the RG inputs, adds a TEMPORARY BaseColor-only fill on top of the SF stack masked by mask_ballistic_shroud.png
(shroud + its anchors/screws/bungees, UV islands picked by ray visibility around the NVG seat on the Ballistic mesh), tunes
its swatch until the shroud region renders like the MCB Ballistic's shroud, exports RG at 2048 and deletes the layer.
The .spp is never saved, so the other colourways are untouched.

  python _tools/rg_shroud_black.py          then   python _tools/rg_velcro.py install
"""
import glob, json, os, re, socket, time
import numpy as np
from PIL import Image

ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
PW = ROOT + "_tools/work/painter/"
SW = PW + "swatches/"
V = "D:/3D Source Library/Headgear/SF_V2/SF_V2/tex/"
exec(open(ROOT + "_tools/rg_velcro.py").read().split("if len(sys.argv)")[0])
REG = np.load(PW + "shroud_region_1024.npy")
VEL = np.load(PW + "layer_regions.npz")["09_Bebra_Velcro"]


def mean(png, region):
    a = np.asarray(Image.open(png).convert("RGB").resize((1024, 1024))).astype(float)
    return a[region].mean(0)


mcb = mean(ROOT + "SFHELMETS/ASSETS/HELMET BLACK/Data/mcbSFBallistic_BCR.png", REG)
painter(f"import substance_painter.project as pj\nif pj.is_open(): pj.close()\npj.open(r'{PW}SF_Ballistic_texturing.spp')\nresult = 'ok'")
wait()
painter(f"exec(open(r'{ROOT}_tools/painter_ballistic.py').read(), globals())\nimport builtins; builtins.PB = {{k: v for k, v in globals().items()}}\nresult = 'ok'")
sw = {k: last("RG", k) for k in KEYS}
cfg = {"base": V + "gray/SF_gray.png", "shell": ["swatch", last("RG", "shell")], "swatches": sw}
painter("import builtins\nPB = builtins.PB\nPB['apply'](" + repr(cfg) + ")\nresult = 'ok'")
uid = painter(f"""import substance_painter.layerstack as ls, substance_painter.textureset as ts, substance_painter.resource as rs
st = ts.TextureSet.from_name('SF').get_stack()
f = ls.insert_fill(ls.InsertPosition.from_textureset_stack(st))
f.set_name('TEMP RG black shroud')
f.active_channels = {{ts.ChannelType.BaseColor}}
f.add_mask(ls.MaskBackground.Black)
m = ls.insert_fill(ls.InsertPosition.inside_node(f, ls.NodeStack.Mask))
m.set_source(None, rs.import_project_resource(r'{PW}mask_ballistic_shroud.png', rs.Usage.TEXTURE).identifier())
result = f.uid()""")
guess = mcb.copy()
for it in range(6):
    p = f"{SW}RGshroud{it}.png"
    Image.new("RGB", (32, 32), tuple(int(round(v)) for v in guess)).save(p)
    painter(f"""import substance_painter.layerstack as ls, substance_painter.textureset as ts, substance_painter.resource as rs
ls.get_node_by_uid({uid}).set_source(ts.ChannelType.BaseColor, rs.import_project_resource(r'{p}', rs.Usage.TEXTURE).identifier())
import builtins
result = builtins.PB['export']('cal_RG', 10, False)""")
    got = mean(PW + "export/cal_RG_BCR.png", REG)
    err = float(np.abs(got - mcb).mean())
    print("iter", it, "shroud", got.round(1), "target (MCB shroud)", mcb.round(1), "err", round(err, 2))
    if err < 1.0:
        break
    ratio = (to_lin(mcb) + 1e-4) / (to_lin(got) + 1e-4)
    guess = to_srgb(to_lin(guess) * np.clip(ratio, 0.2, 5.0))
print("final export", painter("import builtins\nresult = builtins.PB['export']('RG', 11, True)"))
print("RG_BCR 2048: shroud", mean(PW + "export/RG_BCR.png", REG).round(1), "velcro", mean(PW + "export/RG_BCR.png", VEL).round(1))
painter(f"import substance_painter.layerstack as ls\nls.delete_node(ls.get_node_by_uid({uid}))\nresult = 'temp layer removed (spp not saved)'")
