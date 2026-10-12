# -*- coding: utf-8 -*-
"""
刷新率 / 分辨率 通用切换工具 v4 —— 通用版，不绑定任何具体显示器

设计目标：任何 Windows 机器、任何显示器都能直接用。
  覆盖 60Hz 办公屏 ~ 1000Hz+ 电竞屏（卓威 600 / 蚂蚁电竞 750 / AUO 800 /
  LG·飞利浦 Evnia·三星 1000~1040Hz），分辨率与刷新率全部实时检测，不设人为上限。

工作方式：
  启动时不假定任何参数，实时向系统查询该显示器支持的全部「分辨率 × 刷新率」组合。
  先选分辨率，档位列表会自动变成该分辨率下可用的刷新率；点一下即同时应用两者。

重要行为：
  - 请求的刷新率超过该分辨率下的上限时，自动回落到该分辨率支持的最高档，不报错。
    （例如 1080p 最高 144Hz 的屏幕上点 800Hz -> 回落到 144Hz）
  - 切换分辨率时若当前刷新率在新分辨率下不可用，同样回落到新分辨率的最高档。
  - 每次切换都先 TEST 验证再正式应用，切到不支持的模式不会黑屏。

用法：
  双击 / 无参数                        -> 打开图形界面
  refresh_switch.py list               -> 列出全部分辨率及其可用档位
  refresh_switch.py 144                -> 只改刷新率（保持当前分辨率）
  refresh_switch.py 1920x1080          -> 只改分辨率（刷新率自动适配）
  refresh_switch.py 1920x1080@144      -> 同时设定分辨率和刷新率
  refresh_switch.py 144 DISPLAY2       -> 指定显示器

界面：F5 重新检测 / Esc 关闭 / 支持自定义 Hz 输入

依赖：仅 Python 标准库（tkinter + ctypes），无需第三方包。
"""
import ctypes
import json
import os
import sys
import threading
import tkinter as tk
import urllib.request
from tkinter import ttk, messagebox

user32 = ctypes.windll.user32

# 高分屏下让窗口不模糊（必须在创建窗口前调用）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

ENUM_CURRENT_SETTINGS = -1
DM_DISPLAYFREQUENCY = 0x400000
DM_PELSWIDTH = 0x80000
DM_PELSHEIGHT = 0x100000
DM_BITSPERPEL = 0x40000
CDS_TEST = 0x2
DISP_CHANGE_SUCCESSFUL = 0

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x4


class DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", ctypes.c_ulong),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


def list_displays():
    """返回 [(设备名, 描述, 是否主显示器), ...]"""
    out = []
    i = 0
    while True:
        dd = DISPLAY_DEVICE()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
        if user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0) == 0:
            break
        f = dd.StateFlags
        if f & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            desc = dd.DeviceString.strip() or dd.DeviceName.strip()
            out.append((dd.DeviceName, desc,
                        bool(f & DISPLAY_DEVICE_PRIMARY_DEVICE)))
        i += 1
    if not out:
        out.append((None, "默认显示器", True))
    return out


def primary_display():
    for name, desc, isp in list_displays():
        if isp:
            return name
    return list_displays()[0][0]


def get_current(name):
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    r = user32.EnumDisplaySettingsW(name, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    return dm if r else None


# 驱动只上报极少数模式时用来补充的常用分辨率（不会超过屏幕原生面积）
COMMON_RES = [
    (3840, 2160), (2560, 1440), (2048, 1152), (1920, 1200), (1920, 1080),
    (1776, 1000), (1680, 1050), (1600, 1200), (1600, 1024), (1600, 900),
    (1440, 1080), (1440, 900), (1366, 768), (1360, 768), (1280, 1024),
    (1280, 960), (1280, 800), (1280, 720), (1152, 864), (1024, 768),
    (1024, 600), (960, 540), (854, 480), (800, 600), (720, 576), (640, 480),
]
PROBE_RATES = (240, 165, 144, 120, 100, 75, 60)


def probe_mode(name, w, h, hz):
    """用 CDS_TEST 试探「分辨率+刷新率」是否被接受。只验证，不会真的切换。"""
    dm = get_current(name)
    if dm is None:
        return False
    new = DEVMODE()
    new.dmSize = ctypes.sizeof(DEVMODE)
    user32.EnumDisplaySettingsW(name, ENUM_CURRENT_SETTINGS, ctypes.byref(new))
    new.dmPelsWidth = w
    new.dmPelsHeight = h
    new.dmDisplayFrequency = hz
    new.dmBitsPerPel = dm.dmBitsPerPel
    new.dmFields = (DM_PELSWIDTH | DM_PELSHEIGHT |
                    DM_DISPLAYFREQUENCY | DM_BITSPERPEL)
    return user32.ChangeDisplaySettingsExW(
        name, ctypes.byref(new), 0, CDS_TEST, None) == DISP_CHANGE_SUCCESSFUL


def get_modes(name, probe=True):
    """返回 {(宽, 高): [刷新率升序], ...}，按面积从大到小排列。

    先枚举驱动上报的模式。部分驱动/笔记本只上报两三个模式，那样下拉框就没得选，
    所以当枚举结果偏少时，再用 CDS_TEST 逐个试探常用分辨率，把可用的都补进来
    —— 这样换到任何一台显示器上都能拿到完整的分辨率列表。
    """
    modes = {}
    m = DEVMODE()
    m.dmSize = ctypes.sizeof(DEVMODE)
    i = 0
    while user32.EnumDisplaySettingsW(name, i, ctypes.byref(m)) != 0:
        key = (int(m.dmPelsWidth), int(m.dmPelsHeight))
        modes.setdefault(key, set()).add(int(m.dmDisplayFrequency))
        i += 1

    if probe and len(modes) < 8:
        dm = get_current(name)
        if dm is not None:
            native_area = max((k[0] * k[1] for k in modes), default=0)
            native_area = max(native_area, dm.dmPelsWidth * dm.dmPelsHeight)
            cur_hz = int(dm.dmDisplayFrequency)
            for w, h in COMMON_RES:
                if (w, h) in modes:
                    continue
                if w * h > native_area:      # 不超过原生，避免塞进无意义的缩放档
                    continue
                ok = set()
                for hz in (cur_hz,) + PROBE_RATES:
                    if probe_mode(name, w, h, hz):
                        ok.add(int(hz))
                if ok:
                    modes[(w, h)] = ok

    out = {k: sorted(v) for k, v in modes.items()}
    return dict(sorted(out.items(), key=lambda kv: (kv[0][0] * kv[0][1], kv[0][0]),
                       reverse=True))


def get_rates(name, res=None):
    """某分辨率下可用的刷新率；不传 res 则用当前分辨率。"""
    modes = get_modes(name)
    if res is None:
        dm = get_current(name)
        if dm is None:
            return []
        res = (dm.dmPelsWidth, dm.dmPelsHeight)
    return modes.get(res, [])


def set_mode(name, w=None, h=None, hz=None):
    """同时设定分辨率和刷新率。省略的项保持当前值；刷新率超限自动回落到最高档。"""
    dm = get_current(name)
    if dm is None:
        return False, "无法读取当前显示设置"

    cur_res = (int(dm.dmPelsWidth), int(dm.dmPelsHeight))
    cur_hz = int(dm.dmDisplayFrequency)
    if w is None or h is None:
        w, h = cur_res

    modes = get_modes(name)
    if (w, h) not in modes:
        return False, "该显示器不支持 %dx%d（可用分辨率：%s）" % (
            w, h, " / ".join("%dx%d" % r for r in list(modes)[:8]))

    rates = modes[(w, h)]
    clamp_from = None    # 原始请求的 Hz（发生了回落才有值）
    clamp_hi = False     # True = 超上限回落到最高档；False = 回落到最接近的低档
    if hz is None:
        # 只改分辨率：当前 Hz 在新分辨率下能用就保留，否则回落到最高档
        if cur_hz not in rates:
            clamp_from = cur_hz
            clamp_hi = True
            hz = max(rates)
        else:
            hz = cur_hz
    elif hz > max(rates):
        clamp_from = hz
        clamp_hi = True
        hz = max(rates)

    if (w, h) == cur_res and hz == cur_hz:
        # 已经处于目标模式：若这次是回落，仍然要说明原因，否则用户会困惑
        if clamp_from is not None:
            return True, "%dHz 超出 %dx%d 的上限，当前已是最高档 %dHz" % (
                clamp_from, w, h, hz)
        return True, "已经是 %dx%d @ %dHz 了" % (w, h, hz)

    new = DEVMODE()
    new.dmSize = ctypes.sizeof(DEVMODE)
    user32.EnumDisplaySettingsW(name, ENUM_CURRENT_SETTINGS, ctypes.byref(new))
    new.dmPelsWidth = w
    new.dmPelsHeight = h
    new.dmDisplayFrequency = hz
    new.dmBitsPerPel = dm.dmBitsPerPel
    new.dmFields = (DM_PELSWIDTH | DM_PELSHEIGHT |
                    DM_DISPLAYFREQUENCY | DM_BITSPERPEL)

    def test(freq):
        new.dmDisplayFrequency = freq
        return user32.ChangeDisplaySettingsExW(
            name, ctypes.byref(new), 0, CDS_TEST, None)

    rc = test(hz)
    if rc != DISP_CHANGE_SUCCESSFUL:
        # 请求的档位不在枚举列表里（例如 600Hz 屏点 400Hz）：
        # 回落到「不超过请求值」的最接近档位，而不是直接报错
        lower = [r for r in rates if r < hz]
        if lower:
            cand = max(lower)
            if test(cand) == DISP_CHANGE_SUCCESSFUL:
                clamp_from = clamp_from if clamp_from is not None else hz
                hz = cand
            else:
                return False, "系统拒绝该模式（错误码 %d），已保持原样" % rc
        else:
            return False, "系统拒绝该模式（错误码 %d），已保持原样" % rc
        if (w, h) == cur_res and hz == cur_hz:
            return True, "%dHz 在当前分辨率下不可用，当前已是 %dHz" % (
                clamp_from, hz)

    rc = user32.ChangeDisplaySettingsExW(name, ctypes.byref(new), 0, 0, None)
    if rc != DISP_CHANGE_SUCCESSFUL:
        return False, "应用失败（错误码 %d）" % rc

    if clamp_from is not None:
        if clamp_hi:
            return True, "%dHz 超出 %dx%d 的上限，已回落到本机最高档 %dHz" % (
                clamp_from, w, h, hz)
        return True, "%dHz 不是本机档位，已回落到最接近的 %dHz" % (
            clamp_from, hz)
    return True, "已切换到 %dx%d @ %dHz" % (w, h, hz)


# -------- 用途判定：按档位在整体中的相对位置推导，60Hz~1000Hz+ 通用 --------
#
# 注意不能简单用 "能被 24 整除 = 看电影"，因为 240/360/480/600/720/960 全都能被
# 24 整除，在超高刷显示器上会把游戏档误判成电影档。所以按区间划分。

STYLES = {
    "打游戏": "#d73a49",
    "电竞":   "#c2410c",
    "竞技":   "#e8590c",
    "均衡":   "#1f6feb",
    "高刷":   "#1f6feb",
    "看电影": "#8250df",
    "看视频": "#1f6feb",
    "省电":   "#2da44e",
    "最高":   "#8250df",
    "自定义": "#6e7681",
}


def classify(hz, rates):
    """返回 (用途标签, 说明)。规则随检测到的档位自动适配。"""
    if not rates:
        return "自定义", "按需使用"
    hi, lo = max(rates), min(rates)
    if hz == hi:
        # 最高档低于 100Hz 的显示器（办公屏/入门屏）不该标成"打游戏"
        if hi >= 100:
            return "打游戏", "最高刷新率 · 满血流畅"
        return "最高", "该显示器最高档位"
    if hz >= 480:
        return "电竞", "超高刷档 · 竞技发烧"
    if hz >= 240:
        return "竞技", "高刷游戏档 · 降低显卡负载"
    if hz == 120:
        return "看电影", "24fps 五倍频 / 60fps 两倍频 · 无抖动"
    if hz >= 120:
        return "均衡", "日常高刷 · 流畅与功耗兼顾"
    if hz >= 100:
        return "高刷", "流畅与功耗兼顾"
    if hz >= 60:
        return "看视频", "通用片源 · 省电"
    if hz == lo:
        return "省电", "最低刷新率"
    return "自定义", "按需使用"


# ------------------------------ 图形界面 ------------------------------

BG = "#17191f"
CARD = "#23262f"
CARD2 = "#2b2f3a"
HOVER = "#31353f"
FG = "#eceff4"
MUTED = "#98a1b0"
TEXT = "#c9d1d9"
LINE = "#2c303a"
ACCENT = "#e3b341"
GOOD = "#3fb950"
BAD = "#f85149"
PINK = "#f778ba"
MAX_LIST_H = 520   # 档位列表最大高度，超出才滚动

# 常用档位（全面覆盖）：即使本机不支持也能点（超上限会自动回落到本机最高档）
QUICK_RATES = (60, 120, 144, 165, 240, 360, 400, 600, 800, 1000)

STORY_TEXT = (
    "起因是作者有一款用了 10 年的显示器，屏幕边框上贴着 144Hz，"
    "就一直以为自己用的是 144Hz。\n"
    "直到 2026.10.13 凌晨，让 AI 帮我改成 144Hz，"
    "才知道这十年用的一直是 60Hz——\n"
    "期间换了 CPU、换了主板，打三角洲还是卡，气笑了。\n"
    "所以做了这个工具，让其他小伙伴们都不要重蹈我的覆辙。\n"
    "如果对你有帮助，希望您能给我个赞赏，让我更有动力！"
)


def res_path(name):
    """兼容源码运行与 PyInstaller 打包后的资源文件定位。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def data_path():
    """点赞计数存在 %APPDATA%，绿色不污染工具目录。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "RefreshSwitch")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "likes.txt")


def load_likes_state():
    """返回 {"liked": 本机是否已贡献过, "global": 最近一次已知的全局点赞数}。

    兼容旧版本：如果文件里只是个整数，按「已点过、全局数=该整数」处理。
    """
    default = {"liked": False, "global": 0}
    try:
        with open(data_path(), "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return default
        try:
            d = json.loads(raw)
            return {"liked": bool(d.get("liked")), "global": int(d.get("global", 0))}
        except ValueError:
            n = int(raw)
            return {"liked": n > 0, "global": n}
    except Exception:
        return default


def save_likes_state(state):
    try:
        with open(data_path(), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def cloud_likes_url():
    """云端点赞计数器地址，优先级：环境变量 > 同目录下的 cloud_likes_url.txt。

    没配置则返回 None，此时点赞退化为纯本机计数（不影响使用）。
    """
    env = os.environ.get("REFRESH_SWITCH_LIKES_URL")
    if env and env.strip():
        return env.strip()
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, "cloud_likes_url.txt")
    try:
        with open(p, "r", encoding="utf-8") as f:
            u = f.read().strip()
        return u or None
    except Exception:
        return None


def fetch_cloud_likes(url):
    """GET 云端当前总数；失败返回 None。"""
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            return int((r.read() or b"0").decode().strip() or "0")
    except Exception:
        return None


def bump_cloud_likes(url):
    """POST +1，返回新的总数；失败返回 None。"""
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=4) as r:
            return int((r.read() or b"0").decode().strip() or "0")
    except Exception:
        return None


class App:
    def __init__(self, root):
        self.root = root
        self.displays = list_displays()
        self.name = primary_display()
        self.buttons = {}
        self.modes = {}
        self.res_list = []
        self.rates = []
        self.target_res = None

        root.title("刷新率 / 分辨率切换")
        root.configure(bg=BG)
        root.resizable(True, True)          # 允许手动拉伸/缩小窗口
        root.minsize(640, 600)              # 限制最小尺寸，避免挤压到底部按钮

        # 显示器选择（多显示器时才显示）
        if len(self.displays) > 1:
            row = tk.Frame(root, bg=BG)
            row.pack(fill="x", padx=22, pady=(16, 0))
            tk.Label(row, text="显示器", bg=BG, fg=MUTED,
                     font=("Microsoft YaHei", 9)).pack(side="left")
            cb = ttk.Combobox(
                row, state="readonly", width=30,
                values=["%s%s" % (d[1], "  [主]" if d[2] else "")
                        for d in self.displays])
            cur = 0
            for i, d in enumerate(self.displays):
                if d[0] == self.name:
                    cur = i
            cb.current(cur)
            cb.pack(side="left", padx=8)
            cb.bind("<<ComboboxSelected>>", self.on_display)

        # ---- 顶部标题 ----
        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=22, pady=(12, 0))
        tk.Label(top, text="刷新率 · 分辨率切换", bg=BG, fg=FG,
                 font=("Microsoft YaHei", 13, "bold")).pack(anchor="w")
        tk.Label(top, text="通用工具 · 实时检测本机全部档位 · 不写死任何参数",
                 bg=BG, fg="#6a7280",
                 font=("Microsoft YaHei", 8)).pack(anchor="w", pady=(2, 0))
        tk.Frame(root, bg=ACCENT, height=2).pack(fill="x", padx=22, pady=(6, 0))

        # ---- 本机最高刷新率（最醒目） ----
        hero = tk.Frame(root, bg=CARD)
        hero.pack(fill="x", padx=22, pady=(10, 0))
        hi = tk.Frame(hero, bg=CARD)
        hi.pack(fill="x", padx=16, pady=10)
        tk.Label(hi, text="本机最高刷新率", bg=CARD, fg=MUTED,
                 font=("Microsoft YaHei", 10)).pack(anchor="w")
        self.max_lbl = tk.Label(hi, text="-- Hz", bg=CARD, fg=ACCENT,
                                font=("Consolas", 23, "bold"))
        self.max_lbl.pack(anchor="w", pady=(0, 0))
        self.cur_line = tk.Label(hi, text="", bg=CARD, fg=FG,
                                 font=("Microsoft YaHei", 10, "bold"))
        self.cur_line.pack(anchor="w", pady=(3, 0))
        tk.Label(
            hi, text="不知道选哪个？直接点下面「一键最高」，自动适配到您显示器支持的最高刷新率",
            bg=CARD, fg="#8b949e", font=("Microsoft YaHei", 9),
            wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))

        # ---- 分辨率选择 ----
        rr = tk.Frame(root, bg=BG)
        rr.pack(fill="x", padx=22, pady=(8, 0))
        tk.Label(rr, text="分辨率", bg=BG, fg=TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left")
        self.rcb = ttk.Combobox(rr, state="readonly", width=22)
        self.rcb.pack(side="left", padx=10)
        self.rcb.bind("<<ComboboxSelected>>", self.on_res)
        self.rcount = tk.Label(rr, text="", bg=BG, fg=MUTED,
                               font=("Microsoft YaHei", 9))
        self.rcount.pack(side="left")
        self.hint = tk.Label(rr, text="", bg=BG, fg=ACCENT,
                             font=("Microsoft YaHei", 9))
        self.hint.pack(side="left")

        # ---- 快捷：一键最高（大按钮）+ 省电/低档（旁边） ----
        qa = tk.Frame(root, bg=BG)
        qa.pack(fill="x", padx=22, pady=(8, 0))
        self.max_btn = tk.Button(
            qa, text="⚡  一键最高", bg=ACCENT, fg="#1a1c22",
            activebackground="#f0c457", activeforeground="#1a1c22",
            relief="flat", bd=0, padx=22, pady=8, cursor="hand2",
            font=("Microsoft YaHei", 12, "bold"), command=self.apply_max)
        self.max_btn.pack(side="left")
        low = tk.Frame(qa, bg=BG)
        low.pack(side="left", padx=(12, 0))
        for hz, lbl in ((60, "省电"), (120, "看电影")):
            tk.Button(low, text="%dHz %s" % (hz, lbl), bg=CARD2, fg=MUTED,
                      activebackground=HOVER, activeforeground=FG,
                      relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                      font=("Microsoft YaHei", 10),
                      command=lambda x=hz: self.apply(x)
                      ).pack(side="left", padx=(0, 8))

        # ---- 常用档位（全面覆盖） ----
        qk = tk.Frame(root, bg=BG)
        qk.pack(fill="x", padx=22, pady=(8, 0))
        tk.Label(qk, text="常用档位（全面覆盖）", bg=BG, fg=TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(anchor="w")
        tk.Label(qk, text="超出本机上限会自动回落到本机最高档",
                 bg=BG, fg="#6a7280", font=("Microsoft YaHei", 8)
                 ).pack(anchor="w", pady=(1, 4))
        qrow = tk.Frame(root, bg=BG)
        qrow.pack(fill="x", padx=22)
        for hz in QUICK_RATES:
            tk.Button(qrow, text="%d Hz" % hz, bg=CARD2, fg="#79c0ff",
                      activebackground=HOVER, activeforeground="#cae8ff",
                      relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                      font=("Consolas", 10, "bold"),
                      command=lambda x=hz: self.apply(x)
                      ).pack(side="left", padx=(0, 8))

        # ---- 本机可用档位（文字标签） ----
        tt = tk.Frame(root, bg=BG)
        tt.pack(fill="x", padx=22, pady=(10, 3))
        tk.Label(tt, text="本机可用档位", bg=BG, fg=TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left")
        tk.Label(tt, text="点一下即切换 · 当前档高亮", bg=BG, fg="#6a7280",
                 font=("Microsoft YaHei", 8)).pack(side="left", padx=8)
        self.tags = tk.Frame(root, bg=BG)
        self.tags.pack(fill="x", padx=22)

        # ---- 自定义 Hz ----
        cus = tk.Frame(root, bg=BG)
        cus.pack(fill="x", padx=22, pady=(8, 0))
        tk.Label(cus, text="自定义", bg=BG, fg=TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left")
        self.var = tk.StringVar()
        tk.Entry(cus, textvariable=self.var, width=7, bg=CARD, fg=FG,
                 insertbackground=FG, relief="flat",
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=10)
        tk.Label(cus, text="Hz", bg=BG, fg=MUTED,
                 font=("Microsoft YaHei", 9)).pack(side="left")
        tk.Button(cus, text="应用", bg=CARD2, fg=FG, activebackground=HOVER,
                  relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                  font=("Microsoft YaHei", 9),
                  command=self.apply_custom).pack(side="left", padx=12)
        tk.Label(root, text="想用其他刷新率？直接在这里输入，例如 75 / 90 / 200",
                 bg=BG, fg="#6a7280", font=("Microsoft YaHei", 8)
                 ).pack(anchor="w", padx=22, pady=(2, 0))

        self.status = tk.Label(root, text="", bg=BG, fg=MUTED,
                               font=("Microsoft YaHei", 10, "bold"), height=2,
                               wraplength=430, justify="left")
        self.status.pack(fill="x", padx=22, pady=(6, 0))

        # ---- 底部：作者的话 ----
        tk.Frame(root, bg=LINE, height=1).pack(fill="x", padx=22, pady=(3, 8))
        story = tk.Frame(root, bg=CARD)
        story.pack(fill="x", padx=22)
        si = tk.Frame(story, bg=CARD)
        si.pack(fill="x", padx=16, pady=9)
        tk.Label(si, text="❝  作者的话", bg=CARD, fg=ACCENT,
                 font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        for line in STORY_TEXT.split("\n"):
            tk.Label(si, text=line, bg=CARD, fg=TEXT,
                     font=("Microsoft YaHei", 9), wraplength=420,
                     justify="left").pack(anchor="w", pady=(2, 0))

        # ---- 点赞 + 赞赏 ----
        acts = tk.Frame(root, bg=BG)
        acts.pack(fill="x", padx=22, pady=(8, 0))
        tk.Button(acts, text="♥  觉得有用，点个赞", bg=CARD2, fg=PINK,
                  activebackground=HOVER, activeforeground=PINK,
                  relief="flat", bd=0, padx=16, pady=6, cursor="hand2",
                  font=("Microsoft YaHei", 10),
                  command=self.on_like).pack(side="left")
        tk.Button(acts, text="♥  赞赏作者", bg=ACCENT, fg="#1a1c22",
                  activebackground="#f0c457", activeforeground="#1a1c22",
                  relief="flat", bd=0, padx=18, pady=6, cursor="hand2",
                  font=("Microsoft YaHei", 10),
                  command=self.show_donate).pack(side="right")
        self.likecount = tk.Label(root, text="", bg=BG, fg="#6a7280",
                                  font=("Microsoft YaHei", 8))
        self.likecount.pack(anchor="w", padx=22, pady=(3, 0))

        self.foot = tk.Label(root, text="", bg=BG, fg="#6a7280",
                             font=("Microsoft YaHei", 8))
        self.foot.pack(pady=(2, 8))

        self.liked = False
        st = load_likes_state()
        self.liked = st["liked"]
        self.likecount.config(text="已有 %d 人点赞" % st["global"])
        # 后台拉取云端真实总数（不阻塞界面）；拿到后更新显示
        threading.Thread(target=self._refresh_cloud_likes,
                        daemon=True).start()

        root.bind("<Escape>", lambda e: root.destroy())
        root.bind("<F5>", lambda e: self.rebuild())

        self.rebuild()

        # （档位改为文字标签，不再需要画布滚动）

    def key(self, i):
        def h(e):
            if isinstance(e.widget, (tk.Entry, ttk.Combobox)):
                return
            if i <= len(self.rates):
                self.apply(self.rates[i - 1])
        return h

    def on_display(self, event):
        idx = event.widget.current()
        if 0 <= idx < len(self.displays):
            self.name = self.displays[idx][0]
            self.rebuild()

    def on_res(self, event):
        idx = self.rcb.current()
        if 0 <= idx < len(self.res_list):
            self.target_res = self.res_list[idx]
            self.build_rates()

    def rebuild(self):
        self.modes = get_modes(self.name)
        self.res_list = list(self.modes.keys())
        dm = get_current(self.name)
        cur = (dm.dmPelsWidth, dm.dmPelsHeight) if dm else None
        self.target_res = cur if cur in self.modes else (
            self.res_list[0] if self.res_list else None)

        labels = []
        for r in self.res_list:
            t = "%d × %d" % r
            if r == cur:
                t += "   （当前）"
            elif r == self.res_list[0]:
                t += "   （原生）"
            labels.append(t)
        self.rcb.configure(values=labels)
        # 展开高度跟随实际数量（默认只显示极少几行，容易被误认为"只有几个选项"）
        self.rcb.configure(height=min(max(len(labels), 4), 20))
        self.rcount.config(text="共 %d 个" % len(labels))
        if self.target_res in self.res_list:
            self.rcb.current(self.res_list.index(self.target_res))
        self.build_rates()

    def build_rates(self):
        for w in self.tags.winfo_children():
            w.destroy()
        self.buttons.clear()
        self.rates = self.modes.get(self.target_res, [])

        dm = get_current(self.name)
        cur = (dm.dmPelsWidth, dm.dmPelsHeight) if dm else None
        changed = (self.target_res != cur)

        self.hint.config(text="切换后应用新分辨率" if changed else "")
        if not self.rates:
            tk.Label(self.tags, text="该分辨率下未检测到可用刷新率", bg=BG,
                     fg=MUTED, font=("Microsoft YaHei", 10)).pack(anchor="w")
            self.max_lbl.config(text="-- Hz")
            self.max_btn.config(text="⚡  一键最高")
            self.foot.config(text="F5 重新检测      Esc 关闭")
            self.refresh_state()
            return

        mx = max(self.rates)
        self.max_lbl.config(text="%d Hz" % mx)
        self.max_btn.config(text="⚡  一键最高 (%dHz)" % mx)

        for hz in self.rates:
            if hz == 50:
                continue   # 50Hz 易误点且无意义，引导用自定义输入
            tag, desc = classify(hz, self.rates)
            color = STYLES.get(tag, "#6e7681")
            t = tk.Label(self.tags, text="%d Hz" % hz, bg=CARD2, fg=FG,
                         relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                         font=("Microsoft YaHei", 10, "bold"))
            t.pack(side="left", padx=(0, 8), pady=4)
            t.bind("<Button-1>", lambda e, x=hz: self.apply(x))
            self.buttons[hz] = (t, color)

        self.foot.config(text="F5 重新检测      Esc 关闭")
        self.refresh_state()
        self.root.update_idletasks()
        self.center()

        # （档位改为文字标签，渲染见 build_rates）

    def center(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        # 窗口比屏幕还高时贴顶，避免底部按钮被任务栏挡住
        if h > sh - 40:
            y = 0
        self.root.geometry("+%d+%d" % (x, y))

    def show_donate(self):
        win = tk.Toplevel(self.root)
        win.title("赞赏作者")
        win.configure(bg="#ffffff")
        win.resizable(False, False)
        try:
            img = tk.PhotoImage(file=res_path("donate_qr.png"))
            win.img = img   # 挂在窗口上，防止图片对象被回收
            tk.Label(win, image=img, bg="#ffffff").pack(padx=34, pady=(26, 10))
        except Exception:
            tk.Label(win, text="赞赏码加载失败", bg="#ffffff", fg="#333333",
                     font=("Microsoft YaHei", 10)).pack(padx=44, pady=34)
        tk.Label(win, text="微信扫一扫  ·  感谢您的支持！让我更有动力！",
                 bg="#ffffff", fg="#333333",
                 font=("Microsoft YaHei", 11)).pack(pady=(0, 22))
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))

    def refresh_state(self):
        dm = get_current(self.name)
        if dm is None:
            self.cur_line.config(text="读取失败", fg=BAD)
            return
        now = int(dm.dmDisplayFrequency)
        W, H = dm.dmPelsWidth, dm.dmPelsHeight
        # 当前刷新率用颜色区分，让用户一眼看到状态
        if now >= 144:
            col, word = GOOD, "满血流畅"
        elif now >= 100:
            col, word = "#79c0ff", "高刷流畅"
        elif now >= 60:
            col, word = "#d29922", "标准显示"
        else:
            col, word = MUTED, "低刷新率"
        self.cur_line.config(
            text="您当前的显示器刷新率是  %d Hz  （%d×%d · %s）"
                 % (now, W, H, word), fg=col)
        cur = (W, H)
        for hz, item in self.buttons.items():
            t, color = item
            on = (hz == now and self.target_res == cur)
            t.config(bg=color if on else CARD2,
                     fg="#ffffff" if on else FG)

    def _refresh_cloud_likes(self):
        """后台拉取云端真实总数并更新底部显示（不阻塞界面）。"""
        url = cloud_likes_url()
        if not url:
            return
        c = fetch_cloud_likes(url)
        if c is None:
            return
        st = load_likes_state()
        st["global"] = c
        save_likes_state(st)
        try:
            self.root.after(0, lambda: self.likecount.config(
                text="已有 %d 人点赞" % c))
        except Exception:
            pass

    def on_like(self):
        st = load_likes_state()
        url = cloud_likes_url()
        if self.liked:
            # 已点过：顺手刷新一下云端最新数
            if url:
                c = fetch_cloud_likes(url)
                if c is not None:
                    st["global"] = c
                    save_likes_state(st)
            n = st["global"]
            messagebox.showinfo(
                "感谢支持",
                "您已经点过赞啦，感谢！\n\n当前已有 %d 人点赞" % n)
            return
        # 首次点赞：云端 +1（未配置/离线时本机兜底 +1）
        new_n = bump_cloud_likes(url) if url else None
        if new_n is None:
            new_n = st["global"] + 1
        st["liked"] = True
        st["global"] = new_n
        save_likes_state(st)
        self.liked = True
        self.likecount.config(text="已有 %d 人点赞" % new_n)
        messagebox.showinfo(
            "感谢支持",
            "感谢您的点赞，让我更有动力！\n\n"
            "当前已有 %d 人点赞\n\n"
            "如果这个小工具帮到了你，也欢迎扫码赞赏作者 ♥" % new_n)

    def apply(self, hz):
        w, h = self.target_res
        ok, msg = set_mode(self.name, w, h, hz)
        if ok:
            dm = get_current(self.name)
            cur = int(dm.dmDisplayFrequency) if dm else hz
            self.status.config(
                text="✅ %s\n您当前的显示器刷新率已变为  %d Hz"
                     % (msg, cur), fg=GOOD)
            self.rebuild()
        else:
            self.status.config(text="❌ %s" % msg, fg=BAD)
            self.refresh_state()
            messagebox.showerror("切换失败", msg)

    def apply_custom(self):
        raw = self.var.get().strip()
        if not raw.isdigit():
            self.status.config(text="请输入正整数 Hz", fg=BAD)
            return
        self.apply(int(raw))

    def apply_max(self):
        """一键切到当前分辨率下本机支持的最高刷新率。"""
        if not self.rates:
            self.status.config(text="未检测到可用档位", fg=BAD)
            return
        self.apply(max(self.rates))


def alert(msg):
    try:
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("切换失败", msg)
        r.destroy()
    except Exception:
        pass


def cli_list():
    for name, desc, isp in list_displays():
        print("%s%s" % (desc, "  [主显示器]" if isp else ""))
        dm = get_current(name)
        cur = (dm.dmPelsWidth, dm.dmPelsHeight) if dm else None
        cur_hz = int(dm.dmDisplayFrequency) if dm else 0
        modes = get_modes(name)
        print("  当前: %s @ %dHz" % ("x".join(map(str, cur)) if cur else "?", cur_hz))
        print("  共 %d 个分辨率：" % len(modes))
        for res, rates in modes.items():
            mark = "  <- 当前" if res == cur else ""
            native = "  (原生)" if res == list(modes)[0] else ""
            print("    %4d x %-5d%s%s" % (res[0], res[1], native, mark))
            for hz in rates:
                tag, d = classify(hz, rates)
                m = "   <- 当前" if (res == cur and hz == cur_hz) else ""
                print("          %4d Hz  %-4s %s%s" % (hz, tag, d, m))


def main():
    args = sys.argv[1:]
    if not args:
        root = tk.Tk()
        App(root)
        root.mainloop()
        return

    a = args[0].lower()
    if a in ("list", "-l", "--list", "?"):
        cli_list()
        return

    name = primary_display()
    if len(args) > 1:
        for n, d, _ in list_displays():
            if args[1].lower() in n.lower():
                name = n
                break

    # 1920x1080@144 / 1920x1080 / 144
    if "@" in a:
        res, _, hz = a.partition("@")
        try:
            w, h = [int(x) for x in res.replace("*", "x").split("x")]
        except ValueError:
            print("格式应为 宽x高@刷新率，例如 1920x1080@144")
            return
        if not hz.isdigit():
            print("刷新率部分应为数字")
            return
        ok, msg = set_mode(name, w, h, int(hz))
    elif "x" in a:
        try:
            w, h = [int(x) for x in a.split("x")]
        except ValueError:
            print("格式应为 宽x高，例如 1920x1080")
            return
        ok, msg = set_mode(name, w, h)
    elif a.isdigit():
        ok, msg = set_mode(name, None, None, int(a))
    else:
        print(__doc__)
        return

    print(msg)
    if not ok:
        alert(msg)


if __name__ == "__main__":
    main()
