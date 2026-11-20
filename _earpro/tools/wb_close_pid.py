"""Close Claude's OWN Workbench by PID: WM_CLOSE to its 'Enfusion Workbench' window, wait for exit (never by name)."""
import ctypes, sys, time, subprocess
from ctypes import wintypes

u = ctypes.windll.user32
pid = int(sys.argv[1])
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def wins():
    out = []

    def cb(h, l):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, b, 256)
            out.append((h, b.value))
        return True
    u.EnumWindows(EnumProc(cb), 0)
    return out


def alive():
    return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout


for h, t in wins():
    if t.startswith("Enfusion Workbench"):
        u.PostMessageW(h, 0x0010, 0, 0)
        print("WM_CLOSE", t)
for i in range(60):
    time.sleep(1)
    # answer a 'save changes?' prompt with No (Alt+N) - only on our PID's windows
    for h, t in wins():
        if t in ("Save changes", "Enfusion Workbench") or "save" in t.lower():
            pass
    if not alive():
        print("EXITED after", i + 1, "s")
        break
else:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    print("killed own WB", pid)
