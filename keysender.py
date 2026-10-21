"""共用的 Win32 送鍵工具：視窗列舉、按鍵序列解析、背景 / 前景送鍵。auto_key.pyw 與 limbus_battle.pyw 共用。"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ---------------------------------------------------------------- Win32 定義

WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_HOTKEY = 0x0100, 0x0101, 0x0102, 0x0312
WM_ACTIVATE, WM_SETFOCUS, WM_KILLFOCUS, WM_ACTIVATEAPP, WA_ACTIVE = 0x0006, 0x0007, 0x0008, 0x001C, 1
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x0004, 0x0008
VK_SHIFT, VK_CONTROL, VK_MENU, VK_F8 = 0x10, 0x11, 0x12, 0x77
MOD_NOREPEAT = 0x4000
SW_RESTORE = 9
GA_ROOT = 2
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
HOTKEY_ID = 1
PAUSE_HOTKEY_ID = 2
MOD_CONTROL = 0x0002
VK_Y = 0x59
WM_APP_PAUSE_KEY_ON, WM_APP_PAUSE_KEY_OFF = 0x8001, 0x8002  # 通知快捷鍵執行緒註冊 / 取消 Ctrl+Y

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD),
                ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND),
                ("rcCaret", wt.RECT)]


EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32.EnumWindows.argtypes = [EnumWindowsProc, wt.LPARAM]
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.GetForegroundWindow.restype = wt.HWND
user32.EnumChildWindows.argtypes = [wt.HWND, EnumWindowsProc, wt.LPARAM]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
user32.MapVirtualKeyW.restype = wt.UINT
user32.VkKeyScanW.argtypes = [wt.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

# ---------------------------------------------------------------- 按鍵序列解析

SPECIAL_KEYS = {
    "ENTER": 0x0D, "RETURN": 0x0D, "TAB": 0x09, "SPACE": 0x20, "ESC": 0x1B,
    "BACKSPACE": 0x08, "BS": 0x08, "DELETE": 0x2E, "DEL": 0x2E, "INSERT": 0x2D,
    "HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PGDN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
}
SPECIAL_KEYS.update({f"F{i}": 0x6F + i for i in range(1, 25)})
EXTENDED_VKS = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28}

LITERAL_TOKENS = {"LBRACE": "{", "RBRACE": "}"}

# tkinter keysym → 序列語法
RECORD_KEYSYMS = {
    "Return": "{ENTER}", "KP_Enter": "{ENTER}", "Tab": "{TAB}", "space": "{SPACE}",
    "Escape": "{ESC}", "BackSpace": "{BACKSPACE}", "Delete": "{DELETE}", "Insert": "{INSERT}",
    "Home": "{HOME}", "End": "{END}", "Prior": "{PGUP}", "Next": "{PGDN}",
    "Up": "{UP}", "Down": "{DOWN}", "Left": "{LEFT}", "Right": "{RIGHT}",
}

TOKEN_RE = re.compile(r"\{([^{}]+)\}")


def parse_sequence(seq):
    """把 'p{ENTER}' 轉成 [('char','p'), ('vk',0x0D)]。"""
    actions = []
    pos = 0
    for m in TOKEN_RE.finditer(seq):
        actions.extend(("char", ch) for ch in seq[pos:m.start()])
        name = m.group(1).strip().upper()
        if name.startswith("WAIT"):
            try:
                actions.append(("wait", max(0.0, float(name[4:].strip()))))
            except ValueError:
                raise ValueError("WAIT 後面要接秒數，例如 {WAIT 0.5}")
        elif name in LITERAL_TOKENS:
            actions.append(("char", LITERAL_TOKENS[name]))
        elif name in SPECIAL_KEYS:
            actions.append(("vk", SPECIAL_KEYS[name]))
        else:
            raise ValueError(f"不認識的按鍵：{{{m.group(1)}}}")
        pos = m.end()
    actions.extend(("char", ch) for ch in seq[pos:])
    if not any(kind != "wait" for kind, _ in actions):
        raise ValueError("按鍵序列是空的")
    return actions


def utf16_units(ch):
    data = ch.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]

# ---------------------------------------------------------------- 視窗工具


def process_name(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return "?"
    finally:
        kernel32.CloseHandle(h)


def window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def is_cloaked(hwnd):
    cloaked = wt.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return cloaked.value != 0


def list_windows(exclude=None):
    result = []

    @EnumWindowsProc
    def callback(hwnd, _):
        if hwnd != exclude and user32.IsWindowVisible(hwnd) and not is_cloaked(hwnd):
            title = window_title(hwnd)
            if title and title != "Program Manager":
                result.append((hwnd, title, process_name(hwnd)))
        return True

    user32.EnumWindows(callback, 0)
    return result


def activate_window(hwnd):
    """把 hwnd 切到前景；成功回傳 True。"""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_tid and fg_tid != cur_tid and user32.AttachThreadInput(cur_tid, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
    for _ in range(30):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.01)
    return False

# 目標視窗最後一次在前景時，焦點所在的子控制項。視窗失去焦點後 Windows 會清掉這個資訊，所以要自己記
FOCUS_CACHE = {}
EDIT_CLASS_HINTS = ("edit", "richedit", "scintilla", "textbox", "memo")


def current_focus(hwnd):
    """hwnd 正在前景時回傳它裡面有焦點的控制項（並記下來），否則回傳 None。"""
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndFocus:
        if user32.GetAncestor(info.hwndFocus, GA_ROOT) == hwnd:
            FOCUS_CACHE[hwnd] = info.hwndFocus
            return info.hwndFocus
    return None


def find_edit_child(hwnd):
    """找視窗裡面積最大、看得到的文字輸入框。"""
    best, best_area = None, 0

    @EnumWindowsProc
    def callback(child, _):
        nonlocal best, best_area
        if user32.IsWindowVisible(child):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child, buf, 256)
            if any(h in buf.value.lower() for h in EDIT_CLASS_HINTS):
                rc = wt.RECT()
                user32.GetWindowRect(child, ctypes.byref(rc))
                area = (rc.right - rc.left) * (rc.bottom - rc.top)
                if area > best_area:
                    best, best_area = child, area
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    return best

# ---------------------------------------------------------------- 送出按鍵

LPARAM_BITS = 8 * ctypes.sizeof(wt.LPARAM)


def key_lparam(scan, extended, up):
    v = 1 | (scan << 16) | (0x01000000 if extended else 0)
    if up:
        v |= 0xC0000000
    if v >= 1 << (LPARAM_BITS - 1):
        v -= 1 << LPARAM_BITS
    return v


WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 0x0200, 0x0201, 0x0202, 0x0001
INPUT_MOUSE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0, 0x0002, 0x0004
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]


def mouse_lparam(x, y):
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


class BackgroundSender:
    """PostMessage 直接丟進目標視窗的訊息佇列，不搶焦點；部分程式（多數遊戲）不吃這種方式。"""

    def __init__(self, hwnd, hold, game_keys=True, fake_active=False):
        self.hwnd, self.hold = hwnd, hold
        self._target = hwnd
        self.game_keys = game_keys      # True：字母送按鍵訊號（遊戲用）；False：送文字（記事本、聊天框用）
        self.fake_active = fake_active  # 每輪先告訴視窗「你在前景」；Discord、瀏覽器、Unity 遊戲失去焦點時會忽略按鍵

    def target(self):
        # 文字通常要送到有焦點的子控制項（例如記事本裡的編輯框），不是外框視窗
        focus = current_focus(self.hwnd)
        if focus:
            return focus
        cached = FOCUS_CACHE.get(self.hwnd)
        if cached and user32.IsWindow(cached) and user32.GetAncestor(cached, GA_ROOT) == self.hwnd:
            return cached
        return find_edit_child(self.hwnd) or self.hwnd

    def begin(self):
        self._target = self.target()
        if self.fake_active:
            user32.PostMessageW(self.hwnd, WM_ACTIVATEAPP, 1, 0)
            user32.PostMessageW(self.hwnd, WM_ACTIVATE, WA_ACTIVE, 0)
            user32.PostMessageW(self._target, WM_SETFOCUS, 0, 0)
        return True

    def end(self):
        pass

    def finish(self):
        # 停止後把「假裝在前景」還原，除非使用者已經真的切到那個視窗
        if self.fake_active and user32.IsWindow(self.hwnd) and user32.GetForegroundWindow() != self.hwnd:
            user32.PostMessageW(self._target, WM_KILLFOCUS, 0, 0)
            user32.PostMessageW(self.hwnd, WM_ACTIVATE, 0, 0)
            user32.PostMessageW(self.hwnd, WM_ACTIVATEAPP, 0, 0)

    def vk(self, vk):
        scan = user32.MapVirtualKeyW(vk, 0)
        ext = vk in EXTENDED_VKS
        user32.PostMessageW(self._target, WM_KEYDOWN, vk, key_lparam(scan, ext, False))
        time.sleep(self.hold)
        user32.PostMessageW(self._target, WM_KEYUP, vk, key_lparam(scan, ext, True))

    def char(self, ch):
        r = user32.VkKeyScanW(ch)
        if self.game_keys and r != -1:
            # 遊戲只認按鍵訊號；大小寫不分（Shift 狀態無法用這種方式送過去）
            self.vk(r & 0xFF)
            return
        # 文字模式直接送 WM_CHAR；送 KEYDOWN 的話，背景視窗會用自己的鍵盤狀態轉換，大小寫可能跑掉
        for unit in utf16_units(ch):
            user32.PostMessageW(self._target, WM_CHAR, unit, 1)

    def click(self, x, y):
        """在視窗內容區座標 (x, y) 左鍵點一下，不移動真正的滑鼠。"""
        lp = mouse_lparam(x, y)
        user32.PostMessageW(self.hwnd, WM_MOUSEMOVE, 0, lp)
        time.sleep(0.03)
        user32.PostMessageW(self.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        time.sleep(max(self.hold, 0.05))
        user32.PostMessageW(self.hwnd, WM_LBUTTONUP, 0, lp)


class ForegroundSender:
    """切到目標視窗再用 SendInput 模擬實體鍵盤（掃描碼），相容性最高，但會搶焦點。"""

    def __init__(self, hwnd, hold, restore, unicode_chars=False):
        self.hwnd, self.hold, self.restore = hwnd, hold, restore
        self.unicode_chars = unicode_chars  # 一般字元改用 Unicode 輸入，可避開中文輸入法攔截
        self._prev = None

    def begin(self):
        self._prev = user32.GetForegroundWindow()
        return activate_window(self.hwnd)

    def finish(self):
        pass

    def end(self):
        if self.restore and self._prev and self._prev != self.hwnd and user32.IsWindow(self._prev):
            activate_window(self._prev)

    @staticmethod
    def _send(vk, scan, flags):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _press(self, vk, up):
        scan = user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0)
        self._send(vk, scan, flags | (KEYEVENTF_KEYUP if up else 0))

    def vk(self, vk):
        self._press(vk, False)
        time.sleep(self.hold)
        self._press(vk, True)

    def char(self, ch):
        r = user32.VkKeyScanW(ch)
        mods = (r >> 8) & 0xFF
        if not self.unicode_chars and r != -1 and mods & ~0x07 == 0:
            mod_vks = [v for bit, v in ((1, VK_SHIFT), (2, VK_CONTROL), (4, VK_MENU)) if mods & bit]
            for m in mod_vks:
                self._press(m, False)
            self.vk(r & 0xFF)
            for m in reversed(mod_vks):
                self._press(m, True)
        else:
            for unit in utf16_units(ch):
                self._send(0, unit, KEYEVENTF_UNICODE)
                self._send(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

    @staticmethod
    def _mouse(flags):
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def click(self, x, y):
        """把滑鼠移到視窗內容區座標 (x, y) 點一下，再把游標移回原位。"""
        pt = wt.POINT(int(x), int(y))
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        old = wt.POINT()
        user32.GetCursorPos(ctypes.byref(old))
        user32.SetCursorPos(pt.x, pt.y)
        time.sleep(0.05)
        self._mouse(MOUSEEVENTF_LEFTDOWN)
        time.sleep(max(self.hold, 0.05))
        self._mouse(MOUSEEVENTF_LEFTUP)
        time.sleep(0.05)
        user32.SetCursorPos(old.x, old.y)



def resource_path(name):
    # 打包成 exe 後資源會解壓到 sys._MEIPASS
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), name)
