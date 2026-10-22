"""Create the Maritime Painter project with the user's MCB HELMET.spp stack (python _tools/maritime_painter_setup.py; Painter running).

Texture sets MT (shell/rails/harness) and KitA (loop panels), 4096. Imports the Maritime's own vendor textures, bakes mesh maps,
inserts the user's stack from their smart material "Folder 1" (made from MCB HELMET.spp) into BOTH stacks, points the base
layers at the Maritime sources, rebuilds the masks (MT: maritime_masks.py PNGs; KitA: velcro everywhere) and saves
_tools/work/maritime/painter/MT_texturing.spp.
"""
import json, socket, time

ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
PD = ROOT + "_tools/work/maritime/painter/"
S = "D:/3D Source Library/Headgear/OpscoreMaritime/OpscoreMaritime/"


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


def wait_busy():
    time.sleep(2)
    while painter("import substance_painter.project as pj\nresult = pj.is_busy()"):
        time.sleep(2)
    time.sleep(2)


def wait_bake():
    time.sleep(3)
    while True:
        s = socket.create_connection(("127.0.0.1", 60043), timeout=60)
        s.sendall((json.dumps({"id": 1, "op": "baking.status", "params": {}}) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            buf += s.recv(65536)
        r = json.loads(buf.split(b"\n")[0])["result"]
        if not r["running"]:
            return r
        time.sleep(5)


painter("import substance_painter.project as pj\nif pj.is_open(): pj.close()\n"
        f"pj.create(r'{PD}mt_painter.fbx', settings=pj.Settings(default_texture_resolution=4096, normal_map_format=pj.NormalMapFormat.OpenGL))\nresult='ok'")
wait_busy()
files = [S + "AOR1/MT_aor1.png", S + "MC/MT_mc.png", S + "PBR/MT_roughness.jpg", S + "PBR/MT_metallic.jpg", S + "PBR/MT_occlusion.jpg",
         S + "KitAVelcro/KitA_co.png", S + "KitAVelcro/KitA_roughness.jpg", S + "KitAVelcro/KitA_metallic.jpg", S + "KitAVelcro/KitA_occlusion.jpg"]
files += [PD + f"masks/mt_{c}.png" for c in ("shell", "composite", "nylon", "grain", "rubber")]
print(painter("import substance_painter.resource as rs, substance_painter.project as pj, substance_painter.baking as bk, substance_painter.textureset as ts\n"
              f"for f in {files!r}: rs.import_project_resource(f, rs.Usage.TEXTURE)\n"
              f"pj.save_as(r'{PD}MT_texturing.spp', pj.ProjectSaveMode.Full)\n"
              "names = [t.name() for t in ts.all_texture_sets()]\n"
              "for n in names:\n"
              "    bp = bk.BakingParameters.from_texture_set_name(n); c = bp.common(); a = bp.baker(bk.MeshMapUsage.AO)\n"
              "    bk.BakingParameters.set({c['LowAsHigh']: True, c['OutputSize']: (12, 12), a['IgnoreBackfaceSecondary']: 2})\n"
              "    bp.set_enabled_bakers([bk.MeshMapUsage.Normal, bk.MeshMapUsage.WorldSpaceNormal, bk.MeshMapUsage.AO, bk.MeshMapUsage.Curvature, bk.MeshMapUsage.Position, bk.MeshMapUsage.Thickness])\n"
              "result = names"))
for tsname in ("MT", "KitA"):
    painter(f"import substance_painter.baking as bk, substance_painter.textureset as ts\nbk.bake_async(ts.TextureSet.from_name('{tsname}'))\nresult = 'ok'")
    print("bake", tsname, wait_bake())

SETUP = r'''
import substance_painter.layerstack as ls, substance_painter.textureset as ts, substance_painter.resource as rs, substance_painter.project as pj
def proj_res(name):
    for r in rs.search(name):
        i = r.identifier()
        if i.context.startswith("project") and i.name == name:
            return i
    raise RuntimeError("no project resource " + name)
sm = [r for r in rs.search("Folder 1") if str(r.type()) == "Type.SMART_MATERIAL" and r.identifier().name == "Folder 1"][0]
BC, RG, MT = ts.ChannelType.BaseColor, ts.ChannelType.SpecularRoughness, ts.ChannelType.BaseMetalness
out = {}
for tsname, bases, masks in (
        ("MT", ("MT_aor1", "MT_roughness", "MT_metallic", "MT_occlusion"),
         {"Bebra_Velcro": None, "Plastic Grainy Soft": "mt_shell", "Nylon Webbing": "mt_nylon", "Plastic Base Grain": "mt_grain",
          "Plastic Composite": "mt_composite", "Rubber Raw": "mt_rubber"}),
        ("KitA", ("KitA_co", "KitA_roughness", "KitA_metallic", "KitA_occlusion"),
         {"Bebra_Velcro": "WHITE", "Plastic Grainy Soft": None, "Nylon Webbing": None, "Plastic Base Grain": None,
          "Plastic Composite": None, "Rubber Raw": None})):
    stack = ts.Stack.from_name(tsname)
    for n in ls.get_root_layer_nodes(stack):
        if n.get_name() == "Layer 1":
            ls.delete_node(n)
    grp = ls.insert_smart_material(ls.InsertPosition.from_textureset_stack(stack), sm.identifier())
    grp.set_name("MCB stack")
    nodes = {}
    def walk(ns):
        for n in ns:
            nodes.setdefault(n.get_name(), n)
            try: walk(n.sub_layers())
            except Exception: pass
    walk([grp])
    nodes["SF_mc"].set_source(BC, proj_res(bases[0]))
    nodes["SF_roughness"].set_source(RG, proj_res(bases[1]))
    nodes["SF_metallic"].set_source(MT, proj_res(bases[2]))
    nodes["AO"].set_source(BC, proj_res(bases[3]))
    for nm in ("AO", "Curvalture"):
        nodes[nm].remove_mask(); nodes[nm].add_mask(ls.MaskBackground.White)
    for nm, m in masks.items():
        n = nodes[nm]
        n.remove_mask()
        n.add_mask(ls.MaskBackground.White if m == "WHITE" else ls.MaskBackground.Black)
        if m and m != "WHITE":
            fx = ls.insert_fill(ls.InsertPosition.inside_node(n, ls.NodeStack.Mask))
            fx.set_name("Maritime " + m); fx.set_source(None, proj_res(m))
    uids = {"base": nodes["SF_mc"].uid(), "shell_base": nodes["Base"].uid(), "velcro": None, "rubber": nodes["Rubber Raw"].uid(),
            "grain": nodes["Plastic Base Grain"].uid()}
    for n in nodes["Bebra_Velcro"].sub_layers():
        try:
            if type(n.get_source(BC)).__name__ == "SourceUniformColor": uids["velcro"] = n.uid()
        except Exception: pass
    for k, e in (("shell_fill", nodes["Base"]), ("nylon_fill", nodes["Nylon Webbing"]), ("composite_fill", nodes["Plastic Composite"])):
        uids[k] = [x.uid() for x in e.content_effects() if x.get_name() == "Fill"][0]
    out[tsname] = uids
pj.save(pj.ProjectSaveMode.Full)
result = out
'''
uids = painter(SETUP)
json.dump(uids, open(PD + "uids.json", "w"), indent=1)
print("uids", uids)
