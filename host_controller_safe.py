from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

import pyautogui

import host_controller as core


SAFE_VERSION = "0.6.0-safe-desktop-launch"
core.VERSION = SAFE_VERSION


class SafeMusicVMAuto(core.MusicVMAuto):
    """v0.6 wrapper: keep v0.5 IP/QQ OCR logic, replace risky keyboard launch."""

    def _build(self):
        self.title("MusicVMAuto v0.6 - 安全启动版")
        self.geometry("920x650")
        self.minsize(820, 600)

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(
            root,
            text="MusicVMAuto v0.6 - IP验证 + QQ音乐（安全启动）",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            root,
            text=(
                "不录模板、不按F8、不使用固定坐标。QQ音乐启动已彻底取消 Ctrl+G / Win+R / 命令输入，"
                "改为 OCR 找到虚拟机桌面的“QQ音乐”图标文字后直接双击。"
            ),
            wraplength=880,
        ).pack(anchor="w", pady=(4, 10))

        cfg = ttk.LabelFrame(root, text="配置", padding=10)
        cfg.pack(fill="x")
        self.vm_var = tk.StringVar(value=self.cfg["vmware_title_keyword"])
        self.base_var = tk.StringVar(value=self.cfg["base_date"])
        # 兼容 v0.5 的 save_ui；v0.6 不再使用这个路径启动 QQ。
        self.qq_var = tk.StringVar(value=self.cfg.get("qqmusic_exe", core.DEFAULT_CONFIG["qqmusic_exe"]))

        ttk.Label(cfg, text="VMware标题关键字").grid(row=0, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.vm_var, width=24).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(cfg, text="歌单1基准日期").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(cfg, textvariable=self.base_var, width=18).grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Button(cfg, text="保存配置", command=self.save_ui).grid(row=0, column=3, rowspan=2, padx=6, sticky="ns")
        cfg.columnconfigure(2, weight=1)

        today = ttk.LabelFrame(root, text="今日", padding=10)
        today.pack(fill="x", pady=10)
        self.today_var = tk.StringVar()
        ttk.Label(today, textvariable=self.today_var, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self._refresh_today()

        actions = ttk.LabelFrame(root, text="当前选中的虚拟机（先用 A-1 测试）", padding=10)
        actions.pack(fill="x")
        ttk.Button(actions, text="检测 VMware + OCR", command=lambda: self.run_bg(self.diagnose_ocr)).grid(
            row=0, column=0, padx=5, pady=4, sticky="ew"
        )
        ttk.Button(actions, text="1. IP验证", command=lambda: self.run_bg(self.ip_flow)).grid(
            row=0, column=1, padx=5, pady=4, sticky="ew"
        )
        ttk.Button(actions, text="2. QQ音乐", command=lambda: self.run_bg(self.qq_flow)).grid(
            row=0, column=2, padx=5, pady=4, sticky="ew"
        )
        ttk.Button(actions, text="完整：IP → QQ", command=lambda: self.run_bg(self.full_flow)).grid(
            row=0, column=3, padx=5, pady=4, sticky="ew"
        )
        for col in range(4):
            actions.columnconfigure(col, weight=1)

        ttk.Label(
            actions,
            text=(
                "安全规则：IP只允许识别并点击“线路设置 / 验证所有IP”；QQ启动只允许双击 OCR 明确识别到的“QQ音乐”桌面文字。"
                "任何目标找不到都会截图并停止当前步骤，不发送系统快捷键，也不做固定坐标兜底。"
            ),
            wraplength=870,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        info = ttk.LabelFrame(root, text="QQ音乐启动方式", padding=10)
        info.pack(fill="x", pady=10)
        ttk.Label(
            info,
            text=(
                "先 OCR 扫描当前 VMware 画面。如果 QQ 已经打开则直接继续；否则只在虚拟机画面的桌面区域寻找“QQ音乐”，"
                "找到后双击。找不到时保存失败截图并停止，不会再输入任何命令。"
            ),
            wraplength=870,
        ).pack(anchor="w")

        logf = ttk.LabelFrame(root, text="运行日志", padding=8)
        logf.pack(fill="both", expand=True)
        self.logbox = tk.Text(logf, wrap="word", height=18)
        self.logbox.pack(fill="both", expand=True)

    def _startup(self):
        self.log(f"版本：{SAFE_VERSION}")
        self.log(f"配置文件：{core.CONFIG_PATH}")
        self.log("安全修复：已完全禁用 Ctrl+G、Win+R 和命令行方式启动 QQ音乐。")
        self.log("QQ音乐只通过 OCR 定位桌面图标文字并双击启动。")

    def _qq_already_ready(self, items) -> bool:
        recognized = {core.normalize(i.text) for i in items if i.score >= 0.44}
        ready_hits = sum(1 for word in core.QQ_READY_WORDS if core.normalize(word) in recognized)
        return ready_hits >= 2

    def _find_qq_desktop_label(self, win, items):
        width, height = int(win.width), int(win.height)
        # 排除 VMware 顶部菜单/标签区域；桌面快捷方式通常位于左侧。
        preferred_region = (0, int(height * 0.12), int(width * 0.62), int(height * 0.94))
        hit = self.vision.find(
            items,
            ("QQ音乐", "QQ 音乐"),
            min_score=max(0.48, float(self.cfg.get("ocr_min_score", 0.46))),
            region=preferred_region,
        )
        if hit:
            return hit

        # 如果桌面图标被放在右侧，再扩大到整个虚拟机客户区，但仍排除顶部 VMware 区域。
        guest_region = (0, int(height * 0.12), width, int(height * 0.94))
        return self.vision.find(
            items,
            ("QQ音乐", "QQ 音乐"),
            min_score=max(0.52, float(self.cfg.get("ocr_min_score", 0.46))),
            region=guest_region,
        )

    def start_qq_in_guest(self, win):
        self.log("安全启动 QQ音乐：不发送任何键盘快捷键或运行命令。")
        _, items = self.vision.scan(win)

        if self._qq_already_ready(items):
            self.log("检测到 QQ音乐已经打开，跳过启动动作。")
            return

        target = self._find_qq_desktop_label(win, items)
        if not target:
            path = core.save_failure(win, "qq-desktop-icon-not-found")
            raise RuntimeError(
                "OCR没有找到虚拟机桌面的“QQ音乐”图标文字。已停止，绝不发送快捷键或命令。截图：" + str(path)
            )

        x, y = self.vision.screen_point(win, target)
        self.log(
            f"OCR识别到 QQ音乐桌面入口 -> ({x},{y})，置信度={target.score:.3f}；执行双击。"
        )
        pyautogui.moveTo(x, y, duration=0.20)
        pyautogui.doubleClick(x, y, interval=0.16)
        time.sleep(1.0)


if __name__ == "__main__":
    SafeMusicVMAuto().mainloop()
