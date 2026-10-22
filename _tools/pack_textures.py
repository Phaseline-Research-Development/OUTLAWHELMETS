"""Pack vendor PBR maps into Enfusion BCR / NMO PNGs for the attachments that had no textures in OUTLAW yet.

  BCR: RGB base colour, A roughness      NMO: RG DirectX normal, B metalness, A AO
Normal handedness from Shadows-Helmets/_tools/normal_handedness.py (curl test): Comtac VI = OpenGL (flip G),
AMP / counterweight DirectX files, BNVD _nohq = DirectX.
"""
import os
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
A = "D:/3D Source Library/Headgear/New folder/"
CARS = "C:/Users/lebea/OneDrive/Desktop/Cars/"
OUT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/SFHELMETS/ASSETS/Helmet Accessories/"
RES = 2048

_AMP = A + "EarPro_AMPS/EarPro_AMPS/Textures/PBR_OpsCore_AMP_Headset_tx/EarPro_OpsCore_AMPS_"
_C6 = A + "EarPro_Comtac_VI/EarPro_Comtac_VI/Textures/PBR_Comtac_VI_tx/Comtac_6_"
_CW = CARS + "Helmet_CRYE_Airframe_v03/Helmet_CRYE_Airframe_v03/Textures/PBR_NVG_Counterweight_OpsCore_Kit_tx/NVG_Counterweight_OpsCore_Kit_Coyote_"
_BN = A + "BNVDFBatteryPack/BNVDFBatteryPack/"

SETS = {
    "AMP/Data/OpsCore_AMP": dict(base=_AMP + "BaseColor.png", rough=_AMP + "Roughness.png", metal=_AMP + "Metalness.png",
                                 ao=_AMP + "AO.png", normal=_AMP + "DirectX_Normal.png", flip_g=False),
    "COMTACS/COMTAC VI/Data/Comtac6": dict(base=_C6 + "BaseColor.png", rough=_C6 + "Roughness.png", metal=_C6 + "Metalness.png",
                                           ao=_C6 + "AO.png", normal=_C6 + "Normal.png", flip_g=True),
    "COUNTERWEIGHT/Data/OpsCoreCounterweight_Coyote": dict(base=_CW + "BaseColor.png", rough=_CW + "Roughness.png",
                                                           metal=_CW + "Metalness.png", ao=_CW + "AO.png",
                                                           normal=_CW + "DirectX_Normal.png", flip_g=False),
    "BNVD BATTERY/Data/BNVDFBat": dict(base=_BN + "Tex/BNVDFBat_co.png", rough=_BN + "PBR/BNVDFBat_roughness.jpg",
                                       metal=_BN + "PBR/BNVDFBat_metallic.jpg", ao=_BN + "PBR/BNVDFBat_occlusion.jpg",
                                       normal=_BN + "Tex/BNVDFBat_nohq.png", flip_g=False),
}


def load(path, mode):
    if not os.path.exists(path):
        path = path.replace(A, "C:/Users/lebea/Documents/Github/Shadows-Helmets/Source/")
    im = Image.open(path)
    im = im.convert("RGB").convert("L") if mode == "L" else im.convert(mode)
    if im.size != (RES, RES):
        im = im.resize((RES, RES), Image.LANCZOS)
    return np.asarray(im)


for stem, s in SETS.items():
    os.makedirs(os.path.dirname(OUT + stem), exist_ok=True)
    base = load(s["base"], "RGB")
    rough = load(s["rough"], "L")
    metal = load(s["metal"], "L")
    ao = load(s["ao"], "L")
    n = load(s["normal"], "RGB").copy()
    if s["flip_g"]:
        n[..., 1] = 255 - n[..., 1]
    Image.fromarray(np.dstack([base, rough]).astype(np.uint8), "RGBA").save(OUT + stem + "_BCR.png")
    Image.fromarray(np.dstack([n[..., 0], n[..., 1], metal, ao]).astype(np.uint8), "RGBA").save(OUT + stem + "_NMO.png")
    print(stem, "base", base.reshape(-1, 3).mean(0).round(1), "rough %.1f metal %.1f ao %.1f" % (rough.mean(), metal.mean(), ao.mean()))
