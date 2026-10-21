"""Limbus Company 自動戰鬥：看遊戲畫面，輪到選技能時自動按 P + Enter，VICTORY 後停下。

判斷方式（擷取遊戲視窗畫面做影像比對，樣本在 limbus_templates/）：
    右上角齒輪       → 戰鬥進行中
    右上角「«」按鈕   → 輪到選技能（這時才送 P + Enter）
    中央 VICTORY 字樣 → 這場打完
    左側面板上方的吊鉤 → 戰鬥中跳出事件 / 選項（一般關卡、鏡像迷宮都有），立刻暫停並提示
    隊伍畫面「開始戰鬥」按鈕 → （有勾選時）按 Enter 沿用目前隊伍開戰；只比對按鈕外框，文字區遮掉，不受語言 / 漢化影響
    戰鬥中齒輪消失超過設定秒數且不是 VICTORY → 可能打輸或跳出選項，暫停並發出提示音，回到戰鬥畫面後自動繼續

不同解析度：
    自動校準 → 第一次看到戰鬥 / 隊伍畫面時用 0.5～1.6 倍找出介面縮放倍率，依視窗尺寸記住
    重新取樣 → 玩家在自己的畫面上框出元素，存成自訂樣本（優先使用，不再縮放）

提示音、校準結果、設定記在 %APPDATA%/LimbusAutoBattle/settings.json；自訂樣本在同資料夾的 templates/。

F8：開始 / 停止　Ctrl+Y：暫停 / 繼續
"""
import base64
import json
import os
import queue
import threading
import time
import tkinter as tk
import winsound
from tkinter import ttk, messagebox, filedialog

import cv2
import numpy as np

from keysender import *  # noqa: F401,F403
from keysender import resource_path

GAME_TITLE = "LimbusCompany"
REF_WIDTH = 1920  # 樣本擷取時的視窗寬度；其他解析度會先縮放到這個寬度再比對
THRESHOLDS = {"gear": 0.70, "turn": 0.85, "victory": 0.75, "event": 0.80, "start": 0.80}
START_RETRY = 3.0   # 按了 Enter 隊伍畫面沒變的話，隔多久再按
START_MAX_TRIES = 5
TICK = 0.3          # 每隔幾秒看一次畫面
RESEND_AFTER = 2.5  # 送出後選技能畫面還在的話，隔多久再送一次

WM_APP_PAUSE_KEY_ON, WM_APP_PAUSE_KEY_OFF = 0x8001, 0x8002
PAUSE_HOTKEY_ID, MOD_CONTROL, VK_Y = 2, 0x0002, 0x59

gdi32 = ctypes.WinDLL("gdi32")
user32.FindWindowW.restype = wt.HWND
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]

# ---------------------------------------------------------------- 擷取與辨識


def find_game():
    return user32.FindWindowW(None, GAME_TITLE)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
kernel32.GetTickCount.restype = wt.DWORD


def user_input_since(hwnd, tick):
    """遊戲在前景、而且使用者在 tick（GetTickCount）之後動過滑鼠或鍵盤 → 視為正在手動操作。"""
    if user32.GetForegroundWindow() != hwnd:
        return False
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return False
    return ((info.dwTime - tick) & 0xFFFFFFFF) < 0x80000000 and info.dwTime != tick


def capture_bgra(hwnd):
    """用 PrintWindow 擷取視窗內容（被其他視窗蓋住也拍得到），回傳 BGRA 影像；失敗回傳 None。"""
    rc = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    w, h = rc.right, rc.bottom
    if w <= 0 or h <= 0:
        return None
    src = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    try:
        gdi32.SelectObject(mem, bmp)
        user32.PrintWindow(hwnd, mem, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        buf = ctypes.create_string_buffer(w * h * 4)
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, src)
    return np.frombuffer(buf, np.uint8).reshape(h, w, 4)


def capture_gray(hwnd):
    bgra = capture_bgra(hwnd)
    return None if bgra is None else cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)


def normalize_width(img):
    """縮放到 REF_WIDTH 寬，回傳 (影像, 縮放倍率)。所有比對都在這個尺寸上做。"""
    h, w = img.shape[:2]
    if w == REF_WIDTH:
        return img, 1.0
    f = REF_WIDTH / w
    return cv2.resize(img, (REF_WIDTH, round(h * f)), interpolation=cv2.INTER_AREA), f


def load_png(path):
    # cv2.imread 不吃中文路徑，改用 imdecode
    if not os.path.isfile(path):
        return None
    return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_GRAYSCALE)


APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LimbusAutoBattle")
USER_TEMPLATE_DIR = os.path.join(APP_DIR, "templates")
TEMPLATE_INFO = {  # 名稱 → (說明, 在畫面哪裡)
    "gear": ("戰鬥中：右上角的齒輪按鈕", "右上角"),
    "turn": ("選技能回合：右上角的「«」按鈕", "右上角"),
    "victory": ("VICTORY 字樣", "畫面中央"),
    "event": ("選項畫面：左側面板上方的吊鉤", "左上方"),
    "start": ("隊伍畫面：開始戰鬥按鈕", "右下角"),
}
CALIB_ANCHORS = ("gear", "turn", "event", "start")  # 用來校準的樣本（固定在角落、出現頻繁）
CALIB_SCALES = [round(1 + 0.03 * i, 2) for i in range(-17, 21)]  # 0.49～1.60，一定包含 1.00
CALIB_COARSE_MIN = 0.55  # 粗找（半解析度）的候選門檻
CALIB_MIN_SCORE = 0.85   # 細找後要達到這個分數才採用
CALIB_RETRY = 2.0  # 還沒校準時，每隔幾秒試一次（避免每張畫面都做大範圍搜尋）


def search_regions(gray, k=1.0):
    """各樣本的搜尋範圍 {名稱: (左上 x, 左上 y, 影像)}；k = 介面縮放倍率，倍率大時範圍跟著放大。"""
    h, w = gray.shape
    s = max(1.0, k)

    def box(x0, y0, x1, y1):
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
        return x0, y0, gray[y0:y1, x0:x1]

    cx, cy = w / 2, h / 2
    top_right = box(w - 450 * s, 0, w, 150 * s)
    return {
        "gear": top_right,
        "turn": top_right,
        "victory": box(cx - 450 * s, cy - 220 * s, cx + 450 * s, cy + 220 * s),
        "event": box(200, 0, 850 * s, 280 * s),
        "start": box(w - 480 * s, h - 320 * s, w, h),
    }


class Detector:
    def __init__(self, calibration=None, on_calibrated=None):
        self.calibration = dict(calibration or {})  # "寬x高" → 介面縮放倍率
        self.on_calibrated = on_calibrated
        self._last_calib_try = -CALIB_RETRY
        self.reload()

    def reload(self):
        """載入樣本；玩家自己取樣的（USER_TEMPLATE_DIR）優先。"""
        self.templates, self.masks, self.custom = {}, {}, set()
        for name in THRESHOLDS:
            user = load_png(os.path.join(USER_TEMPLATE_DIR, name + ".png"))
            if user is not None:
                self.templates[name], self.masks[name] = user, None
                self.custom.add(name)
            else:
                self.templates[name] = load_png(resource_path(f"limbus_templates/{name}.png"))
                self.masks[name] = load_png(resource_path(f"limbus_templates/{name}_mask.png"))

    def _match(self, region, name, scales):
        """在 region 裡用各種縮放找樣本，回傳 (最高分, 樣本中心在 region 內的座標)。"""
        tpl, mask = self.templates[name], self.masks[name]
        best, center = -1.0, (0, 0)
        for scale in scales:
            if scale == 1.0:
                t, m = tpl, mask
            else:
                interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                t = cv2.resize(tpl, None, fx=scale, fy=scale, interpolation=interp)
                m = None if mask is None else cv2.resize(mask, (t.shape[1], t.shape[0]), interpolation=cv2.INTER_NEAREST)
            if min(t.shape) < 8 or t.shape[0] > region.shape[0] or t.shape[1] > region.shape[1]:
                continue
            res = cv2.matchTemplate(region, t, cv2.TM_CCOEFF_NORMED, mask=m)
            res[~np.isfinite(res)] = -1
            _, score, _, (x, y) = cv2.minMaxLoc(res)
            if score > best:
                best, center = float(score), (x + t.shape[1] / 2, y + t.shape[0] / 2)
        return best, center

    def calibrate(self, ngray, key):
        """找介面縮放倍率：先用半解析度粗找候選，再用原解析度細找到 0.01。
        找到可信的結果就記下來並回傳，否則回傳 None。"""
        anchors = [n for n in CALIB_ANCHORS if n not in self.custom]
        if not anchors:
            return None
        regions = search_regions(ngray, max(CALIB_SCALES))
        candidates = []
        for name in anchors:
            region = regions[name][2]
            half = cv2.resize(region, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            best = max((self._match(half, name, (k * 0.5,))[0], k) for k in CALIB_SCALES)
            if best[0] >= CALIB_COARSE_MIN:
                candidates.append((best[0], best[1], name))
        best_score, best_k, best_name = -1.0, None, None
        for _, k0, name in sorted(candidates, reverse=True)[:2]:
            region = regions[name][2]
            for k in np.arange(k0 - 0.04, k0 + 0.041, 0.01):
                score, _ = self._match(region, name, (float(k),))
                if score > best_score:
                    best_score, best_k, best_name = score, float(k), name
        if best_score < CALIB_MIN_SCORE:
            return None
        best_k = round(best_k, 2)
        self.calibration[key] = best_k
        if self.on_calibrated:
            self.on_calibrated(key, best_k, best_name, best_score)
        return best_k

    def analyse(self, gray):
        """回傳 (是否看到各元素, 各元素分數, 「開始戰鬥」按鈕在原始畫面的座標)。"""
        h0, w0 = gray.shape
        key = f"{w0}x{h0}"
        ngray, f = normalize_width(gray)
        k = self.calibration.get(key)
        if k is None and time.monotonic() - self._last_calib_try >= CALIB_RETRY:
            self._last_calib_try = time.monotonic()
            k = self.calibrate(ngray, key)
        k = k or 1.0
        regions = search_regions(ngray, k)
        scores, start_pos = {}, None
        for name, (ox, oy, region) in regions.items():
            base = 1.0 if name in self.custom else k  # 自訂樣本本來就是玩家畫面的大小
            scores[name], (px, py) = self._match(region, name, (base, base * 0.97, base * 1.03))
            if name == "start":
                start_pos = ((ox + px) / f, (oy + py) / f)
        found = {n: v >= THRESHOLDS[n] for n, v in scores.items()}
        found["black"] = float(ngray.mean()) < 3  # 視窗最小化時會拍到全黑
        return found, scores, start_pos


def scene_name(found):
    if found["black"]:
        return "拍不到畫面（遊戲最小化了？）"
    if found["victory"]:
        return "VICTORY"
    if found["event"]:
        return "事件／選項畫面"
    if found["start"]:
        return "隊伍編成畫面"
    if found["turn"]:
        return "選技能回合"
    if found["gear"]:
        return "戰鬥中"
    return "非戰鬥畫面"


# ---------------------------------------------------------------- 重新取樣視窗


class ResampleDialog(tk.Toplevel):
    """擷取目前遊戲畫面，讓玩家框出要辨識的元素，存成自訂樣本。"""

    MAX_W, MAX_H = 1280, 720

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("重新取樣")
        self.resizable(False, False)
        self.transient(app.root)
        self.choice = tk.StringVar(value=TEMPLATE_INFO["gear"][0])
        self.hint = tk.StringVar()
        self.rect = None
        self.drag_from = None

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="要取樣的元素：").pack(side="left")
        box = ttk.Combobox(top, textvariable=self.choice, state="readonly", width=34,
                           values=[v[0] for v in TEMPLATE_INFO.values()])
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _: self._show_region())
        ttk.Button(top, text="重新擷取畫面", command=self.capture).pack(side="left", padx=8)
        ttk.Label(self, textvariable=self.hint, foreground="#1a5fb4", padding=(8, 0)).pack(anchor="w")

        self.canvas = tk.Canvas(self, highlightthickness=0, cursor="crosshair", bg="black")
        self.canvas.pack(padx=8, pady=6)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="儲存這個樣本", command=self.save).pack(side="left")
        ttk.Button(bottom, text="關閉", command=self.destroy).pack(side="right")
        self.capture()

    def name(self):
        return next(n for n, v in TEMPLATE_INFO.items() if v[0] == self.choice.get())

    def capture(self):
        hwnd = find_game()
        bgra = capture_bgra(hwnd) if hwnd else None
        if bgra is None:
            messagebox.showwarning("重新取樣", "擷取不到遊戲畫面，請確認遊戲開著且沒有最小化", parent=self)
            self.destroy()
            return
        self.bgr, _ = normalize_width(cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR))
        self.gray = cv2.cvtColor(self.bgr, cv2.COLOR_BGR2GRAY)
        h, w = self.gray.shape
        self.disp = min(self.MAX_W / w, self.MAX_H / h, 1.0)
        shown = cv2.resize(self.bgr, (round(w * self.disp), round(h * self.disp)), interpolation=cv2.INTER_AREA)
        self.photo = tk.PhotoImage(data=base64.b64encode(cv2.imencode(".png", shown)[1].tobytes()))
        self.canvas.config(width=shown.shape[1], height=shown.shape[0])
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.rect = None
        self._show_region()

    def _show_region(self):
        """用虛線標出這個元素的搜尋範圍，框的時候要框在裡面。"""
        self.canvas.delete("region")
        ox, oy, region = search_regions(self.gray)[self.name()]
        d = self.disp
        self.canvas.create_rectangle(ox * d, oy * d, (ox + region.shape[1]) * d, (oy + region.shape[0]) * d,
                                     outline="#ffd60a", dash=(6, 4), width=2, tags="region")
        where = TEMPLATE_INFO[self.name()][1]
        self.hint.set(f"請先切到有「{self.choice.get()}」的遊戲畫面，再用滑鼠拖曳框住它（在{where}的黃色虛線範圍內）")

    def _on_press(self, e):
        self.drag_from = (e.x, e.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff3b30", width=2)

    def _on_drag(self, e):
        if self.rect and self.drag_from:
            self.canvas.coords(self.rect, *self.drag_from, e.x, e.y)

    def save(self):
        if not self.rect:
            messagebox.showinfo("重新取樣", "請先在畫面上拖曳框出元素", parent=self)
            return
        x0, y0, x1, y1 = (v / self.disp for v in self.canvas.coords(self.rect))
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        if x1 - x0 < 12 or y1 - y0 < 12:
            messagebox.showwarning("重新取樣", "框的範圍太小了，請框大一點", parent=self)
            return
        name = self.name()
        ox, oy, region = search_regions(self.gray)[name]
        if x0 < ox or y0 < oy or x1 > ox + region.shape[1] or y1 > oy + region.shape[0]:
            messagebox.showwarning("重新取樣", "框的位置要在黃色虛線範圍內，程式只會在那裡找這個元素", parent=self)
            return
        os.makedirs(USER_TEMPLATE_DIR, exist_ok=True)
        cv2.imencode(".png", self.gray[y0:y1, x0:x1])[1].tofile(os.path.join(USER_TEMPLATE_DIR, name + ".png"))
        self.app.on_templates_changed(f"已儲存自訂樣本：{TEMPLATE_INFO[name][0]}")
        messagebox.showinfo("重新取樣", f"已儲存「{TEMPLATE_INFO[name][0]}」。\n可以繼續取樣其他元素，或關閉這個視窗。",
                            parent=self)


# ---------------------------------------------------------------- 提示音

SOUNDS = {  # 種類 → (顯示名稱, 預設檔)
    "alert": ("輸了＆跳出選項", "sounds/alert.mp3"),
    "victory": ("戰鬥勝利（結束）", "sounds/victory.mp3"),
}
SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LimbusAutoBattle", "settings.json")

winmm = ctypes.WinDLL("winmm")
winmm.mciSendStringW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.UINT, wt.HANDLE]


def mci(command):
    buf = ctypes.create_unicode_buffer(256)
    return winmm.mciSendStringW(command, buf, 256, None)


def play_sound(path):
    """用 Windows 內建的 MCI 播放 mp3 / wav，不需要額外套件；同時只播一個。只能在主執行緒呼叫。"""
    mci("close lbsound")
    if mci(f'open "{path}" type mpegvideo alias lbsound'):
        return False
    return mci("play lbsound") == 0


def stop_sound():
    mci("close lbsound")


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return {}


def save_settings(updates):
    """只更新傳進來的欄位，其他設定（例如校準結果）保留。"""
    data = load_settings()
    data.update(updates)
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except OSError:
        pass

# ---------------------------------------------------------------- GUI


class App:
    def __init__(self, root):
        self.root = root
        root.title("Limbus Company 自動戰鬥")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.worker = None
        self.hotkey_tid = 0
        self.detector = Detector(load_settings().get("calibration", {}),
                                 on_calibrated=lambda *a: self.events.put(("calibrated", a)))
        self.calib_var = tk.StringVar()

        self.seq_var = tk.StringVar(value="p{ENTER}")
        self.hold_var = tk.StringVar(value="50")
        self.send_var = tk.StringVar(value="bg")
        self.alert_var = tk.StringVar(value="25")  # EGO 動畫約 15 秒看不到齒輪，要留餘裕
        all_settings = load_settings()
        settings = all_settings.get("sounds", {})
        self.auto_start_var = tk.BooleanVar(value=all_settings.get("auto_start", False))
        self.auto_start = self.auto_start_var.get()  # 給背景執行緒讀的副本
        self.sound_enabled = {}
        self.sound_path = {}  # None = 用預設檔
        for kind in SOUNDS:
            conf = settings.get(kind, {})
            self.sound_enabled[kind] = tk.BooleanVar(value=conf.get("enabled", True))
            path = conf.get("path")
            self.sound_path[kind] = path if path and os.path.isfile(path) else None
        self.sound_label = {}
        self.topmost_var = tk.BooleanVar(value=False)
        self.scene_var = tk.StringVar(value="—")
        self.status_var = tk.StringVar(value="進遊戲後按「開始」或 F8；執行中按 Ctrl+Y 暫停")

        pad = {"padx": 6, "pady": 4}
        f = ttk.Frame(root, padding=10)
        f.grid()

        ttk.Label(f, text="隊伍畫面").grid(row=0, column=0, sticky="w", **pad)
        ttk.Checkbutton(f, text="自動按「開始戰鬥」（沿用目前選好的隊伍）", variable=self.auto_start_var,
                        command=self._on_auto_start).grid(row=0, column=1, columnspan=3, sticky="w", **pad)

        ttk.Label(f, text="選技能時按").grid(row=1, column=0, sticky="w", **pad)
        self.seq_entry = ttk.Entry(f, textvariable=self.seq_var, width=16)
        self.seq_entry.grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(f, text="每個鍵按多久（毫秒）").grid(row=1, column=2, sticky="e", **pad)
        self.hold_spin = ttk.Spinbox(f, textvariable=self.hold_var, from_=1, to=1000, increment=10, width=8)
        self.hold_spin.grid(row=1, column=3, sticky="w", **pad)

        ttk.Label(f, text="送鍵方式").grid(row=2, column=0, sticky="nw", **pad)
        sends = ttk.Frame(f)
        sends.grid(row=2, column=1, columnspan=3, sticky="w", **pad)
        self.send_bg = ttk.Radiobutton(sends, text="背景傳送（不搶焦點）", variable=self.send_var, value="bg")
        self.send_bg.pack(anchor="w")
        self.send_fg = ttk.Radiobutton(sends, text="前景模擬（背景沒反應時改用這個，會切到遊戲視窗）",
                                       variable=self.send_var, value="fg")
        self.send_fg.pack(anchor="w")

        ttk.Label(f, text="戰鬥畫面消失").grid(row=3, column=0, sticky="w", **pad)
        alert_row = ttk.Frame(f)
        alert_row.grid(row=3, column=1, columnspan=3, sticky="w", **pad)
        self.alert_spin = ttk.Spinbox(alert_row, textvariable=self.alert_var, from_=4, to=120, increment=1, width=6)
        self.alert_spin.pack(side="left")
        ttk.Label(alert_row, text="秒就暫停並提示（打輸、跳出選項時）").pack(side="left", padx=4)

        ttk.Label(f, text="提示音").grid(row=4, column=0, sticky="nw", **pad)
        sounds = ttk.Frame(f)
        sounds.grid(row=4, column=1, columnspan=3, sticky="w", **pad)
        for r, (kind, (title, _)) in enumerate(SOUNDS.items()):
            ttk.Checkbutton(sounds, text=title, width=16, variable=self.sound_enabled[kind],
                            command=self.save_sound_settings).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Button(sounds, text="▶ 試聽", width=7,
                       command=lambda k=kind: self.preview_sound(k)).grid(row=r, column=1, padx=2)
            ttk.Button(sounds, text="更換…", width=6,
                       command=lambda k=kind: self.change_sound(k)).grid(row=r, column=2, padx=2)
            ttk.Button(sounds, text="預設", width=5,
                       command=lambda k=kind: self.reset_sound(k)).grid(row=r, column=3, padx=2)
            self.sound_label[kind] = ttk.Label(sounds, foreground="gray")
            self.sound_label[kind].grid(row=r, column=4, sticky="w", padx=6)
            self._update_sound_label(kind)

        ttk.Label(f, text="辨識").grid(row=5, column=0, sticky="nw", **pad)
        calib = ttk.Frame(f)
        calib.grid(row=5, column=1, columnspan=3, sticky="w", **pad)
        ttk.Label(calib, textvariable=self.calib_var, foreground="gray").pack(anchor="w")
        calib_btns = ttk.Frame(calib)
        calib_btns.pack(anchor="w", pady=(3, 0))
        self.recalib_btn = ttk.Button(calib_btns, text="重新校準", command=self.reset_calibration)
        self.recalib_btn.pack(side="left")
        self.resample_btn = ttk.Button(calib_btns, text="重新取樣…", command=lambda: ResampleDialog(self))
        self.resample_btn.pack(side="left", padx=6)
        self.reset_tpl_btn = ttk.Button(calib_btns, text="恢復預設樣本", command=self.reset_templates)
        self.reset_tpl_btn.pack(side="left")
        self._update_calib_label()

        bar = ttk.Frame(f)
        bar.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.start_btn = ttk.Button(bar, text="開始 (F8)", command=self.toggle, width=14)
        self.start_btn.pack(side="left", padx=6)
        self.pause_btn = ttk.Button(bar, text="暫停 (Ctrl+Y)", command=self.toggle_pause, width=14)
        self.pause_btn.pack(side="left", padx=6)
        self.pause_btn.state(["disabled"])
        self.test_btn = ttk.Button(bar, text="測試辨識", command=self.test_detect)
        self.test_btn.pack(side="left", padx=6)
        ttk.Checkbutton(bar, text="視窗置頂", variable=self.topmost_var,
                        command=lambda: root.attributes("-topmost", self.topmost_var.get())).pack(side="left", padx=6)

        scene = ttk.Frame(f)
        scene.grid(row=7, column=0, columnspan=4, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(scene, text="目前畫面：").pack(side="left")
        ttk.Label(scene, textvariable=self.scene_var, foreground="#c01c28").pack(side="left")

        log_frame = ttk.Frame(f)
        log_frame.grid(row=8, column=0, columnspan=4, sticky="we", padx=6, pady=(6, 0))
        self.log_box = tk.Listbox(log_frame, height=9, width=70, activestyle="none")
        self.log_box.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        sb.pack(side="right", fill="y")
        self.log_box.config(yscrollcommand=sb.set)

        ttk.Label(f, textvariable=self.status_var, foreground="#1a5fb4").grid(
            row=9, column=0, columnspan=4, sticky="w", padx=6, pady=(6, 0))

        self._inputs = [self.seq_entry, self.hold_spin, self.send_bg, self.send_fg, self.alert_spin,
                        self.test_btn, self.recalib_btn, self.resample_btn, self.reset_tpl_btn]

        threading.Thread(target=self._hotkey_loop, daemon=True).start()
        self._poll()

    # ---------- 紀錄

    def log(self, text):
        self.log_box.insert("end", f"{time.strftime('%H:%M:%S')}  {text}")
        if self.log_box.size() > 500:
            self.log_box.delete(0)
        self.log_box.see("end")

    # ---------- 提示音設定

    def sound_file(self, kind):
        return self.sound_path[kind] or resource_path(SOUNDS[kind][1])

    def _update_sound_label(self, kind):
        path = self.sound_path[kind]
        self.sound_label[kind].config(text=os.path.basename(path) if path else "（預設）")

    # ---------- 校準 / 取樣

    def _update_calib_label(self):
        cal = self.detector.calibration
        text = ("校準：" + "、".join(f"{k.replace('x', '×')} → {v:.2f} 倍" for k, v in cal.items()) if cal
                else "校準：尚未校準（看到戰鬥或隊伍畫面時會自動校準）")
        if self.detector.custom:
            text += "　｜　自訂樣本：" + "、".join(TEMPLATE_INFO[n][0].split("：")[0] for n in self.detector.custom)
        self.calib_var.set(text)

    def _on_calibrated(self, key, k, name, score):
        save_settings({"calibration": self.detector.calibration})
        self._update_calib_label()
        self.log(f"自動校準完成：{key.replace('x', '×')} 介面縮放 {k:.2f} 倍"
                 f"（依據：{TEMPLATE_INFO[name][0]}，吻合度 {score:.2f}）")

    def reset_calibration(self):
        self.detector.calibration.clear()
        self.detector._last_calib_try = -CALIB_RETRY
        save_settings({"calibration": {}})
        self._update_calib_label()
        self.log("已清除校準結果，下次看到戰鬥或隊伍畫面時會重新校準")

    def on_templates_changed(self, message):
        self.detector.reload()
        self.detector.calibration.clear()  # 樣本換了，倍率重新找
        self.detector._last_calib_try = -CALIB_RETRY
        save_settings({"calibration": {}})
        self._update_calib_label()
        self.log(message)

    def reset_templates(self):
        files = [os.path.join(USER_TEMPLATE_DIR, n + ".png") for n in THRESHOLDS]
        files = [p for p in files if os.path.isfile(p)]
        if not files:
            messagebox.showinfo("Limbus Company 自動戰鬥", "目前沒有自訂樣本，已經是預設樣本了")
            return
        if not messagebox.askyesno("Limbus Company 自動戰鬥", f"要刪除 {len(files)} 個自訂樣本、改回內建樣本嗎？"):
            return
        for path in files:
            os.remove(path)
        self.on_templates_changed("已恢復預設樣本")

    def save_sound_settings(self):
        save_settings({"sounds": {k: {"enabled": self.sound_enabled[k].get(), "path": self.sound_path[k]}
                                  for k in SOUNDS},
                       "auto_start": self.auto_start_var.get()})

    def _on_auto_start(self):
        self.auto_start = self.auto_start_var.get()
        self.save_sound_settings()

    def preview_sound(self, kind):
        if not play_sound(self.sound_file(kind)):
            messagebox.showwarning("Limbus Company 自動戰鬥", f"播放失敗：{self.sound_file(kind)}")

    def change_sound(self, kind):
        path = filedialog.askopenfilename(
            title=f"選擇「{SOUNDS[kind][0]}」提示音",
            filetypes=[("音效檔", "*.mp3 *.wav *.wma *.m4a"), ("所有檔案", "*.*")])
        if not path:
            return
        if not play_sound(path):
            messagebox.showwarning("Limbus Company 自動戰鬥", "這個檔案無法播放，請換 mp3 或 wav 檔")
            return
        self.sound_path[kind] = os.path.normpath(path)
        self._update_sound_label(kind)
        self.save_sound_settings()

    def reset_sound(self, kind):
        self.sound_path[kind] = None
        self._update_sound_label(kind)
        self.save_sound_settings()

    def notify(self, kind):
        if self.sound_enabled[kind].get():
            play_sound(self.sound_file(kind))

    # ---------- 測試辨識

    def test_detect(self):
        hwnd = find_game()
        if not hwnd:
            messagebox.showwarning("Limbus Company 自動戰鬥", "找不到 Limbus Company 的視窗，請先開遊戲")
            return
        gray = capture_gray(hwnd)
        if gray is None:
            self.log("測試辨識：擷取畫面失敗")
            return
        self.detector._last_calib_try = -CALIB_RETRY  # 手動測試時，還沒校準就立刻試
        found, scores, _ = self.detector.analyse(gray)
        self._drain_calibration_events()
        self.scene_var.set(scene_name(found))
        k = self.detector.calibration.get(f"{gray.shape[1]}x{gray.shape[0]}")
        self.log(f"測試辨識：{scene_name(found)}（畫面 {gray.shape[1]}×{gray.shape[0]}，"
                 f"{'縮放 %.2f 倍' % k if k else '尚未校準'}，"
                 f"齒輪 {scores['gear']:.2f}／選技能 {scores['turn']:.2f}／VICTORY {scores['victory']:.2f}／"
                 f"選項 {scores['event']:.2f}／開始戰鬥 {scores['start']:.2f}）")

    def _drain_calibration_events(self):
        """測試辨識是在主執行緒做的，校準事件直接處理掉，紀錄順序才會正確。"""
        rest = []
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "calibrated":
                self._on_calibrated(*data)
            else:
                rest.append((kind, data))
        for item in rest:
            self.events.put(item)

    # ---------- 開始 / 停止 / 暫停

    def running(self):
        return bool(self.worker and self.worker.is_alive())

    def toggle(self):
        if self.running():
            self.stop_event.set()
        else:
            self.start()

    def start(self):
        if not find_game():
            messagebox.showwarning("Limbus Company 自動戰鬥", "找不到 Limbus Company 的視窗，請先開遊戲")
            return
        try:
            actions = parse_sequence(self.seq_var.get())
        except ValueError as e:
            messagebox.showwarning("Limbus Company 自動戰鬥", str(e))
            return
        try:
            hold = max(1, int(self.hold_var.get())) / 1000
            alert_after = max(2.0, float(self.alert_var.get()))
        except ValueError:
            messagebox.showwarning("Limbus Company 自動戰鬥", "按多久、消失秒數都要填數字")
            return
        self.stop_event.clear()
        self.pause_event.clear()
        args = (actions, hold, self.send_var.get(), alert_after)
        self.worker = threading.Thread(target=self._run, args=args, daemon=True)
        self.worker.start()
        self.start_btn.config(text="停止 (F8)")
        self.pause_btn.config(text="暫停 (Ctrl+Y)")
        self.pause_btn.state(["!disabled"])
        self._set_pause_hotkey(True)
        for w in self._inputs:
            w.state(["disabled"])
        self.status_var.set("執行中：等待戰鬥畫面…")
        self.log("開始監看遊戲畫面")

    def toggle_pause(self):
        if not self.running():
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="暫停 (Ctrl+Y)")
            self.status_var.set("執行中")
            self.log("繼續")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="繼續 (Ctrl+Y)")
            self.status_var.set("已暫停，按 Ctrl+Y 繼續")
            self.log("暫停")

    def _set_pause_hotkey(self, on):
        if self.hotkey_tid:
            user32.PostThreadMessageW(self.hotkey_tid, WM_APP_PAUSE_KEY_ON if on else WM_APP_PAUSE_KEY_OFF, 0, 0)

    # ---------- 背景工作：看畫面 → 判斷 → 送鍵

    def _run(self, actions, hold, send_mode, alert_after):
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # 建立訊息佇列，前景模式切視窗需要
        say = lambda text: self.events.put(("log", text))  # noqa: E731
        state = "wait"           # wait：等戰鬥開始　battle：戰鬥中　alert：畫面消失已暫停　after：剛 VICTORY
        missing_since = None
        last_press = 0.0
        last_press_tick = 0
        on_turn = manual_noted = False  # 目前是否停在同一個選技能畫面；是否已提示過手動操作
        presses = battles = 0
        start_tries, last_start_click, start_warned = 0, -START_RETRY, False
        reason = "已停止"
        sender = None
        hwnd = None
        try:
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    missing_since = None
                    self.stop_event.wait(TICK)
                    continue
                if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
                    self.stop_event.wait(0.05)  # 剛按完 Ctrl+Y，等 Ctrl 放開再送鍵
                    continue
                t0 = time.monotonic()
                new_hwnd = find_game()
                if not new_hwnd:
                    self.events.put(("scene", "找不到遊戲視窗"))
                    self.stop_event.wait(1.0)
                    continue
                if new_hwnd != hwnd:
                    hwnd = new_hwnd
                    sender = (ForegroundSender(hwnd, hold, restore=False) if send_mode == "fg"
                              else BackgroundSender(hwnd, hold, game_keys=True, fake_active=True))
                gray = capture_gray(hwnd)
                if gray is None:
                    self.stop_event.wait(TICK)
                    continue
                found, _, start_pos = self.detector.analyse(gray)
                self.events.put(("scene", scene_name(found)))
                now = time.monotonic()
                in_battle_ui = found["gear"] or found["turn"]
                if not found["turn"]:
                    on_turn = False

                if not found["start"]:
                    start_tries, start_warned = 0, False

                if state == "wait" and found["start"] and self.auto_start and not in_battle_ui:
                    if start_tries < START_MAX_TRIES and now - last_start_click >= START_RETRY:
                        if sender.begin():
                            try:
                                sender.vk(0x0D)  # 隊伍畫面按 Enter = 開始戰鬥
                            finally:
                                sender.end()
                            start_tries += 1
                            last_start_click = time.monotonic()
                            say("隊伍畫面：已按 Enter 開始戰鬥" + (f"（第 {start_tries} 次）" if start_tries > 1 else ""))
                    elif start_tries >= START_MAX_TRIES and not start_warned:
                        start_warned = True
                        say(f"⚠ 按了 {START_MAX_TRIES} 次「開始戰鬥」畫面都沒變（人數不足？背景按鍵沒效？），請手動處理")
                        self.events.put(("sound", "alert"))

                elif state == "wait":
                    if in_battle_ui:
                        battles += 1
                        state, missing_since = "battle", None
                        say(f"偵測到第 {battles} 場戰鬥，開始自動")
                        self.events.put(("status", f"戰鬥中（第 {battles} 場）"))

                elif state in ("battle", "alert"):
                    if found["victory"]:
                        say(f"第 {battles} 場 VICTORY！（共 {presses} 回合）")
                        presses = 0  # 回合數每場重新計算
                        self.events.put(("sound", "victory"))
                        state = "after"
                        self.events.put(("status", "已勝利，等待下一場戰鬥…"))
                    elif in_battle_ui:
                        if state == "alert":
                            say("回到戰鬥畫面，繼續自動")
                            self.events.put(("status", f"戰鬥中（第 {battles} 場）"))
                        state, missing_since = "battle", None
                        resend = on_turn and now - last_press >= RESEND_AFTER
                        if resend and user_input_since(hwnd, last_press_tick):
                            resend = False  # 按完後玩家在遊戲裡動了滑鼠 / 鍵盤（例如手動選 EGO），不要打斷
                            if not manual_noted:
                                manual_noted = True
                                say("偵測到你在手動操作，這回合不再自動重按")
                        if found["turn"] and (not on_turn or resend):
                            if sender.begin():
                                try:
                                    for kind, value in actions:
                                        if kind == "wait":
                                            self.stop_event.wait(value)
                                        elif kind == "vk":
                                            sender.vk(value)
                                        else:
                                            sender.char(value)
                                finally:
                                    sender.end()
                                last_press = time.monotonic()
                                last_press_tick = kernel32.GetTickCount()
                                if resend:
                                    say(f"第 {battles} 場第 {presses} 回合：畫面沒變，再按一次")
                                else:
                                    presses += 1
                                    on_turn, manual_noted = True, False
                                    say(f"第 {battles} 場第 {presses} 回合：已送出按鍵")
                            else:
                                say("無法切換到遊戲視窗，這回合略過")
                    elif state == "battle" and found["event"]:
                        state = "alert"
                        say("⚠ 跳出事件／選項，已暫停，選完回到戰鬥畫面會自動繼續")
                        self.events.put(("status", "⚠ 需要手動選擇，回到戰鬥畫面後自動繼續"))
                        self.events.put(("sound", "alert"))
                    elif state == "battle":
                        missing_since = missing_since or now
                        if now - missing_since >= alert_after:
                            state = "alert"
                            say(f"⚠ 戰鬥畫面消失超過 {alert_after:g} 秒（打輸或跳出選項？），已暫停，處理完會自動繼續")
                            self.events.put(("status", "⚠ 需要手動操作，回到戰鬥畫面後自動繼續"))
                            self.events.put(("sound", "alert"))

                elif state == "after":
                    if not found["victory"] and not in_battle_ui:
                        state = "wait"  # VICTORY 動畫結束，等下一場

                self.stop_event.wait(max(0.0, TICK - (time.monotonic() - t0)))
        except Exception as e:
            reason = f"發生錯誤：{e}"
        if sender:
            try:
                sender.finish()
            except Exception:
                pass
        self.events.put(("stopped", reason))

    # ---------- 全域快捷鍵

    def _hotkey_loop(self):
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self.hotkey_tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F8):
            self.events.put(("log", "F8 快捷鍵註冊失敗（視窗自動按鍵器是不是也開著？），請用按鈕操作"))
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.events.put(("toggle", None))
            elif msg.message == WM_HOTKEY and msg.wParam == PAUSE_HOTKEY_ID:
                self.events.put(("pause", None))
            elif msg.message == WM_APP_PAUSE_KEY_ON:
                if not user32.RegisterHotKey(None, PAUSE_HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_Y):
                    self.events.put(("log", "Ctrl+Y 快捷鍵註冊失敗，請用「暫停」按鈕"))
            elif msg.message == WM_APP_PAUSE_KEY_OFF:
                user32.UnregisterHotKey(None, PAUSE_HOTKEY_ID)
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "toggle":
                    self.toggle()
                elif kind == "pause":
                    self.toggle_pause()
                elif kind == "log":
                    self.log(data)
                elif kind == "sound":
                    self.notify(data)
                elif kind == "calibrated":
                    self._on_calibrated(*data)
                elif kind == "scene":
                    self.scene_var.set(data)
                elif kind == "status":
                    if not self.pause_event.is_set():
                        self.status_var.set(data)
                elif kind == "stopped":
                    self.log(data)
                    self.status_var.set(data)
                    self.scene_var.set("—")
                    self.start_btn.config(text="開始 (F8)")
                    self.pause_btn.config(text="暫停 (Ctrl+Y)")
                    self.pause_btn.state(["disabled"])
                    self.pause_event.clear()
                    self._set_pause_hotkey(False)
                    for w in self._inputs:
                        w.state(["!disabled"])
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def on_close(self):
        self.stop_event.set()
        stop_sound()
        self.root.destroy()


if __name__ == "__main__":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AutoKey.LimbusBattle")
    root = tk.Tk()
    try:
        root.iconbitmap(default=resource_path("icon.ico"))
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
