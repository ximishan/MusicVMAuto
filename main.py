from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

from music_auto.config import load_config, save_config
from music_auto.orchestrator import run_once
from music_auto.proxy import ProxyController
from music_auto.qqmusic import QQMusicAdapter
from music_auto.rotation import playlist_for_day

CONFIG_PATH = Path(__file__).with_name("config.json")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MusicVMAuto Demo - QQ音乐")
        self.geometry("760x640")
        self.minsize(720, 600)
        self.config_data = load_config(CONFIG_PATH)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self.after(100, self._flush_logs)
        self._refresh_today()

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text="QQ音乐 VM 自动化 Demo", font=("Microsoft YaHei UI", 16, "bold"))
        title.pack(anchor="w")
        ttk.Label(
            root,
            text="当前版本先验证单台虚拟机：线路设置 → 验证所有IP → QQ音乐 → 两个歌单按天轮换。",
        ).pack(anchor="w", pady=(4, 12))

        info = ttk.LabelFrame(root, text="今日任务", padding=10)
        info.pack(fill="x")
        self.today_var = tk.StringVar()
        self.playlist_var = tk.StringVar()
        ttk.Label(info, textvariable=self.today_var).grid(row=0, column=0, sticky="w", padx=(0, 24))
        ttk.Label(info, textvariable=self.playlist_var, font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=1, sticky="w")

        settings = ttk.LabelFrame(root, text="配置", padding=10)
        settings.pack(fill="x", pady=10)

        ttk.Label(settings, text="基准日期（歌单1）").grid(row=0, column=0, sticky="w")
        self.base_date_var = tk.StringVar(value=self.config_data["base_date"])
        ttk.Entry(settings, textvariable=self.base_date_var, width=16).grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(settings, text="QQMusic.exe（可留空）").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.exe_var = tk.StringVar(value=self.config_data["qqmusic"].get("exe_path", ""))
        ttk.Entry(settings, textvariable=self.exe_var, width=58).grid(row=1, column=1, columnspan=3, sticky="ew", padx=8, pady=(8, 0))
        settings.columnconfigure(3, weight=1)

        coords = ttk.Frame(settings)
        coords.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.p1_var = tk.StringVar()
        self.p2_var = tk.StringVar()
        self._refresh_coord_labels()
        ttk.Label(coords, textvariable=self.p1_var).pack(side="left", padx=(0, 20))
        ttk.Label(coords, textvariable=self.p2_var).pack(side="left")

        actions = ttk.LabelFrame(root, text="测试", padding=10)
        actions.pack(fill="x", pady=(0, 10))

        buttons = [
            ("保存配置", self.save_settings),
            ("测试 IP 验证", lambda: self.run_bg(self.test_proxy)),
            ("启动 QQ音乐", lambda: self.run_bg(self.launch_qq)),
            ("记录歌单1位置", lambda: self.run_bg(lambda: self.capture_playlist(1))),
            ("记录歌单2位置", lambda: self.run_bg(lambda: self.capture_playlist(2))),
            ("测试今日歌单", lambda: self.run_bg(self.test_playlist)),
            ("完整测试当前虚拟机", lambda: self.run_bg(self.full_test)),
        ]
        for i, (text, command) in enumerate(buttons):
            ttk.Button(actions, text=text, command=command).grid(
                row=i // 3, column=i % 3, padx=4, pady=4, sticky="ew"
            )
        for c in range(3):
            actions.columnconfigure(c, weight=1)

        log_frame = ttk.LabelFrame(root, text="运行日志", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=18, wrap="word")
        self.log_text.pack(fill="both", expand=True)

    def _refresh_today(self):
        self.config_data["base_date"] = self.base_date_var.get().strip() or "2026-08-12"
        try:
            idx = playlist_for_day(self.config_data["base_date"], date.today())
            self.today_var.set(f"日期：{date.today().isoformat()}")
            self.playlist_var.set(f"今日播放：歌单 {idx}")
        except Exception as e:
            self.playlist_var.set(f"日期配置错误：{e}")
        self.after(5000, self._refresh_today)

    def _refresh_coord_labels(self):
        p1 = self.config_data["qqmusic"].get("playlist_1_relative")
        p2 = self.config_data["qqmusic"].get("playlist_2_relative")
        self.p1_var.set(f"歌单1：{'已校准' if p1 else '未校准'}")
        self.p2_var.set(f"歌单2：{'已校准' if p2 else '未校准'}")

    def log(self, text: str):
        self.log_queue.put(str(text))

    def _flush_logs(self):
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
        self.after(100, self._flush_logs)

    def run_bg(self, fn):
        def worker():
            try:
                fn()
            except Exception as e:
                self.log(f"错误：{e}")
                self.after(0, lambda: messagebox.showerror("执行失败", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def save_settings(self):
        self.config_data["base_date"] = self.base_date_var.get().strip() or "2026-08-12"
        self.config_data["qqmusic"]["exe_path"] = self.exe_var.get().strip()
        save_config(self.config_data, CONFIG_PATH)
        self.log("配置已保存")
        self._refresh_today()

    def test_proxy(self):
        self.save_settings()
        result = ProxyController(self.config_data["proxy"], self.log).verify_ip()
        self.log(f"IP结果：{'成功' if result.ok else '失败'} - {result.message}")

    def launch_qq(self):
        self.save_settings()
        qq = QQMusicAdapter(self.config_data["qqmusic"], self.log)
        qq.launch()
        win = qq.wait_main_window()
        qq.close_popups(win)

    def capture_playlist(self, no: int):
        self.save_settings()
        qq = QQMusicAdapter(self.config_data["qqmusic"], self.log)
        rel = qq.capture_playlist_position(no)
        self.config_data["qqmusic"][f"playlist_{no}_relative"] = rel
        save_config(self.config_data, CONFIG_PATH)
        self.after(0, self._refresh_coord_labels)

    def test_playlist(self):
        self.save_settings()
        no = playlist_for_day(self.config_data["base_date"], date.today())
        self.log(f"今天应播放歌单 {no}")
        qq = QQMusicAdapter(self.config_data["qqmusic"], self.log)
        qq.play_playlist(no)

    def full_test(self):
        self.save_settings()
        result = run_once(self.config_data, self.log)
        self.log(f"完整测试：{'成功' if result.ok else '失败'} - {result.message}")


def cli_run_once() -> int:
    cfg = load_config(CONFIG_PATH)
    result = run_once(cfg, print)
    print(result)
    return 0 if result.ok else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-once", action="store_true", help="按当前配置执行一次完整流程")
    args = parser.parse_args()
    if args.run_once:
        raise SystemExit(cli_run_once())
    App().mainloop()


if __name__ == "__main__":
    main()
