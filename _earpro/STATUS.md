# Phaseline Helmets - interactive ear protection: status

Last update: 2026-11-06 22:50. Branch `earpro-articulation` of this repo (not committed). Mod files are in `SFHELMETS`
(prefix `PLHM_`); this `_earpro` folder holds the test addon, tools and Blender scripts and is never packed.

## What changed in the mod
- All 24 ear-pro prefabs (`Prefabs/EarPro`) carry `PLHM_EarProComponent` (clip set per placement; ComTac pivot/poses).
- The 19 worn models (AMP 3 shapes x 3 colours, ComTac VI + no-strap x SF/XP x colours) are rigged IN PLACE: same files,
  names, GUIDs, vertices, UVs and colour materials; a 5-bone skeleton added (originals backed up on D:).
- Helmet ear-pro slots (SF, Maritime, XP bases): `InheritParentSkeleton 1` -> `PivotID "Head"`.
- 72 hand clips (6 placement families x raise / lower / vent / unvent x left, right, both hands), 72 proxies, graph.
- Scripts `Scripts/Game/EarPro`, inputs `Configs/System/chimeraInputCommon.conf` + `keyBindingMenu.conf`.

## Verified in game (Arma Reforger 1.9.0.37, Diag client)
| What | Evidence |
|---|---|
| Every ear-pro prefab sits where it did on its helmet (SF / Maritime / XP), all colours | run `rollout_v2` fit shots (third person) |
| Hand on the cup through every clip, all 6 families, both hands: knuckle 51-57 mm median from the grip point | run `rollout_v2` `[RO]` log |
| Weapon in hand: slung first (M60 ~1.4 s), own hands work the cups, weapon re-drawn after (~4.5 s total) | run `rollout_v2` (sling/redraw log + shots) |
| ComTac rear fold matches the reference photo (cup behind the ARC adapter at rail height) | Blender clearance lab + fit shots |
| First-person hide (`OUTLAW_FirstPersonHideComponent`) still hides the wearer's own ear-pro after the visual rebuild | run `fitdiag` |
| Dedicated server + client, replication, dummy loop | run `mpdemo_2026-11-06_21-05-33` (Tyler: "looks perfect", AMP prototype) |

## Controls
`[` stow / deploy both cups, `]` vent / close both cups, hold `\` radial (each cup on its own). Rebindable under
Settings > Controls > Phaseline. **Not yet pressed in game.**

## Not done yet
- Keybinds + radial pressed in game; dedicated server + 2 clients + join-in-progress with the full set.
- Interruption tests (death, unequip, vehicle entry mid-clip); docs set; commit (only when Tyler asks).
- Known: the ComTac fold path brushes the shell by ~3 mm with the thin stirrup wire beside the hub (not visible in renders).
