"""Run jobs through Claude's OWN Workbench on the ear-pro snapshot (never Tyler's): launch minimised after the Tyler
guard, wait for the NET API (port 5775 must be free before launch), run jobs, close OUR window, kill only OUR PID.

python wb_session.py <jobs.json>
jobs: [{"op": "fbx", "fbx": abs, "meta_src": abs|null, "skinning": true, "hierarchy": true},
       {"op": "register", "paths": [abs, ...]},
       {"op": "info", "path": abs}]
"""
import os, sys, json, time, socket, subprocess, re, ctypes
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wbcall

WB = r"C:\Users\tyler\Gaming\steamapps\common\Arma Reforger Tools\Workbench\ArmaReforgerWorkbenchSteamDiag.exe"
GPROJ = os.environ.get("EP_GPROJ", r"C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\SFHELMETS\addon.gproj")
ADDONS = os.environ.get("EP_ADDONS", r"C:\Users\tyler\Gaming\steamapps\common\Arma Reforger\addons,D:\PhaselineHelmetsTest\deps,C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS,C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\_earpro")
GUARD = r"C:\Users\tyler\OneDrive\Desktop\SOCOM_TRAINING_MAP\SOURCE\tools\tyler_guard.ps1"


def port_busy():
    try:
        socket.create_connection(("127.0.0.1", 5775), timeout=1).close()
        return True
    except OSError:
        return False


def tyler_busy():
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f". '{GUARD}'; Test-TylerBusy"], capture_output=True, text=True)
    return r.stdout.strip().lower().startswith("true")


def our_pids():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'ArmaReforgerWorkbench*' } | "
                        "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"], capture_output=True, text=True)
    out = []
    for ln in r.stdout.splitlines():
        if "|" in ln:
            pid, cmd = ln.split("|", 1)
            if "_earpro" in cmd or "PLHM_DevTools" in cmd:
                out.append(int(pid))
    return out


def main():
    jobs = json.load(open(sys.argv[1]))
    while tyler_busy():
        print("[guard] Tyler's game / Workbench is running - waiting", flush=True)
        time.sleep(30)
    if port_busy():
        print("ABORT: NET API port 5775 is already owned by another Workbench (maybe Tyler's) - not touching it", flush=True)
        return 2
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    p = subprocess.Popen([WB, "-gproj", GPROJ, "-addonsDir", ADDONS, "-noFocus"], startupinfo=si)
    print("launched WB pid", p.pid, flush=True)
    pid = p.pid
    for _ in range(400):
        if port_busy():
            break
        cand = our_pids()
        if cand and pid not in cand:
            pid = cand[0]
        wbcall.sweep(pid)
        time.sleep(2)
    else:
        print("NET API never came up", flush=True)
    time.sleep(5)
    cand = our_pids()
    if cand:
        pid = cand[0]
    print("our WB pid", pid, flush=True)
    results = []
    for j in jobs:
        t0 = time.time()
        if j["op"] == "fbx":
            fbx = j["fbx"]
            ov = []
            src = j.get("meta_src")
            if src and os.path.exists(src):
                txt = open(src, encoding="utf-8").read()
                ov = [{"sourceMaterial": s, "assignedMaterial": a} for s, a in
                      re.findall(r'SourceMaterial "([^"]+)"\s*\n\s*AssignedMaterial "([^"]+)"', txt)]
            xob = fbx[:-4] + ".xob"
            old = os.path.getmtime(xob) if os.path.exists(xob) else 0
            r = wbcall.call(pid, "ExportFBXResource", {"resourcePath": fbx, "exportMorphs": False,
                                                       "exportSceneHierarchy": bool(j.get("hierarchy", True)),
                                                       "exportSkinning": bool(j.get("skinning", True)),
                                                       "materialOverrides": ov})
            for _ in range(600):
                if os.path.exists(xob) and os.path.getmtime(xob) != old and os.path.exists(xob + ".meta"):
                    break
                wbcall.sweep(pid)
                time.sleep(1)
            time.sleep(2)
            meta = open(xob + ".meta", encoding="utf-8").read() if os.path.exists(xob + ".meta") else ""
            res = {"fbx": os.path.basename(fbx), "status": r, "xob_kb": round(os.path.getsize(xob) / 1024, 1) if os.path.exists(xob) else None,
                   "skinning": "ExportSkinning 1" in meta, "hierarchy": "ExportSceneHierarchy 1" in meta,
                   "assigned": meta.count("AssignedMaterial"), "name": (re.search(r'Name "(.*?)"', meta).group(1) if meta else None),
                   "secs": round(time.time() - t0, 1)}
        elif j["op"] == "register":
            r = wbcall.call(pid, "RegisterResource", {"path": j["paths"]})
            res = {"register": len(j["paths"]), "status": r, "secs": round(time.time() - t0, 1)}
        elif j["op"] == "info":
            r = wbcall.call(pid, "GetResourceInfo", {"path": j["path"], "expandResource": True})
            res = {"info": j["path"], "result": r}
        else:
            res = {"unknown": j}
        print(json.dumps(res), flush=True)
        results.append(res)
    # close our window, then make sure our PID is gone
    subprocess.run([sys.executable, os.path.join(HERE, "wb_close_pid.py"), str(pid)], timeout=200)
    for q in our_pids():
        subprocess.run(["taskkill", "/PID", str(q), "/F"], capture_output=True)
        print("killed own leftover WB", q, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
