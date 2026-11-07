"""Phaseline ear-pro: generate the Enfusion side of the clip set from build/anim (one source of truth).

  python gen_earpro_assets.py txa        copy TXAs into the snapshot (prints the new ones to register)
  python gen_earpro_assets.py meta       set SourceProfile in every .anm.meta (then move .anm aside + rebuild the TXA)
  python gen_earpro_assets.py graph      write PLHM_EarPro.ast / PLHM_EarPro_RaiseL.asi / PLHM_EarPro.agf
  python gen_earpro_assets.py proxies    write the hand proxy prefabs (prints the new ones to register)
  python gen_earpro_assets.py enforce    write Scripts/Game/EarPro/PLHM_EarProClips.c (needs proxy + anm GUIDs)

Clip ids are stable (replicated): never reorder CLIPS, only append.
"""
import os, sys, json, re, shutil

BUILD = r"C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\_earpro\build\anim"
ADDON = r"C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\SFHELMETS"
TXA_DIR = os.path.join(ADDON, "anims", "EarPro", "txa")
WS = os.path.join(ADDON, "anims", "EarPro", "workspaces")
HANDS = os.path.join(ADDON, "Prefabs", "EarPro", "Hands")
SCRIPT = os.path.join(ADDON, "Scripts", "Game", "EarPro", "PLHM_EarProClips.c")

RAISE, LOWER, VENT, UNVENT = 1, 2, 3, 4
L, R, B = 1, 2, 3
ACT = {"raise": RAISE, "lower": LOWER, "vent": VENT, "unvent": UNVENT}
# Clip sets = placement families (each with its own pivots / grip points); set 0 keeps the original AMP names.
# id, set, file stem, anim name, action, mask, armed (True = left hand only, rifle lowered), profile
FAMILIES = [("amp", ""), ("ampxp", "AmpXp"), ("ctns", "CtNs"), ("ctnsxp", "CtNsXp"), ("ctvi", "CtVi"), ("ctvixp", "CtViXp")]
CLIPS = []
# Tyler 2026-11-06: no left hand reaching over for the right cup; with a weapon in hand it is slung first
_order = [("L", L, None), ("R", R, False), ("B", B, False)]
for set_id, (fam, pre) in enumerate(FAMILIES):
    for sfx, mask, armed in _order:
        for a in ("raise", "lower", "vent", "unvent"):
            prof = {"L": "PLHM_LArmABS", "R": "PLHM_RArmABS", "B": "PLHM_ArmsABS", "RbyL": "PLHM_LArmABS"}[sfx]
            CLIPS.append({"id": len(CLIPS), "set": set_id, "stem": f"plhm_{fam}_{a}_{sfx}", "anim": pre + a.capitalize() + sfx,
                          "action": ACT[a], "mask": mask, "armed": armed, "profile": prof})


def anm_guid(stem):
    m = os.path.join(TXA_DIR, stem + ".anm.meta")
    if not os.path.exists(m):
        return None
    g = re.search(r'Name "\{([0-9A-F]{16})\}', open(m, encoding="utf-8").read())
    return g.group(1) if g else None


def et_guid(path):
    m = path + ".meta"
    if not os.path.exists(m):
        return None
    g = re.search(r'Name "\{([0-9A-F]{16})\}', open(m, encoding="utf-8").read())
    return g.group(1) if g else None


def w(path, text):
    open(path, "w", encoding="utf-8", newline="\n").write(text)


def do_txa():
    new = []
    for c in CLIPS:
        src = os.path.join(BUILD, c["stem"] + ".txa")
        dst = os.path.join(TXA_DIR, c["stem"] + ".txa")
        if not os.path.exists(dst):
            new.append(dst)
        shutil.copyfile(src, dst)
    print("NEW", " ".join(f'"{p}"' for p in new))


def do_meta():
    for c in CLIPS:
        m = os.path.join(TXA_DIR, c["stem"] + ".anm.meta")
        if not os.path.exists(m):
            print("missing meta", m)
            continue
        s = open(m, encoding="utf-8").read()
        if "SourceProfile" in s:
            s = re.sub(r'SourceProfile "[^"]*"', f'SourceProfile "{c["profile"]}"', s)
        else:
            s = s.replace("  TXAResourceClass PC {\n  }", f'  TXAResourceClass PC {{\n   SourceProfile "{c["profile"]}"\n  }}', 1)
        assert f'SourceProfile "{c["profile"]}"' in s, m
        w(m, s)
    print("meta ok")


def do_graph():
    ast = ["AnimSetTemplateSource {", " Groups {", '  AnimSetTemplateSource_AnimationGroup "{44ABD3C7E12B0561}" {',
           '   Name "EarPro"', "   Animations {"]
    # the engine looks names up in a SORTED list: an unsorted list left 14 of 16 sources 'Invalid' (2026-11-06)
    ast += [f'    "{n}"' for n in sorted(c["anim"] for c in CLIPS)]
    ast += ["   }", "   Columns {", '    "Default"', "   }", "  }", " }", "}"]
    w(os.path.join(WS, "PLHM_EarPro.ast"), "\n".join(ast) + "\n")
    asi = ["AnimSetInstanceSource {", ' Template "{98906314B67BFA60}anims/EarPro/workspaces/PLHM_EarPro.ast"', " Lines {"]
    for c in sorted(CLIPS, key=lambda c: c["anim"]):
        g = anm_guid(c["stem"])
        assert g, "no anm guid for " + c["stem"]
        asi += [f'  AnimSetInstanceSource_Line "EarPro.Default.{c["anim"]}" {{',
                f'   Resource "{{{g}}}anims/EarPro/txa/{c["stem"]}.anm"', "  }"]
    asi += [" }", "}"]
    w(os.path.join(WS, "PLHM_EarPro_RaiseL.asi"), "\n".join(asi) + "\n")
    nodes = []
    for i, c in enumerate(CLIPS):
        a = c["anim"]
        x = (i % 4) * 10
        y = (i // 4) * 8
        h1 = "%016X" % (0x5A10000000000000 + i * 2)
        h2 = "%016X" % (0x5A10000000000001 + i * 2)
        nodes.append(f"""    AnimSrcNodeStateMachine MC_{a} {{
     Tags {{
      "TagGadget"
     }}
     EditorPos {x} {y}
     states {{
      AnimSrcNodeState Start {{
       EditorPos {x} {y + 2}
       Child "{a}_BufStart"
       StartCondition "true"
       TimeStorage "Real Time"
      }}
      AnimSrcNodeState Act {{
       EditorPos {x + 3} {y + 2}
       Child "{a}_ActB"
       StartCondition "false"
       TimeStorage "Real Time"
      }}
      AnimSrcNodeState Done {{
       EditorPos {x + 6} {y + 2}
       Child "{a}_BufDone"
       StartCondition "false"
       TimeStorage "Real Time"
      }}
     }}
     transitions {{
      AnimSrcNodeTransition "{{{h1}}}" {{
       FromState "Start"
       ToState "Act"
       Duration "0.3"
       Condition "true"
       BlendFn S
      }}
      AnimSrcNodeTransition "{{{h2}}}" {{
       FromState "Act"
       ToState "Done"
       Duration "0.35"
       Condition "RemainingTimeLess(0.35)"
       BlendFn S
      }}
     }}
    }}
    AnimSrcNodeBufferUse {a}_BufStart {{
     EditorPos {x} {y + 4}
     BufferName "FullbodyGadget"
    }}
    AnimSrcNodeBufferUse {a}_BufAct {{
     EditorPos {x + 2} {y + 5}
     BufferName "FullbodyGadget"
    }}
    AnimSrcNodeBufferUse {a}_BufDone {{
     EditorPos {x + 6} {y + 4}
     BufferName "FullbodyGadget"
    }}
    AnimSrcNodeSource {a}_Src {{
     EditorPos {x + 4} {y + 5}
     Source "EarPro.Default.{a}"
    }}
    AnimSrcNodeBlend {a}_ActB {{
     EditorPos {x + 3} {y + 4}
     BlendWeight "1"
     Child0 "{a}_BufAct"
     Child1 "{a}_Src"
     Optimization "Always eval both"
    }}""")
    agf = "AnimSrcGraphFile {\n Sheets {\n  AnimSrcGraphSheet Main {\n   Nodes {\n" + "\n".join(nodes) + "\n   }\n  }\n }\n}\n"
    w(os.path.join(WS, "PLHM_EarPro.agf"), agf)
    print("graph ok", len(CLIPS))


def proxy_path(c):
    return os.path.join(HANDS, f"PLHM_EarProHand_{c['anim']}.et")


def do_proxies():
    base = "{76F4C8F4B05F7003}Prefabs/EarPro/Hands/PLHM_EarProHand_RaiseL.et"
    new = []
    for c in CLIPS:
        if c["anim"] == "RaiseL":
            continue
        p = proxy_path(c)
        ent_id = "%016X" % (0x5E1C7A3B9D204F00 + c["id"] * 7)
        if c["anim"] == "LowerL":
            ent_id = "5E1C7A3B9D204F86"        # keep the registered prefab's id
        w(p, f"""GenericEntity : "{base}" {{
 ID "{ent_id}"
 components {{
  InventoryItemComponent "{{B8A863F664B9C48D}}" {{
   Attributes SCR_ItemAttributeCollection "{{429BB8DA8FD6E9D4}}" {{
    ItemAnimationAttributes ItemAnimationAttributes "{{1977151CB44A0F26}}" {{
     AnimationAttachments {{
      AnimationAttachmentInfo "{{CED57F735D98A848}}" {{
       StartNode "MC_{c['anim']}"
      }}
     }}
    }}
   }}
  }}
 }}
}}
""")
        if not os.path.exists(p + ".meta"):
            new.append(p)
    print("NEW", " ".join(f'"{x}"' for x in new))


def fl(v):
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def do_enforce():
    lines = ["// Phaseline Helmets - ear-pro clip table.",
             "// GENERATED by OUTLAWHELMETS/_earpro/tools/gen_earpro_assets.py from build/anim/*_timeline.json - do not edit by hand.",
             "// Clip ids are replicated (PLHM_EarProComponent.m_iTransition): append only.",
             "class PLHM_EarProClips",
             "{",
             f"\tstatic const int COUNT = {len(CLIPS)};",
             ""]
    def table(name, typ, vals):
        lines.append(f"\tstatic {typ} {name}(int clip)")
        lines.append("\t{")
        lines.append("\t\tswitch (clip)")
        lines.append("\t\t{")
        for i, v in enumerate(vals):
            lines.append(f"\t\t\tcase {i}: return {v};")
        lines.append("\t\t}")
        default = {"int": "0", "float": "0", "bool": "false", "ResourceName": "ResourceName.Empty", "string": '""'}[typ]
        lines.append(f"\t\treturn {default};")
        lines.append("\t}")
        lines.append("")
    tls = {}
    for c in CLIPS:
        tls[c["id"]] = json.load(open(os.path.join(BUILD, c["stem"] + "_timeline.json")))
    table("SetOf", "int", [c["set"] for c in CLIPS])
    table("ActionOf", "int", [c["action"] for c in CLIPS])
    table("MaskOf", "int", [c["mask"] for c in CLIPS])
    table("ArmedOf", "bool", ["true" if c["armed"] else "false" for c in CLIPS])
    table("Duration", "float", [fl(tls[c["id"]]["duration"]) for c in CLIPS])
    table("NameOf", "string", ['"%s"' % c["anim"] for c in CLIPS])
    px = []
    for c in CLIPS:
        p = proxy_path(c)
        g = et_guid(p)
        if not g and "--allow-missing" in sys.argv:
            px.append('""')        # bootstrap: proxy not registered yet (regenerate after registration)
            continue
        assert g, "proxy not registered: " + p
        px.append(f'"{{{g}}}Prefabs/EarPro/Hands/PLHM_EarProHand_{c["anim"]}.et"')
    table("Proxy", "ResourceName", px)
    lines += ["\t//! clip for a clip set (placement family) / action / side mask; armed = rifle in hand (left hand only).",
              "\t//! -1 = none (armed both cups: run L, then R)",
              "\tstatic int Find(int clipSet, int action, int mask, bool armed)",
              "\t{",
              "\t\tfor (int i = 0; i < COUNT; i++)",
              "\t\t{",
              "\t\t\tif (SetOf(i) != clipSet || ActionOf(i) != action || MaskOf(i) != mask)",
              "\t\t\t\tcontinue;",
              "\t\t\tif (mask == 1 || ArmedOf(i) == armed)",
              "\t\t\t\treturn i;",
              "\t\t}",
              "\t\treturn -1;",
              "\t}",
              "",
              "\t//! cup channel keys (clip seconds, value pairs) for one side (1 = L, 2 = R); false if the clip does not move it",
              "\tstatic bool Keys(int clip, int side, out array<float> splay, out array<float> swing, out array<float> spin, out array<float> yaw)",
              "\t{",
              "\t\tswitch (clip * 4 + side)",
              "\t\t{"]
    for c in CLIPS:
        for sd, sn in (("L", 1), ("R", 2)):
            k = tls[c["id"]]["cup_keys"].get(sd)
            if not k:
                continue
            lines.append(f"\t\t\tcase {c['id'] * 4 + sn}:")
            for ch in ("splay", "swing", "spin", "yaw"):
                arr = ", ".join(f"{fl(t)}, {fl(v)}" for t, v in k.get(ch, [[0, 0]]))
                lines.append(f"\t\t\t\t{ch} = {{{arr}}};")
            lines.append("\t\t\t\treturn true;")
    lines += ["\t\t}", "\t\treturn false;", "\t}", "}", ""]
    w(SCRIPT, "\n".join(lines))
    print("enforce ok", SCRIPT)


if __name__ == "__main__":
    {"txa": do_txa, "meta": do_meta, "graph": do_graph, "proxies": do_proxies, "enforce": do_enforce}[sys.argv[1]]()
