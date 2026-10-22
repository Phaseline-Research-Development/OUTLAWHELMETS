"""Create the XP / XP Carbon Painter project with the user's MCB HELMET.spp stack (python _tools/xp_painter_setup.py; Painter up).

Texture sets XP1 (XP shell/rails/harness), Carbon1 (carbon shell), XP4M (4-hole mount plate), 4096. The user's stack comes from
their smart material "Folder 1"; base layers point at the XP / Carbon vendor maps (XP AO = green of XP_as.png); masks from
xp_masks.py (XP4M is hardware = Plastic Composite everywhere). Bakes run one texture set at a time and finish before anything
else is sent (painter_bridge.bake). Saves _tools/work/xp/painter/XP_texturing.spp and uids.json.
"""
import json, time
import painter_bridge as pb

ROOT = "C:/Users/lebea/Documents/Github/OUTLAWHELMETS/"
PD = ROOT + "_tools/work/xp/painter/"
X = "D:/3D Source Library/Headgear/OpscoreXP_Carbon/OpscoreXP_Carbon/"
SETS = {
    "XP1": (("xp_low_XP_BaseColor", "xp_low_XP_Roughness", "xp_low_XP_Metallic", "XP_ao"),
            {"Bebra_Velcro": None, "Plastic Grainy Soft": "XP1_shell", "Nylon Webbing": "XP1_nylon", "Plastic Base Grain": "XP1_grain",
             "Plastic Composite": "XP1_composite", "Rubber Raw": "XP1_rubber"}),
    "Carbon1": (("Carbon_baseColor", "Carbon_roughness", "Carbon_metallic", "Carbon_occlusion"),
                {"Bebra_Velcro": None, "Plastic Grainy Soft": "Carbon1_shell", "Nylon Webbing": "Carbon1_nylon", "Plastic Base Grain": "Carbon1_grain",
                 "Plastic Composite": "Carbon1_composite", "Rubber Raw": "Carbon1_rubber"}),
    "XP4M": (("xp_low_XP_BaseColor", "xp_low_XP_Roughness", "xp_low_XP_Metallic", "XP_ao"),
             {"Bebra_Velcro": None, "Plastic Grainy Soft": None, "Nylon Webbing": None, "Plastic Base Grain": None,
              "Plastic Composite": "WHITE", "Rubber Raw": None}),
}
FILES = [X + "XP/pbr/xp_low_XP_BaseColor.png", X + "XP/Tan/pbr/xp_tan_XP_BaseColor.png", X + "XP/pbr/xp_low_XP_Roughness.png",
         X + "XP/pbr/xp_low_XP_Metallic.png", PD + "XP_ao.png", X + "Carbon/PBR/Carbon_baseColor.jpg", X + "Carbon/PBR/Carbon_roughness.jpg",
         X + "Carbon/PBR/Carbon_metallic.jpg", X + "Carbon/PBR/Carbon_occlusion.jpg"]
FILES += [PD + f"masks/{t}_{c}.png" for t in ("XP1", "Carbon1") for c in ("shell", "composite", "nylon", "grain", "rubber")]

WIRE = r'''
import substance_painter.layerstack as ls, substance_painter.textureset as ts, substance_painter.resource as rs
def proj_res(name):
    for r in rs.search(name):
        i = r.identifier()
        if i.context.startswith("project") and i.name == name:
            return i
    raise RuntimeError("no project resource " + name)
BC, RG, MT = ts.ChannelType.BaseColor, ts.ChannelType.SpecularRoughness, ts.ChannelType.BaseMetalness
stack = ts.Stack.from_name(TS)
grp = [n for n in ls.get_root_layer_nodes(stack) if n.get_name() == "MCB stack"][0]
nodes = {}
def walk(ns):
    for n in ns:
        nodes.setdefault(n.get_name(), n)
        try: walk(n.sub_layers())
        except Exception: pass
walk([grp])
nodes["SF_mc"].set_source(BC, proj_res(BASES[0]))
nodes["SF_roughness"].set_source(RG, proj_res(BASES[1]))
nodes["SF_metallic"].set_source(MT, proj_res(BASES[2]))
nodes["AO"].set_source(BC, proj_res(BASES[3]))
for nm in ("AO", "Curvalture"):
    nodes[nm].remove_mask(); nodes[nm].add_mask(ls.MaskBackground.White)
for nm, m in MASKS.items():
    n = nodes[nm]
    n.remove_mask()
    n.add_mask(ls.MaskBackground.White if m == "WHITE" else ls.MaskBackground.Black)
    if m and m != "WHITE":
        fx = ls.insert_fill(ls.InsertPosition.inside_node(n, ls.NodeStack.Mask))
        fx.set_name("XP " + m); fx.set_source(None, proj_res(m))
uids = {"base": nodes["SF_mc"].uid(), "shell_base": nodes["Base"].uid(), "rubber": nodes["Rubber Raw"].uid(), "grain": nodes["Plastic Base Grain"].uid()}
for n in nodes["Bebra_Velcro"].sub_layers():
    try:
        if type(n.get_source(BC)).__name__ == "SourceUniformColor": uids["velcro"] = n.uid()
    except Exception: pass
for k, e in (("shell_fill", nodes["Base"]), ("nylon_fill", nodes["Nylon Webbing"]), ("composite_fill", nodes["Plastic Composite"])):
    uids[k] = [x.uid() for x in e.content_effects() if x.get_name() == "Fill"][0]
result = uids
'''
INSERT = r'''
import substance_painter.layerstack as ls, substance_painter.textureset as ts, substance_painter.resource as rs
sm = [r for r in rs.search("Folder 1") if str(r.type()) == "Type.SMART_MATERIAL" and r.identifier().name == "Folder 1"][0]
stack = ts.Stack.from_name(TS)
for n in ls.get_root_layer_nodes(stack):
    if n.get_name() == "Layer 1":
        ls.delete_node(n)
g = ls.insert_smart_material(ls.InsertPosition.from_textureset_stack(stack), sm.identifier())
g.set_name("MCB stack")
result = "ok"
'''
SAVE = "import substance_painter.project as pj\npj.save(pj.ProjectSaveMode.Full)\nresult = 'saved'"

pb.py("import substance_painter.project as pj\nif pj.is_open(): pj.save(pj.ProjectSaveMode.Full); pj.close()\n"
      f"pj.create(r'{PD}xp_painter.fbx', settings=pj.Settings(default_texture_resolution=4096, normal_map_format=pj.NormalMapFormat.OpenGL))\nresult = 'ok'")
pb.wait_ready()
print(pb.py("import substance_painter.resource as rs, substance_painter.project as pj, substance_painter.textureset as ts\n"
            f"for f in {FILES!r}: rs.import_project_resource(f, rs.Usage.TEXTURE)\n"
            f"pj.save_as(r'{PD}XP_texturing.spp', pj.ProjectSaveMode.Full)\nresult = [t.name() for t in ts.all_texture_sets()]"))
for t in SETS:
    print(t, "baked in %.0fs" % pb.bake(t))
print(pb.py(SAVE))
uids = {}
for t, (bases, masks) in SETS.items():
    pb.py(f"TS = {t!r}\n" + INSERT)
    uids[t] = pb.py(f"TS = {t!r}\nBASES = {bases!r}\nMASKS = {masks!r}\n" + WIRE)
    print(t, "wired", uids[t], pb.py(SAVE))
json.dump(uids, open(PD + "uids.json", "w"), indent=1)
