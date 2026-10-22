"""Normal mesh map = the vendor _nohq, the way the user's MCB HELMET.spp does it (python _tools/set_vendor_normals.py; Painter up).

User 2026-09-30: "why do the rails on the xp look like this ... it looks very flat or very matte". The user's spp uses SF_nohq as
the SF texture set's Normal mesh map (measured: its Normal_DirectX output matches SF_nohq, corr 0.99, so that project reads
_nohq as DirectX). My XP / Maritime projects had a low-as-high baked normal instead = flat, and the SF Ballistic copy lost
SF_nohq to the same bake. The vendor _nohq maps are DirectX (XP_nohq vs the vendor height map: green anti-correlates with
dH/drow); XP / XP4 / Maritime projects are OpenGL, so they get the _nohq with green flipped; the Ballistic project is the
user's own (DirectX) and gets SF_nohq unchanged. XP4M keeps its baked normal (that UV area is the 3-hole frame's in XP_nohq).
"""
import os
import numpy as np
from PIL import Image
import painter_bridge as pb

Image.MAX_IMAGE_PIXELS = None
ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/_tools/work/"
H = "D:/3D Source Library/Headgear/"


def gl(src, dst):
    if not os.path.exists(dst):
        a = np.array(Image.open(src).convert("RGB"))
        a[..., 1] = 255 - a[..., 1]
        Image.fromarray(a).save(dst)
    return dst


JOBS = [
    (ROOT + "xp/painter/XP_texturing.spp", {
        "XP1": gl(H + "OpscoreXP_Carbon/OpscoreXP_Carbon/XP/tex/XP_nohq.png", ROOT + "xp/painter/XP_nohq_gl.png"),
        "Carbon1": gl(H + "OpscoreXP_Carbon/OpscoreXP_Carbon/Carbon/Tex/Carbon_nohq.png", ROOT + "xp/painter/Carbon_nohq_gl.png")}),
    (ROOT + "xp/painter/XP4_texturing.spp", {"XP1": ROOT + "xp/painter/XP_nohq_gl.png"}),
    (ROOT + "maritime/painter/MT_texturing.spp", {
        "MT": gl(H + "OpscoreMaritime/OpscoreMaritime/AOR1/MT_nohq.png", ROOT + "maritime/painter/MT_nohq_gl.png"),
        "KitA": gl(H + "OpscoreMaritime/OpscoreMaritime/KitAVelcro/KitA_nohq.png", ROOT + "maritime/painter/KitA_nohq_gl.png")}),
    (ROOT + "painter/SF_Ballistic_texturing.spp", {"SF": H + "SF_V2/SF_V2/tex/SF_nohq.png"}),
]

for spp, sets in JOBS:
    pb.py("import substance_painter.project as pj\nif pj.is_open(): pj.close()\n"
          f"pj.open(r'{spp}')\nresult = 'ok'")
    pb.wait_ready()
    print(spp.split("/")[-1], pb.py(
        "import substance_painter.resource as rs, substance_painter.textureset as ts, substance_painter.project as pj\n"
        f"out = {{}}\nfor t, f in {sets!r}.items():\n"
        "    r = rs.import_project_resource(f, rs.Usage.TEXTURE)\n"
        "    ts.TextureSet.from_name(t).set_mesh_map_resource(ts.MeshMapUsage.Normal, r.identifier())\n"
        "    out[t] = str(ts.TextureSet.from_name(t).get_mesh_map_resource(ts.MeshMapUsage.Normal).url()).split('?')[0]\n"
        "pj.save(pj.ProjectSaveMode.Full)\nresult = out"))
