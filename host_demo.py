from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import pyautogui
import pygetwindow as gw


def _set_dpi_awareness():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_set_dpi_awareness()
CONFIG_PATH = _app_dir() / "host_config.json"

DEFAULT_CONFIG = {
    "base_date": "2026-08-12",
    "vmware_title_keyword": "VMware",
    "delays": {
        "after_tab": 0.7,
        "after_verify": 4.0,
        "after_qqmusic_launch": 10.0,
        "after_playlist": 1.0,
    },
    "points": {
        "proxy_tab2": None,
        "verify_all_ip": None,
        "qqmusic_icon": None,
        "playlist_1": None,
        "playlist_2": None,
    },
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg = json.loads(json.dumps(DEFAULT_CONFIG))
            cfg["base_date"] = data.get("base_date", cfg["base_date"])
            cfg["vmware_title_keyword"] = data.get("vmware_title_keyword", cfg["vmware_title_keyword"])
            cfg["delays"].update(data.get("delays", {}))
            cfg["points"].update(data.get("points", {}))
            return cfg
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def playlist_for_today(base_date: str) -> int:
    base = date.fromisoformat(base_date)
    return ((date.today() - base).days % 2) + 1


def find_vmware_window(keyword: str):
    keyword = (keyword or "VMware").strip()
    all_windows = [w for w in gw.getAllWindows() if (w.title or "").strip()]
    wins = [w for w in all_windows if keyword.lower() in (w.title or "").lower()]
    if not wins and keyword.lower() != "vmware":
        wins = [w for w in all_windows if "vmware" in (w.title or "").lower()]
    if not wins:
        titles = [w.title for w in all_windows if "vm" in (w.title or "").lower()][:10]
        extra = ("\n检测到的疑似窗口：" + " | ".join(titles)) if titles else ""
        raise RuntimeError(f"找不到 VMware 窗口。当前关键字：{keyword}{extra}")
    win = max(wins, key=lambda w: max(1, w.width) * max(1, w.height))
    if win.isMinimized:
        win.restore()
        time.sleep(0.5)
    try:
        win.activate()
    except Exception:
        pass
    time.sleep(0.5)
    return win


def point_to_screen(win, p):
    if not p:
        raise RuntimeError("该位置还没有校准，请先点这一行的“记录位置”。")
    x = int(win.left + p["rx"] * win.width)
    y = int(win.top + p["ry"] * win.height)
    return x, y


class HostDemo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.title("MusicVMAuto Host Demo v0.2 - QQ音乐")
        self.geometry("860x760")
        self.minsize(780, 680)
        self._build()
        self._refresh_today()
        self.after(400, self._startup_notice)

    def _startup_notice(self):
        self.log(f"配置文件：{CONFIG_PATH}")
        self.log("当前权限：" + ("管理员" if _is_admin() else "普通权限"))
        if not _is_admin():
            messagebox.showwarning(
                "建议管理员权限运行",
                "当前 EXE 不是管理员权限。\n\n如果 VMware 是“以管理员身份运行”的，Windows 会阻止本程序向 VMware 注入鼠标点击。\n请右键 EXE → 以管理员身份运行。",
            )

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="QQ音乐 VMware 宿主机自动化 Demo v0.2", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="只运行在 VMware 外面的宿主机；虚拟机里不安装任何程序。测试前先校准位置。", wraplength=820).pack(anchor="w", pady=(4, 10))

        perm_text = "管理员权限：是" if _is_admin() else "管理员权限：否（建议右键以管理员身份运行）"
        ttk.Label(root, text=perm_text).pack(anchor="w", pady=(0, 8))

        today = ttk.LabelFrame(root, text="今日任务", padding=10)
        today.pack(fill="x")
        self.today_var = tk.StringVar()
        self.playlist_var = tk.StringVar()
        ttk.Label(today, textvariable=self.today_var).grid(row=0, column=0, sticky="w", padx=(0, 24))
        ttk.Label(today, textvariable=self.playlist_var, font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=1, sticky="w")

        cfgf = ttk.LabelFrame(root, text="基础配置", padding=10)
        cfgf.pack(fill="x", pady=10)
        ttk.Label(cfgf, text="基准日期（当天播放歌单1）").grid(row=0, column=0, sticky="w")
        self.base_date_var = tk.StringVar(value=self.cfg["base_date"])
        ttk.Entry(cfgf, textvariable=self.base_date_var, width=16).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(cfgf, text="VMware 标题关键字").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.vmware_var = tk.StringVar(value=self.cfg["vmware_title_keyword"])
        ttk.Entry(cfgf, textvariable=self.vmware_var, width=28).grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        ttk.Button(cfgf, text="保存配置", command=self.save_basic).grid(row=0, column=2, rowspan=2, padx=8)
        ttk.Button(cfgf, text="检测 VMware 窗口", command=lambda: self.run_bg(self.detect_vmware)).grid(row=0, column=3, rowspan=2, padx=8)

        cal = ttk.LabelFrame(root, text="A-1 首次校准（先记录位置，再测试点击）", padding=10)
        cal.pack(fill="x", pady=(0, 10))
        self.status_vars = {}
        items = [
            ("proxy_tab2", "线路设置（第二个Tab）"),
            ("verify_all_ip", "验证所有IP"),
            ("qqmusic_icon", "桌面 QQ音乐图标"),
            ("playlist_1", "第1个歌单"),
            ("playlist_2", "第2个歌单"),
        ]
        for row, (key, label) in enumerate(items):
            ttk.Label(cal, text=label, width=24).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            self.status_vars[key] = var
            ttk.Label(cal, textvariable=var, width=14).grid(row=row, column=1, sticky="w")
            ttk.Button(cal, text="记录位置", command=lambda k=key, l=label: self.capture_point(k, l)).grid(row=row, column=2, padx=6)
            ttk.Button(cal, text="只移动鼠标", command=lambda k=key: self.run_bg(lambda: self.test_move(k))).grid(row=row, column=3, padx=6)
            ttk.Button(cal, text="测试点击", command=lambda k=key: self.run_bg(lambda: self.test_click(k))).grid(row=row, column=4, padx=6)
        self._refresh_status()

        actions = ttk.LabelFrame(root, text="测试当前选中的虚拟机", padding=10)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="1. 测试 IP 点击", command=lambda: self.run_bg(self.test_ip_clicks)).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(actions, text="2. 测试打开 QQ音乐", command=lambda: self.run_bg(self.test_open_qq)).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(actions, text="3. 测试今日歌单", command=lambda: self.run_bg(self.test_playlist)).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(actions, text="完整演示（当前VM）", command=lambda: self.run_bg(self.full_demo)).grid(row=1, column=0, columnspan=3, padx=4, pady=6, sticky="ew")
        for c in range(3):
            actions.columnconfigure(c, weight=1)

        note = ttk.LabelFrame(root, text="测试顺序", padding=10)
        note.pack(fill="x", pady=(0, 10))
        ttk.Label(note, text="① 检测 VMware 窗口 → ② 记录“线路设置”位置 → ③ 点“只移动鼠标”确认坐标 → ④ 再点“测试点击”。不要在未校准时直接测试。", wraplength=800).pack(anchor="w")

        logf = ttk.LabelFrame(root, text="运行日志", padding=8)
        logf.pack(fill="both", expand=True)
        self.logbox = tk.Text(logf, height=14, wrap="word")
        self.logbox.pack(fill="both", expand=True)

    def log(self, msg):
        self.after(0, lambda: (self.logbox.insert("end", str(msg) + "\n"), self.logbox.see("end")))

    def save_basic(self):
        self.cfg["base_date"] = self.base_date_var.get().strip() or "2026-08-12"
        self.cfg["vmware_title_keyword"] = self.vmware_var.get().strip() or "VMware"
        save_config(self.cfg)
        self._refresh_today()
        self.log("基础配置已保存。")

    def detect_vmware(self):
        self.save_basic()
        win = find_vmware_window(self.cfg["vmware_title_keyword"])
        self.log(f"已找到 VMware：{win.title} | left={win.left}, top={win.top}, width={win.width}, height={win.height}")
        self.after(0, lambda: messagebox.showinfo("检测成功", f"已找到 VMware 窗口：\n{win.title}"))

    def _refresh_today(self):
        try:
            idx = playlist_for_today(self.base_date_var.get().strip() or "2026-08-12")
            self.today_var.set("日期：" + date.today().isoformat())
            self.playlist_var.set(f"今日播放：第 {idx} 个歌单")
        except Exception as e:
            self.playlist_var.set(f"日期配置错误：{e}")
        self.after(5000, self._refresh_today)

    def _refresh_status(self):
        for key, var in self.status_vars.items():
            var.set("已校准" if self.cfg["points"].get(key) else "未校准")

    def capture_point(self, key, label):
        self.save_basic()
        messagebox.showinfo("记录位置", f"点确定后有 4 秒。\n\n请把鼠标移动到 VMware 里：{label}\n不要点击，停在那里即可。")
        self.log(f"4 秒后记录：{label}")
        threading.Thread(target=self._capture_worker, args=(key, label), daemon=True).start()

    def _capture_worker(self, key, label):
        time.sleep(4)
        win = find_vmware_window(self.cfg["vmware_title_keyword"])
        time.sleep(0.2)
        x, y = pyautogui.position()
        if not (win.left <= x <= win.left + win.width and win.top <= y <= win.top + win.height):
            self.log(f"记录失败：鼠标 ({x},{y}) 不在 VMware 窗口内。")
            self.after(0, lambda: messagebox.showerror("记录失败", "鼠标没有停在 VMware 窗口内，请重新记录。"))
            return
        rx = (x - win.left) / max(1, win.width)
        ry = (y - win.top) / max(1, win.height)
        self.cfg["points"][key] = {"rx": round(rx, 6), "ry": round(ry, 6)}
        save_config(self.cfg)
        self.after(0, self._refresh_status)
        self.log(f"已记录 {label}：屏幕 ({x},{y})，相对位置 ({rx:.4f}, {ry:.4f})")

    def run_bg(self, fn):
        def worker():
            try:
                fn()
            except Exception as e:
                self.log("错误：" + str(e))
                self.after(0, lambda err=str(e): messagebox.showerror("执行失败", err))
        threading.Thread(target=worker, daemon=True).start()

    def _target(self, key):
        p = self.cfg["points"].get(key)
        if not p:
            raise RuntimeError(f"{key} 尚未校准。请先点击这一行的“记录位置”。")
        win = find_vmware_window(self.cfg["vmware_title_keyword"])
        x, y = point_to_screen(win, p)
        return win, x, y

    def test_move(self, key):
        _, x, y = self._target(key)
        self.log(f"移动鼠标到 {key}: ({x}, {y})，不点击。")
        pyautogui.moveTo(x, y, duration=0.6)

    def _click(self, key, clicks=1, interval=0.15):
        _, x, y = self._target(key)
        self.log(f"准备点击 {key}: ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.35)
        time.sleep(0.15)
        pyautogui.click(x, y, clicks=clicks, interval=interval)
        self.log(f"已点击 {key}")

    def test_click(self, key):
        self._click(key)

    def test_ip_clicks(self):
        self.log("开始测试 IP：只点击‘线路设置’和‘验证所有IP’。")
        if not self.cfg["points"].get("proxy_tab2") or not self.cfg["points"].get("verify_all_ip"):
            raise RuntimeError("请先校准“线路设置”和“验证所有IP”两个位置。")
        self._click("proxy_tab2")
        time.sleep(float(self.cfg["delays"]["after_tab"]))
        self._click("verify_all_ip")
        self.log("已点击‘验证所有IP’。当前版本先人工观察是否出现 √。")
        time.sleep(float(self.cfg["delays"]["after_verify"]))

    def test_open_qq(self):
        if not self.cfg["points"].get("qqmusic_icon"):
            raise RuntimeError("请先校准桌面 QQ音乐图标位置。")
        self.log("双击桌面 QQ音乐图标。")
        self._click("qqmusic_icon", clicks=2)
        time.sleep(float(self.cfg["delays"]["after_qqmusic_launch"]))
        self.log("等待完成，请人工确认 QQ音乐是否正常打开。")

    def test_playlist(self):
        no = playlist_for_today(self.cfg["base_date"])
        key = f"playlist_{no}"
        if not self.cfg["points"].get(key):
            raise RuntimeError(f"请先校准第 {no} 个歌单位置。")
        self.log(f"今天应该播放第 {no} 个歌单。")
        self._click(key, clicks=2)
        time.sleep(float(self.cfg["delays"]["after_playlist"]))

    def full_demo(self):
        self.test_ip_clicks()
        self.test_open_qq()
        self.test_playlist()
        self.log("当前 VM 完整演示结束。")


if __name__ == "__main__":
    pyautogui.FAILSAFE = True
    HostDemo().mainloop()
