# -*- coding: utf-8 -*-
"""
重建桌面快捷方式（换电脑、移动工具目录后跑一次即可）

只创建 1 个图标：
    刷新率切换  —— 打开主界面，分辨率 / 刷新率都在里面选（全部实时检测）

不设任何 Ctrl+Alt 全局热键（容易和其他软件冲突），也不生成档位快捷图标。
旧的本工具图标会被自动清理并送入回收站（不是永久删除）。
"""
import ctypes
import os
import re
import subprocess
import sys
from ctypes import wintypes as w

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

EXE = os.path.join(HERE, "dist", "RefreshSwitch.exe")
SRC = os.path.join(HERE, "refresh_switch.py")
DESK = os.path.join(os.path.expanduser("~"), "Desktop")

# 本工具以前生成过的图标命名规则： "144Hz 打游戏" / "1920x1080 原生"
PAT_HZ = re.compile(r"^\d+Hz .+\.lnk$")
PAT_RES = re.compile(r"^\d+x\d+ .+\.lnk$")


def find_pythonw():
    cand = []
    if sys.executable:
        cand.append(os.path.join(os.path.dirname(sys.executable), "pythonw.exe"))
    base = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                        "Programs", "Python")
    if os.path.isdir(base):
        for d in sorted(os.listdir(base), reverse=True):
            cand.append(os.path.join(base, d, "pythonw.exe"))
    for c in cand:
        if os.path.isfile(c):
            return c
    return None


def trash(paths):
    """把文件送进回收站（SHFileOperationW + FOF_ALLOWUNDO）。"""
    paths = [p for p in paths if os.path.isfile(p)]
    if not paths:
        return 0

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", w.HWND),
            ("wFunc", w.UINT),
            ("pFrom", w.LPCWSTR),
            ("pTo", w.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", w.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", w.LPCWSTR),
        ]

    op = SHFILEOPSTRUCTW()
    op.wFunc = 3                      # FO_DELETE
    op.pFrom = "\0".join(paths) + "\0\0"   # 多路径 \0 分隔 + 双 \0 结尾
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # 允许撤销|不确认|静默|无错误框
    try:
        ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except Exception as e:
        print("  回收站删除失败:", e)
        return 0
    for p in paths:
        print("  已移除(回收站):", os.path.basename(p))
    return len(paths)


if os.path.isfile(EXE):
    LAUNCH = EXE
    WORD = ""
    print("使用打包版:", EXE)
else:
    pw = find_pythonw()
    if not pw:
        sys.exit("没找到 exe，也没找到 pythonw.exe。")
    LAUNCH = pw
    WORD = '"%s"' % SRC
    print("使用源码版:", pw)

# ---- 清掉以前生成的档位图标 ----
old = [os.path.join(DESK, f) for f in os.listdir(DESK)
       if f.endswith(".lnk") and (PAT_HZ.match(f) or PAT_RES.match(f))]
if old:
    print("清理旧图标:")
    trash(old)
else:
    print("没有需要清理的旧图标")

# ---- 建 1 个图标（无热键）----
vbs = "\r\n".join([
    'Set ws = CreateObject("WScript.Shell")',
    'py = "%s"' % LAUNCH.replace("\\", "\\\\"),
    'word = "%s"' % WORD.replace("\\", "\\\\"),
    'fd = "%s"' % HERE.replace("\\", "\\\\"),
    'dt = ws.SpecialFolders("Desktop")',
    'Set s = ws.CreateShortcut(dt & "\\刷新率切换.lnk")',
    's.TargetPath = py',
    's.Arguments = Trim(word)',
    's.WorkingDirectory = fd',
    's.Description = "刷新率 / 分辨率一键切换（自动检测本机档位）"',
    's.IconLocation = py & ",0"',
    's.WindowStyle = 7',
    's.Hotkey = ""',
    's.Save',
    'WScript.Echo "OK"',
]) + "\r\n"
print("创建: 刷新率切换（无全局热键）")

tmp = os.path.join(os.environ.get("TEMP", "."), "_mklnk6.vbs")
with open(tmp, "wb") as f:
    f.write(b"\xff\xfe")
    f.write(vbs.encode("utf-16-le"))
r = subprocess.run(["cscript", "//nologo", tmp],
                   capture_output=True, text=True, errors="replace")
print("cscript 退出码:", r.returncode)
if r.stderr.strip():
    print("错误:", r.stderr)
try:
    os.remove(tmp)
except Exception:
    pass

print("\n桌面现有本工具图标:")
for f in sorted(os.listdir(DESK)):
    if f.endswith(".lnk") and ("刷新率" in f or PAT_HZ.match(f)
                               or PAT_RES.match(f)):
        print(" *", f)
