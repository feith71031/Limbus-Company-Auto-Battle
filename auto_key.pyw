"""視窗自動按鍵器：對指定視窗以固定間隔重複送出按鍵（例如 p + Enter）。

按鍵序列語法：
    一般字元直接輸入，例如  p
    特殊鍵用大括號，例如    {ENTER} {TAB} {SPACE} {ESC} {BACKSPACE} {DELETE}
                            {UP} {DOWN} {LEFT} {RIGHT} {HOME} {END} {PGUP} {PGDN} {F1}~{F24}
    序列中暫停             {WAIT 0.5}  (單位：秒)
    範例                    p{ENTER}      →  按 p 再按 Enter
                            hello{WAIT 1}{ENTER}

F8：全域快捷鍵，隨時開始 / 停止。Ctrl+Y：執行中暫停 / 繼續。
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from keysender import *  # noqa: F401,F403  Win32 定義、送鍵類別、視窗工具


# ---------------------------------------------------------------- GUI


class App:
    def __init__(self, root):
        self.root = root
        root.title("視窗自動按鍵器")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()  # set = 暫停中
        self.sent_count = 0
        self.hotkey_tid = 0
        self.worker = None
        self.windows = []
        self.target_hwnd = None
        self.interval = 1.0

        self.seq_var = tk.StringVar(value="p{ENTER}")
        self.interval_var = tk.StringVar(value="1.0")
        self.count_var = tk.StringVar(value="0")
        self.hold_var = tk.StringVar(value="1")
        self.mode_var = tk.StringVar(value="bg")
        self.restore_var = tk.BooleanVar(value=True)
        self.unicode_var = tk.BooleanVar(value=False)
        self.bg_kind_var = tk.StringVar(value="game")
        self.fake_active_var = tk.BooleanVar(value=True)
        self.topmost_var = tk.BooleanVar(value=False)
        self.rec_wait_var = tk.BooleanVar(value=False)
        self.recording = False
        self._last_rec_time = None
        self.status_var = tk.StringVar(value="選好視窗後按「開始」或 F8；執行中可按 Ctrl+Y 暫停，也能隨時改「每輪間隔」")

        self.interval_var.trace_add("write", lambda *_: self._read_interval())

        pad = {"padx": 6, "pady": 4}
        f = ttk.Frame(root, padding=10)
        f.grid()

        ttk.Label(f, text="目標視窗").grid(row=0, column=0, sticky="w", **pad)
        self.win_combo = ttk.Combobox(f, state="readonly", width=56)
        self.win_combo.grid(row=0, column=1, columnspan=3, sticky="we", **pad)
        self.win_combo.bind("<<ComboboxSelected>>", self.on_select_window)
        btns = ttk.Frame(f)
        btns.grid(row=1, column=1, columnspan=3, sticky="w")
        ttk.Button(btns, text="重新整理清單", command=self.refresh_windows).pack(side="left", padx=6)
        self.grab_btn = ttk.Button(btns, text="3 秒後抓取前景視窗", command=self.grab_foreground)
        self.grab_btn.pack(side="left", padx=6)

        ttk.Label(f, text="按鍵序列").grid(row=2, column=0, sticky="w", **pad)
        self.seq_entry = ttk.Entry(f, textvariable=self.seq_var, width=40)
        self.seq_entry.grid(row=2, column=1, columnspan=3, sticky="we", **pad)
        rec = ttk.Frame(f)
        rec.grid(row=3, column=1, columnspan=3, sticky="w")
        self.record_btn = ttk.Button(rec, text="● 錄製按鍵", command=self.toggle_record, width=14)
        self.record_btn.pack(side="left", padx=6)
        self.record_btn.bind("<KeyPress>", self.on_record_key)
        self.record_btn.bind("<FocusOut>", lambda _: self.stop_record())
        self.clear_btn = ttk.Button(rec, text="清除", command=lambda: self.seq_var.set(""))
        self.clear_btn.pack(side="left", padx=6)
        self.rec_wait_chk = ttk.Checkbutton(rec, text="記錄按鍵之間的時間差", variable=self.rec_wait_var)
        self.rec_wait_chk.pack(side="left", padx=6)
        ttk.Label(f, foreground="gray",
                  text="按「錄製按鍵」後直接按鍵盤，按完再點一次停止；也可以手動編輯，特殊鍵如 {ENTER}、暫停 {WAIT 0.5}"
                  ).grid(row=4, column=1, columnspan=3, sticky="w", padx=6)

        ttk.Label(f, text="每輪間隔（秒）").grid(row=5, column=0, sticky="w", **pad)
        ttk.Spinbox(f, textvariable=self.interval_var, from_=0.05, to=86400, increment=0.1,
                    width=10).grid(row=5, column=1, sticky="w", **pad)
        ttk.Label(f, text="次數（0 = 無限）").grid(row=5, column=2, sticky="e", **pad)
        self.count_spin = ttk.Spinbox(f, textvariable=self.count_var, from_=0, to=10**9, increment=1, width=10)
        self.count_spin.grid(row=5, column=3, sticky="w", **pad)

        ttk.Label(f, text="每個鍵按多久（毫秒）").grid(row=6, column=0, sticky="w", **pad)
        self.hold_spin = ttk.Spinbox(f, textvariable=self.hold_var, from_=0, to=2000, increment=10, width=10)
        self.hold_spin.grid(row=6, column=1, sticky="w", **pad)
        ttk.Label(f, foreground="gray", text="一般不用改；遊戲偶爾沒反應再調大（例如 80）").grid(row=6, column=2, columnspan=2, sticky="w", padx=6)

        ttk.Label(f, text="傳送模式").grid(row=7, column=0, sticky="nw", **pad)
        modes = ttk.Frame(f)
        modes.grid(row=7, column=1, columnspan=3, sticky="w", **pad)
        self.bg_radio = ttk.Radiobutton(modes, text="背景傳送（不搶焦點，可以同時做別的事）",
                                        variable=self.mode_var, value="bg", command=self._update_mode)
        self.bg_radio.pack(anchor="w")
        bg_opts = ttk.Frame(modes)
        bg_opts.pack(anchor="w", padx=20)
        self.bg_game_radio = ttk.Radiobutton(bg_opts, text="送遊戲按鍵（遊戲用）", variable=self.bg_kind_var, value="game")
        self.bg_game_radio.pack(side="left")
        self.bg_text_radio = ttk.Radiobutton(bg_opts, text="送文字（記事本、聊天框用）", variable=self.bg_kind_var, value="text")
        self.bg_text_radio.pack(side="left", padx=(12, 0))
        self.fake_active_chk = ttk.Checkbutton(modes, text="讓目標以為自己在前景（Discord、瀏覽器、遊戲需要，建議保持勾選）",
                                               variable=self.fake_active_var)
        self.fake_active_chk.pack(anchor="w", padx=20)
        self.fg_radio = ttk.Radiobutton(modes, text="前景模擬（每次切到該視窗按鍵，相容性最高）",
                                        variable=self.mode_var, value="fg", command=self._update_mode)
        self.fg_radio.pack(anchor="w")
        self.restore_chk = ttk.Checkbutton(modes, text="按完切回原本的視窗", variable=self.restore_var)
        self.restore_chk.pack(anchor="w", padx=20)
        self.unicode_chk = ttk.Checkbutton(modes, text="字元用 Unicode 輸入（避開中文輸入法；遊戲快捷鍵請勿勾選）",
                                           variable=self.unicode_var)
        self.unicode_chk.pack(anchor="w", padx=20)

        bottom = ttk.Frame(f)
        bottom.grid(row=8, column=0, columnspan=4, sticky="we", pady=(8, 0))
        self.start_btn = ttk.Button(bottom, text="開始 (F8)", command=self.toggle, width=14)
        self.start_btn.pack(side="left", padx=6)
        self.pause_btn = ttk.Button(bottom, text="暫停 (Ctrl+Y)", command=self.toggle_pause, width=14)
        self.pause_btn.pack(side="left", padx=6)
        self.pause_btn.state(["disabled"])
        ttk.Checkbutton(bottom, text="視窗置頂", variable=self.topmost_var,
                        command=lambda: root.attributes("-topmost", self.topmost_var.get())).pack(side="left", padx=6)
        ttk.Label(f, textvariable=self.status_var, foreground="#1a5fb4").grid(
            row=9, column=0, columnspan=4, sticky="w", padx=6, pady=(8, 0))

        self._inputs = [self.win_combo, self.grab_btn, self.seq_entry, self.count_spin,
                        self.hold_spin, self.bg_radio, self.fg_radio, self.restore_chk, self.unicode_chk,
                        self.bg_game_radio, self.bg_text_radio, self.fake_active_chk,
                        self.record_btn, self.clear_btn, self.rec_wait_chk]

        self._update_mode()
        root.update_idletasks()
        self.own_hwnd = user32.GetAncestor(root.winfo_id(), GA_ROOT)
        self.refresh_windows()
        threading.Thread(target=self._hotkey_loop, daemon=True).start()
        self._poll()

    # ---------- 視窗選擇

    def refresh_windows(self, select=None):
        keep = select or self.target_hwnd
        self.windows = list_windows(exclude=self.own_hwnd)
        self.win_combo["values"] = [f"[{proc}] {title}" for _, title, proc in self.windows]
        hwnds = [w[0] for w in self.windows]
        if keep in hwnds:
            self.win_combo.current(hwnds.index(keep))
            self.target_hwnd = keep
        else:
            self.win_combo.set("")
            self.target_hwnd = None

    def on_select_window(self, _=None):
        i = self.win_combo.current()
        self.target_hwnd = self.windows[i][0] if i >= 0 else None

    def grab_foreground(self, remaining=3):
        if remaining > 0:
            self.grab_btn.state(["disabled"])
            self.status_var.set(f"請在 {remaining} 秒內點一下目標視窗…")
            self.root.after(1000, self.grab_foreground, remaining - 1)
            return
        self.grab_btn.state(["!disabled"])
        hwnd = user32.GetForegroundWindow()
        if not hwnd or hwnd == self.own_hwnd:
            self.status_var.set("沒抓到其他視窗，請再試一次")
            return
        self.refresh_windows(select=hwnd)
        if self.target_hwnd == hwnd:
            self.status_var.set(f"已選擇：{window_title(hwnd)}")
        else:
            self.status_var.set("抓到的視窗不在清單中（可能沒有標題），請改用下拉選單")

    # ---------- 錄製按鍵

    def toggle_record(self):
        if self.recording:
            self.stop_record()
        else:
            self.recording = True
            self._last_rec_time = None
            self.seq_var.set("")
            self.record_btn.config(text="■ 停止錄製")
            self.record_btn.focus_set()
            self.status_var.set("錄製中：直接按鍵盤，按完點「停止錄製」")

    def stop_record(self):
        if not self.recording:
            return
        self.recording = False
        self.record_btn.config(text="● 錄製按鍵")
        self.status_var.set("錄製完成" if self.seq_var.get() else "沒有錄到任何按鍵")

    def on_record_key(self, event):
        if not self.recording:
            return None
        token = RECORD_KEYSYMS.get(event.keysym)
        if token is None and event.keysym.startswith("F") and event.keysym[1:].isdigit():
            token = "{" + event.keysym + "}" if event.keysym in SPECIAL_KEYS else None
        if token is None and len(event.char) == 1 and event.char.isprintable():
            token = {"{": "{LBRACE}", "}": "{RBRACE}"}.get(event.char, event.char)
        if token is None:
            return "break"  # Shift/Ctrl 等單獨的修飾鍵不記錄
        now = time.monotonic()
        if self.rec_wait_var.get() and self._last_rec_time is not None:
            gap = round(now - self._last_rec_time, 2)
            if gap >= 0.05:
                token = f"{{WAIT {gap}}}" + token
        self._last_rec_time = now
        self.seq_var.set(self.seq_var.get() + token)
        return "break"

    # ---------- 參數

    def _read_interval(self):
        try:
            self.interval = max(0.01, float(self.interval_var.get()))
        except ValueError:
            pass

    def _update_mode(self):
        fg = self.mode_var.get() == "fg"
        for w in (self.restore_chk, self.unicode_chk):
            w.state(["!disabled"] if fg else ["disabled"])
        for w in (self.bg_game_radio, self.bg_text_radio, self.fake_active_chk):
            w.state(["disabled"] if fg else ["!disabled"])

    # ---------- 開始 / 停止

    def running(self):
        return bool(self.worker and self.worker.is_alive())

    def toggle(self):
        if self.running():
            self.stop_event.set()
        else:
            self.start()

    def toggle_pause(self):
        if not self.running():
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="暫停 (Ctrl+Y)")
            self.status_var.set(f"執行中… 已送出 {self.sent_count} 次")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="繼續 (Ctrl+Y)")
            self.status_var.set(f"已暫停（已送出 {self.sent_count} 次），按 Ctrl+Y 繼續")

    def _set_pause_hotkey(self, on):
        if self.hotkey_tid:
            user32.PostThreadMessageW(self.hotkey_tid, WM_APP_PAUSE_KEY_ON if on else WM_APP_PAUSE_KEY_OFF, 0, 0)

    def start(self):
        self.stop_record()
        hwnd = self.target_hwnd
        if not hwnd or not user32.IsWindow(hwnd):
            messagebox.showwarning("視窗自動按鍵器", "請先選擇目標視窗（視窗可能已關閉，請重新整理）")
            return
        try:
            actions = parse_sequence(self.seq_var.get())
        except ValueError as e:
            messagebox.showwarning("視窗自動按鍵器", str(e))
            return
        try:
            float(self.interval_var.get())
            count = int(self.count_var.get())
            hold = max(0, int(self.hold_var.get())) / 1000
        except ValueError:
            messagebox.showwarning("視窗自動按鍵器", "間隔、次數、每個鍵按多久都要填數字")
            return
        self._read_interval()

        if self.mode_var.get() == "fg":
            sender = ForegroundSender(hwnd, hold, self.restore_var.get(), self.unicode_var.get())
        else:
            sender = BackgroundSender(hwnd, hold, self.bg_kind_var.get() == "game", self.fake_active_var.get())

        self.stop_event.clear()
        self.pause_event.clear()
        self.sent_count = 0
        self.worker = threading.Thread(target=self._run, args=(sender, hwnd, actions, count), daemon=True)
        self.worker.start()
        self.start_btn.config(text="停止 (F8)")
        self.pause_btn.config(text="暫停 (Ctrl+Y)")
        self.pause_btn.state(["!disabled"])
        self._set_pause_hotkey(True)
        for w in self._inputs:
            w.state(["disabled"])
        self.status_var.set("執行中…")

    def _run(self, sender, hwnd, actions, count):
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # 建立訊息佇列，AttachThreadInput 需要
        sent = 0
        reason = "已停止"
        try:
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    self.stop_event.wait(0.05)
                    continue
                if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
                    # 剛按完 Ctrl+Y 繼續時 Ctrl 可能還沒放開，先等放開，免得送出 Ctrl+P 之類的組合鍵
                    self.stop_event.wait(0.02)
                    continue
                if not user32.IsWindow(hwnd):
                    reason = "目標視窗已關閉，自動停止"
                    break
                t0 = time.monotonic()
                if sender.begin():
                    try:
                        for kind, value in actions:
                            if self.stop_event.is_set():
                                break
                            if kind == "wait":
                                self.stop_event.wait(value)
                            elif kind == "vk":
                                sender.vk(value)
                            else:
                                sender.char(value)
                    finally:
                        sender.end()
                    sent += 1
                    self.sent_count = sent
                    if not self.pause_event.is_set():
                        self.events.put(("status", f"執行中… 已送出 {sent} 次"))
                else:
                    self.events.put(("status", f"無法切換到目標視窗，這次略過（已送出 {sent} 次）"))
                if count and sent >= count:
                    reason = "已完成指定次數"
                    break
                self.stop_event.wait(max(0.0, self.interval - (time.monotonic() - t0)))
        except Exception as e:
            reason = f"發生錯誤：{e}"
        try:
            sender.finish()
        except Exception:
            pass
        self.events.put(("stopped", f"{reason}（共送出 {sent} 次）"))

    # ---------- 全域快捷鍵 / 事件

    def _hotkey_loop(self):
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # 先建立訊息佇列才能收 PostThreadMessage
        self.hotkey_tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F8):
            self.events.put(("status", "F8 快捷鍵註冊失敗（可能被其他程式占用），請用按鈕操作"))
        # Ctrl+Y 只在執行中註冊，平常不會擋到其他程式的 Ctrl+Y（重做）
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.events.put(("toggle", None))
            elif msg.message == WM_HOTKEY and msg.wParam == PAUSE_HOTKEY_ID:
                self.events.put(("pause", None))
            elif msg.message == WM_APP_PAUSE_KEY_ON:
                if not user32.RegisterHotKey(None, PAUSE_HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_Y):
                    self.events.put(("status", "Ctrl+Y 快捷鍵註冊失敗（可能被其他程式占用），請用「暫停」按鈕"))
            elif msg.message == WM_APP_PAUSE_KEY_OFF:
                user32.UnregisterHotKey(None, PAUSE_HOTKEY_ID)
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "toggle":
                    if not self.recording:
                        self.toggle()
                elif kind == "pause":
                    self.toggle_pause()
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "stopped":
                    self.status_var.set(data)
                    self.start_btn.config(text="開始 (F8)")
                    self.pause_btn.config(text="暫停 (Ctrl+Y)")
                    self.pause_btn.state(["disabled"])
                    self.pause_event.clear()
                    self._set_pause_hotkey(False)
                    for w in self._inputs:
                        w.state(["!disabled"])
                    self.win_combo.state(["readonly"])
                    self._update_mode()
        except queue.Empty:
            pass
        if self.target_hwnd and user32.GetForegroundWindow() == self.target_hwnd:
            current_focus(self.target_hwnd)
        self.root.after(50, self._poll)

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
