"""Ranger Green velcro on the SF Ballistic RG (user 2026-10-09: "the velcro color needs to be changed on the shell").

The RG Ballistic was calibrated to the RG Bump, whose velcro is coyote. This re-tunes ONLY the velcro swatch so the
Bebra_Velcro region renders as the RG shell colour a shade darker (loop velcro reads darker than the shell), keeps every
other RG input (latest RG swatches), exports RG at 2048 (same as installed) and does not save the .spp.

  python _tools/rg_velcro.py            then  python _tools/rg_velcro.py install
"""
import glob, json, os, re, shutil, socket, sys, time
import numpy as np
from PIL import Image

ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
PW = ROOT + "_tools/work/painter/"
SW = PW + "swatches/"
V = "D:/3D Source Library/Headgear/SF_V2/SF_V2/tex/"
REG = np.load(PW + "layer_regions.npz")
VEL, SHELL = REG["09_Bebra_Velcro"], REG["08_Plastic_Grainy_Soft"]
DARKER = 0.88
KEYS = ("velcro", "nylon", "composite", "grain", "rubber")


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
    while painter("import substance_painter.project as pj\nresult = pj.is_busy() or not pj.is_in_edition_state()"):
        time.sleep(2)
    time.sleep(2)


def last(tag, key):
    files = glob.glob(f"{SW}{tag}[0-9]_{key}.png")
    return max(files, key=lambda f: int(re.search(rf"{re.escape(tag)}(\d)_", os.path.basename(f)).group(1)))


def to_lin(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255.0


def means(png):
    a = np.asarray(Image.open(png).convert("RGB").resize((1024, 1024))).astype(float)
    return a[VEL].mean(0), a[SHELL].mean(0)


if len(sys.argv) > 1 and sys.argv[1] == "install":
    bk = ROOT + "_tools/work/tex_backup/"
    for kind in ("BCR", "NMO"):
        dst = f"{ROOT}SFHELMETS/ASSETS/HELMET RG/Data/RGSFBallistic_{kind}.png"
        b = f"{bk}RGSFBallistic_{kind}_before_rg_velcro.png"
        if not os.path.exists(b):
            shutil.copyfile(dst, b)
        shutil.copyfile(f"{PW}export/RG_{kind}.png", dst)
        print("installed", dst, "(backup", b + ")")
    sys.exit(0)

painter(f"import substance_painter.project as pj\nif pj.is_open(): pj.close()\npj.open(r'{PW}SF_Ballistic_texturing.spp')\nresult = 'ok'")
wait()
painter(f"exec(open(r'{ROOT}_tools/painter_ballistic.py').read(), globals())\nimport builtins; builtins.PB = {{k: v for k, v in globals().items()}}\nresult = 'ok'")
sw = {k: last("RG", k) for k in KEYS}
shell = ["swatch", last("RG", "shell")]
it0 = max(int(re.search(r"RG(\d)_", os.path.basename(f)).group(1)) for f in glob.glob(SW + "RG[0-9]_*.png")) + 1
guess = np.asarray(Image.open(sw["velcro"]).convert("RGB"))[0, 0].astype(float)
target = None
for it in range(6):
    p = f"{SW}RG{min(it0 + it, 9)}_velcro.png"
    Image.new("RGB", (32, 32), tuple(int(round(v)) for v in guess)).save(p)
    cfg = {"base": V + "gray/SF_gray.png", "shell": shell, "swatches": dict(sw, velcro=p)}
    painter("import builtins\nPB = builtins.PB\nPB['apply'](" + repr(cfg) + ")\nresult = PB['export']('cal_RG', 10, False)")
    vel, sh = means(PW + "export/cal_RG_BCR.png")
    if target is None:
        target = sh * DARKER
    err = float(np.abs(vel - target).mean())
    print("iter", it, "velcro", vel.round(1), "target", target.round(1), "shell", sh.round(1), "err", round(err, 2), os.path.basename(p))
    if err < 1.2:
        break
    ratio = (to_lin(target) + 1e-4) / (to_lin(vel) + 1e-4)
    guess = to_srgb(to_lin(guess) * np.clip(ratio, 0.2, 5.0))
print("final export", painter("import builtins\nresult = builtins.PB['export']('RG', 11, True)"))
vel, sh = means(PW + "export/RG_BCR.png")
print("RG_BCR 2048: velcro", vel.round(1), "shell", sh.round(1))
