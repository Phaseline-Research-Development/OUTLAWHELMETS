"""NET API call into Claude's OWN Workbench while answering only that PID's known dialogs:
'Register Resource File(s)' -> Enter (as Model), 'Script Authorization Required' -> Alt+Y (Bohemia's core import scripts)."""
import os, sys, time, threading, ctypes, re
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wbnet

u = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
answered = {"model": 0, "auth": 0}


def sweep(pid):
    def cb(h, l):
        p = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, b, 256)
            if b.value == "Register Resource File(s)":
                u.PostMessageW(h, 0x0100, 0x0D, 0); u.PostMessageW(h, 0x0101, 0x0D, 0); answered["model"] += 1
            elif b.value == "Script Authorization Required":
                lp = (1 << 29) | 1
                u.PostMessageW(h, 0x0104, 0x59, lp); u.PostMessageW(h, 0x0105, 0x59, lp | (3 << 30)); answered["auth"] += 1
        return True
    u.EnumWindows(EnumProc(cb), 0)


def call(pid, func, params, timeout=900):
    res = {}
    t = threading.Thread(target=lambda: res.update(r=wbnet.call(func, params, timeout=timeout)))
    t.start()
    while t.is_alive():
        sweep(pid); time.sleep(1.0)
    return res.get("r")


def meta_name(path):
    for _ in range(60):
        if os.path.exists(path + ".meta"):
            return re.search(r'Name "(.*?)"', open(path + ".meta", encoding="utf-8").read()).group(1)
        time.sleep(1)
    raise RuntimeError("no meta for " + path)
