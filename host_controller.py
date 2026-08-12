from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
from rapidocr import RapidOCR

try:
    import win32con
    import win32gui
except Exception:
    win32con = None
    win32gui = None


VERSION = "0.5.2-window-restore-ip-state"
CHECKMARKS = ("√", "✓", "✔", "☑")
BLOCKING_POPUP_WORDS = ("验证码", "安全验证", "登录保护", "重新登录", "二维码", "网络异常", "风险")
SAFE_POPUP_BUTTONS = ("稍后再说", "暂不升级", "以后再说", "我知道了", "知道了")
QQ_READY_WORDS = ("QQ音乐", "音乐馆", "我喜欢", "本地和下载", "创建的歌单", "自建歌单", "我的歌单")
PLAYLIST_HEADINGS = ("创建的歌单", "自建歌单", "我的歌单")
QQ_DESKTOP_NAMES = ("QQ音乐",)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def setup_windows() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08


setup_windows()
ROOT = app_dir()
CONFIG_PATH = ROOT / "host_no_template_config.json"
FAILURE_DIR = ROOT / "failures"
FAILURE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "vmware_title_keyword": "VMware",
    "base_date": "2026-08-11",
    "ocr_min_score": 0.46,
    "ip_result_wait_seconds": 8,
    "qq_start_timeout_seconds": 45,
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key in DEFAULT_CONFIG:
                if key in data:
                    cfg[key] = data[key]
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize(text: str) -> str:
    return "".join((text or "").replace("\u3000", " ").split()).strip().lower()


def playlist_for_today(base_date: str) -> int:
    base = date.fromisoformat(base_date)
    return ((date.today() - base).days % 2) + 1


class NativeWindow:
    """Win32 window wrapper that still works while the window is minimized."""

    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)

    @property
    def title(self) -> str:
        return win32gui.GetWindowText(self.hwnd) if win32gui else ""

    def _rect(self):
        return win32gui.GetWindowRect(self.hwnd)

    @property
    def left(self) -> int:
        return int(self._rect()[0])

    @property
    def top(self) -> int:
        return int(self._rect()[1])

    @property
    def width(self) -> int:
        r = self._rect()
        return max(1, int(r[2] - r[0]))

    @property
    def height(self) -> int:
        r = self._rect()
        return max(1, int(r[3] - r[1]))

    @property
    def isMinimized(self) -> bool:
        return bool(win32gui.IsIconic(self.hwnd))

    def restore(self):
        if win32gui and win32con:
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            time.sleep(0.55)

    def activate(self):
        if not win32gui or not win32con:
            return
        if self.isMinimized:
            self.restore()
        try:
            win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
            win32gui.BringWindowToTop(self.hwnd)
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            try:
                ctypes.windll.user32.SetForegroundWindow(self.hwnd)
            except Exception:
                pass
        time.sleep(0.4)


def find_vmware_window(keyword: str, activate: bool = True):
    """Find VMware even when minimized, then restore it before OCR."""
    keyword = (keyword or "VMware").strip().lower()

    if win32gui is not None:
        handles = []

        def enum_cb(hwnd, _):
            try:
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if not title:
                    return True
                low = title.lower()
                if keyword in low or "vmware" in low:
                    handles.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            handles = []

        if handles:
            def rank(hwnd):
                title = (win32gui.GetWindowText(hwnd) or "").lower()
                score = 0
                if "vmware workstation" in title:
                    score += 1_000_000_000
                elif "vmware" in title:
                    score += 500_000_000
                if not win32gui.IsIconic(hwnd):
                    try:
                        l, t, r, b = win32gui.GetWindowRect(hwnd)
                        score += max(0, r - l) * max(0, b - t)
                    except Exception:
                        pass
                return score

            win = NativeWindow(max(handles, key=rank))
            if win.isMinimized:
                win.restore()
            if activate:
                win.activate()
            return win

    # Fallback for machines where pywin32 is unavailable.
    windows = [w for w in gw.getAllWindows() if (w.title or "").strip()]
    matches = [w for w in windows if keyword in (w.title or "").lower()]
    if not matches and keyword != "vmware":
        matches = [w for w in windows if "vmware" in (w.title or "").lower()]
    if not matches:
        raise RuntimeError("找不到 VMware Workstation 窗口。")
    win = max(matches, key=lambda w: max(1, w.width) * max(1, w.height))
    if win.isMinimized:
        win.restore()
        time.sleep(0.55)
    if activate:
        try:
            win.activate()
        except Exception:
            pass
        time.sleep(0.4)
    return win


def screenshot_window(win) -> np.ndarray:
    image = pyautogui.screenshot(region=(int(win.left), int(win.top), int(win.width), int(win.height)))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def save_failure(win, name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = FAILURE_DIR / f"{stamp}-{name}.png"
    image = screenshot_window(win)
    ok, data = cv2.imencode(".png", image)
    if ok:
        data.tofile(str(path))
    return path


@dataclass
class OCRItem:
    text: str
    score: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def cx(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def cy(self) -> int:
        return (self.y1 + self.y2) // 2

    @property
    def height(self) -> int:
        return max(1, self.y2 - self.y1)


class OCRVision:
    def __init__(self, log):
        self.log = log
        self._engine = None
        self._lock = threading.Lock()

    def engine(self):
        if self._engine is None:
            self.log("首次初始化本地 OCR，第一次会比后续稍慢。")
            self._engine = RapidOCR()
        return self._engine

    def scan(self, win) -> tuple[np.ndarray, list[OCRItem]]:
        image = screenshot_window(win)
        with self._lock:
            result = self.engine()(image, use_cls=False)
        items: list[OCRItem] = []
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or txts is None or scores is None:
            return image, items
        for box, text, score in zip(boxes, txts, scores):
            pts = np.asarray(box, dtype=float)
            x1 = int(np.min(pts[:, 0]))
            y1 = int(np.min(pts[:, 1]))
            x2 = int(np.max(pts[:, 0]))
            y2 = int(np.max(pts[:, 1]))
            items.append(OCRItem(str(text), float(score), x1, y1, x2, y2))
        return image, items

    def find(self, items: list[OCRItem], candidates, min_score=0.46, contains=False, region=None):
        norms = [(c, normalize(c)) for c in candidates]
        hits = []
        for item in items:
            if item.score < min_score:
                continue
            if region is not None:
                x1, y1, x2, y2 = region
                if not (x1 <= item.cx <= x2 and y1 <= item.cy <= y2):
                    continue
            value = normalize(item.text)
            for candidate, wanted in norms:
                matched = wanted in value if contains else value == wanted
                if matched:
                    hits.append((item.score, len(wanted), candidate, item))
        if not hits:
            return None
        hits.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return hits[0][3]

    def screen_point(self, win, item: OCRItem):
        return int(win.left + item.cx), int(win.top + item.cy)

    def click_item(self, win, item: OCRItem, label: str):
        x, y = self.screen_point(win, item)
        self.log(f"OCR识别“{label}” -> ({x},{y})，置信度={item.score:.3f}")
        pyautogui.moveTo(x, y, duration=0.18)
        pyautogui.click()

    def double_click_item(self, win, item: OCRItem, label: str):
        x, y = self.screen_point(win, item)
        self.log(f"OCR识别桌面“{label}” -> ({x},{y})，置信度={item.score:.3f}；执行双击。")
        pyautogui.moveTo(x, y, duration=0.18)
        pyautogui.doubleClick(x, y, interval=0.16)

    def has_checkmark(self, items: list[OCRItem]) -> bool:
        for item in items:
            raw = item.text or ""
            if any(mark in raw for mark in CHECKMARKS):
                self.log(f"检测到验证成功符号：{raw!r}，置信度={item.score:.3f}")
                return True
        return False


class MusicVMAuto(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.vision = OCRVision(self.log)
        self.title("MusicVMAuto v0.5.2 - 无模板 IP + QQ音乐")
        self.geometry("920x660")
        self.minsize(820, 590)
        self._build()
        self.after(300, self._startup)

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="MusicVMAuto v0.5.2 - 无模板版", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="VMware 最小化也会自动找到并恢复。IP 不再强制每次重新识别第二个 Tab；先判断当前页面状态，再决定是否切换。",
            wraplength=880,
        ).pack(anchor="w", pady=(4, 10))

        cfg = ttk.LabelFrame(root, text="配置", padding=10)
        cfg.pack(fill="x")
        self.vm_var = tk.StringVar(value=self.cfg["vmware_title_keyword"])
        self.base_var = tk.StringVar(value=self.cfg["base_date"])
        ttk.Label(cfg, text="VMware标题关键字").grid(row=0, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.vm_var, width=22).grid(row=0, column=1, sticky="w", padx=6)
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
        ttk.Button(actions, text="检测 VMware + OCR", command=lambda: self.run_bg(self.diagnose_ocr)).grid(row=0, column=0, padx=5, pady=4, sticky="ew")
        ttk.Button(actions, text="1. IP验证", command=lambda: self.run_bg(self.ip_flow)).grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        ttk.Button(actions, text="2. QQ音乐", command=lambda: self.run_bg(self.qq_flow)).grid(row=0, column=2, padx=5, pady=4, sticky="ew")
        ttk.Button(actions, text="完整：IP → QQ", command=lambda: self.run_bg(self.full_flow)).grid(row=0, column=3, padx=5, pady=4, sticky="ew")
        for col in range(4):
            actions.columnconfigure(col, weight=1)
        ttk.Label(
            actions,
            text="IP安全规则：已经看到“验证所有IP”就不再重复点“线路设置”；只有确实不在第二个Tab时才切换。验证按钮最多3次。",
            wraplength=870,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        info = ttk.LabelFrame(root, text="当前 v0.5.2 规则", padding=10)
        info.pack(fill="x", pady=10)
        ttk.Label(
            info,
            text="QQ仍然只用OCR双击桌面“QQ音乐”图标启动，不使用 Ctrl+G / Win+R / CMD。VMware若最小化，程序会先恢复窗口再截图识别。",
            wraplength=870,
        ).pack(anchor="w")

        logf = ttk.LabelFrame(root, text="运行日志", padding=8)
        logf.pack(fill="both", expand=True)
        self.logbox = tk.Text(logf, wrap="word", height=18)
        self.logbox.pack(fill="both", expand=True)

    def _startup(self):
        self.log(f"版本：{VERSION}")
        self.log(f"配置文件：{CONFIG_PATH}")
        self.log("VMware窗口查找已改用 Win32：窗口最小化时也能找到并自动恢复。")
        self.log("IP流程已改为状态判断：已在线路设置页时不会再次强制寻找/点击第二个Tab。")

    def log(self, msg):
        text = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        if hasattr(self, "logbox"):
            try:
                self.after(0, lambda t=text: (self.logbox.insert("end", t + "\n"), self.logbox.see("end")))
            except Exception:
                pass

    def save_ui(self):
        self.cfg["vmware_title_keyword"] = self.vm_var.get().strip() or "VMware"
        self.cfg["base_date"] = self.base_var.get().strip() or DEFAULT_CONFIG["base_date"]
        save_config(self.cfg)
        self._refresh_today()
        self.log("配置已保存。")

    def _refresh_today(self):
        try:
            idx = playlist_for_today(self.base_var.get().strip() or DEFAULT_CONFIG["base_date"])
            self.today_var.set(f"{date.today().isoformat()}：今天播放第 {idx} 个歌单")
        except Exception as e:
            self.today_var.set("基准日期错误：" + str(e))
        self.after(5000, self._refresh_today)

    def run_bg(self, fn):
        def worker():
            try:
                fn()
            except Exception as e:
                self.log("失败：" + str(e))
                self.after(0, lambda err=str(e): messagebox.showerror("执行失败", err))
        threading.Thread(target=worker, daemon=True).start()

    def current_vm(self):
        return find_vmware_window(self.cfg["vmware_title_keyword"], activate=True)

    def diagnose_ocr(self):
        win = self.current_vm()
        self.log(f"VMware：{win.title} | {win.width}x{win.height} @ ({win.left},{win.top})")
        _, items = self.vision.scan(win)
        texts = [i.text for i in items if i.score >= float(self.cfg["ocr_min_score"])]
        self.log(f"OCR识别到 {len(texts)} 条有效文字。")
        self.log("前60条：" + " | ".join(texts[:60]))
        if not texts:
            raise RuntimeError("OCR没有识别到文字，请确认虚拟机画面可见、未锁屏。")

    def find_verify_button(self, items, min_score):
        return self.vision.find(items, ("验证所有IP", "验证所有 IP"), min_score=max(0.38, min_score - 0.06), contains=True)

    def ip_success_with_page_hint(self, items) -> bool:
        # 当“验证所有IP”OCR临时漏识别时，用“可用 + √”共同证明仍处于线路设置页。
        available = self.vision.find(items, ("可用",), min_score=0.35, contains=True)
        if not available:
            return False
        return self.vision.has_checkmark(items)

    def ip_flow(self):
        win = self.current_vm()
        min_score = float(self.cfg["ocr_min_score"])
        self.log("开始 IP 验证：先判断当前页面，再决定是否切换线路设置。")

        _, items = self.vision.scan(win)
        verify = self.find_verify_button(items, min_score)

        if verify:
            self.log("当前已经在线路设置页：识别到“验证所有IP”，不再重复点击第二个Tab。")
        elif self.ip_success_with_page_hint(items):
            self.log("当前页面识别到“可用 + √”，确认已经在线路设置页且IP可用。")
            return True
        else:
            # OCR可能偶发漏掉Tab文字，先重新扫描几次，避免一次漏识别就失败。
            tab = None
            for scan_no in range(1, 4):
                tab = self.vision.find(items, ("线路设置",), min_score=max(0.38, min_score - 0.06), contains=True)
                if tab:
                    break
                if scan_no < 3:
                    self.log(f"第 {scan_no} 次未识别到“线路设置”，等待后重新OCR。")
                    time.sleep(0.55)
                    _, items = self.vision.scan(win)
                    verify = self.find_verify_button(items, min_score)
                    if verify:
                        self.log("重新OCR后发现“验证所有IP”，说明其实已经在线路设置页。")
                        break
                    if self.ip_success_with_page_hint(items):
                        self.log("重新OCR后发现“可用 + √”，IP已经成功。")
                        return True

            if not verify:
                if not tab:
                    path = save_failure(win, "ip-page-state-unknown")
                    raise RuntimeError(f"既没有识别到“验证所有IP”，也没有识别到“线路设置”，已停止。截图：{path}")

                self.vision.click_item(win, tab, "线路设置")
                self.log("已点击线路设置；后面只检查页面结果，不会再次寻找/点击第二个Tab。")

                verify = None
                for wait_no in range(1, 5):
                    time.sleep(0.55)
                    _, items = self.vision.scan(win)
                    verify = self.find_verify_button(items, min_score)
                    if verify:
                        self.log("切换完成：已识别到“验证所有IP”。")
                        break
                    if self.ip_success_with_page_hint(items):
                        self.log("切换完成后识别到“可用 + √”，IP已经成功。")
                        return True
                    self.log(f"切换线路设置后第 {wait_no}/4 次OCR暂未识别到验证按钮，继续等待。")

                if not verify:
                    path = save_failure(win, "ip-tab-switched-but-no-verify")
                    raise RuntimeError(f"已经点击“线路设置”，但多次OCR仍未找到“验证所有IP”。截图：{path}")

        # 已确认当前就是线路设置页。从这里开始绝不再找第二个Tab。
        for attempt in range(1, 4):
            _, items = self.vision.scan(win)
            if self.vision.has_checkmark(items):
                self.log("IP 已经显示验证成功符号，不再点击。")
                return True

            verify = self.find_verify_button(items, min_score)
            if not verify:
                # 验证按钮偶发漏OCR时重扫，不回头找Tab。
                for retry_scan in range(1, 4):
                    time.sleep(0.45)
                    _, items = self.vision.scan(win)
                    if self.vision.has_checkmark(items):
                        self.log("重扫时检测到 √，IP验证成功。")
                        return True
                    verify = self.find_verify_button(items, min_score)
                    if verify:
                        break
                    self.log(f"验证按钮OCR漏识别，重扫 {retry_scan}/3。")

            if not verify:
                path = save_failure(win, f"ip-no-verify-button-{attempt}")
                raise RuntimeError(f"已确认在线路设置页，但连续多次OCR都没找到“验证所有IP”，为防误点已停止。截图：{path}")

            self.log(f"IP验证第 {attempt}/3 次。")
            self.vision.click_item(win, verify, "验证所有IP")
            pyautogui.moveTo(int(win.left + win.width - 12), int(win.top + 40), duration=0.12)

            deadline = time.time() + int(self.cfg["ip_result_wait_seconds"])
            while time.time() < deadline:
                time.sleep(1.0)
                _, result_items = self.vision.scan(win)
                if self.vision.has_checkmark(result_items):
                    self.log(f"IP验证成功，第 {attempt} 次点击后检测到 √。")
                    return True

            if attempt < 3:
                self.log("本次等待结束仍未识别到 √，只重试“验证所有IP”，不会再点击Tab。")

        path = save_failure(win, "ip-no-checkmark-after-3")
        raise RuntimeError(f"验证所有IP已点击3次，仍未检测到√。截图：{path}")

    def qq_ready_score(self, items: list[OCRItem]) -> int:
        recognized = {normalize(i.text) for i in items if i.score >= 0.44}
        return sum(1 for word in QQ_READY_WORDS if normalize(word) in recognized)

    def find_desktop_qq_icon(self, win, items: list[OCRItem]):
        height = int(win.height)
        min_score = float(self.cfg["ocr_min_score"])
        names = {normalize(x) for x in QQ_DESKTOP_NAMES}
        hits = []
        for item in items:
            if item.score < min_score:
                continue
            if normalize(item.text) not in names:
                continue
            if item.cy < int(height * 0.12) or item.cy > int(height * 0.92):
                continue
            if item.height > 55:
                continue
            hits.append(item)
        if not hits:
            return None
        hits.sort(key=lambda i: (i.cx, -i.score))
        return hits[0]

    def start_qq_from_desktop(self, win):
        self.log("启动 QQ音乐：只使用 OCR 查找桌面“QQ音乐”图标，不发送任何系统组合键。")
        _, items = self.vision.scan(win)
        if self.qq_ready_score(items) >= 2:
            self.log("当前画面已经是 QQ音乐主界面，不重复启动。")
            return items

        icon = self.find_desktop_qq_icon(win, items)
        if not icon:
            path = save_failure(win, "qq-desktop-icon-not-found")
            raise RuntimeError(f"OCR没有找到虚拟机桌面的“QQ音乐”图标。没有发送任何快捷键。截图：{path}")

        self.vision.double_click_item(win, icon, "QQ音乐")
        time.sleep(1.0)
        return None

    def scan_for_blocking_popup(self, items):
        for word in BLOCKING_POPUP_WORDS:
            hit = self.vision.find(items, (word,), min_score=0.42, contains=True)
            if hit:
                return word
        return None

    def try_close_safe_popup(self, win, items):
        w, h = int(win.width), int(win.height)
        region = (int(w * 0.15), int(h * 0.12), int(w * 0.90), int(h * 0.90))
        hit = self.vision.find(items, SAFE_POPUP_BUTTONS, min_score=0.48, region=region)
        if not hit:
            return False
        self.vision.click_item(win, hit, hit.text)
        self.log("已关闭一个可安全识别的普通提示。")
        time.sleep(0.8)
        return True

    def wait_qq_ready(self, win):
        deadline = time.time() + int(self.cfg["qq_start_timeout_seconds"])
        while time.time() < deadline:
            _, items = self.vision.scan(win)
            blocking = self.scan_for_blocking_popup(items)
            if blocking:
                path = save_failure(win, "qq-blocking-popup")
                raise RuntimeError(f"检测到需要人工处理的QQ界面“{blocking}”，未自动点击。截图：{path}")
            if self.try_close_safe_popup(win, items):
                continue
            ready_hits = self.qq_ready_score(items)
            if ready_hits >= 2:
                self.log(f"QQ音乐界面已就绪，命中 {ready_hits} 个界面标志。")
                return items
            time.sleep(1.2)
        path = save_failure(win, "qq-not-ready")
        raise RuntimeError(f"双击桌面QQ音乐后等待加载超时。截图：{path}")

    def playlist_candidates(self, win, items, heading: OCRItem):
        width, height = int(win.width), int(win.height)
        excluded_parts = (
            "创建的歌单", "自建歌单", "我的歌单", "收藏的歌单", "音乐馆", "视频", "电台", "我喜欢",
            "本地和下载", "最近播放", "试听列表", "歌单", "更多", "下载"
        )
        result = []
        for item in items:
            if item.score < 0.43:
                continue
            if item.cy <= heading.y2 + 2 or item.cy >= min(height - 70, heading.y2 + 430):
                continue
            if item.cx >= int(width * 0.36):
                continue
            text = (item.text or "").strip()
            if not text or len(text) > 36:
                continue
            nt = normalize(text)
            if any(normalize(part) in nt for part in excluded_parts):
                continue
            result.append(item)

        result.sort(key=lambda i: (i.cy, i.cx))
        dedup = []
        for item in result:
            if dedup and abs(item.cy - dedup[-1].cy) < 10:
                if item.score > dedup[-1].score:
                    dedup[-1] = item
                continue
            dedup.append(item)
        return dedup

    def qq_flow(self):
        win = self.current_vm()
        target_index = playlist_for_today(self.cfg["base_date"])
        self.log(f"开始 QQ音乐流程；今天目标：第 {target_index} 个歌单。")

        ready_items = self.start_qq_from_desktop(win)
        items = ready_items if ready_items is not None else self.wait_qq_ready(win)

        heading = self.vision.find(items, PLAYLIST_HEADINGS, min_score=0.43)
        if not heading:
            time.sleep(1.0)
            _, items = self.vision.scan(win)
            heading = self.vision.find(items, PLAYLIST_HEADINGS, min_score=0.43)
        if not heading:
            path = save_failure(win, "qq-no-playlist-heading")
            raise RuntimeError(f"没有找到“创建的歌单/自建歌单/我的歌单”。截图：{path}")

        candidates = self.playlist_candidates(win, items, heading)
        self.log("侧栏歌单候选：" + " | ".join(i.text for i in candidates[:8]))
        if len(candidates) < target_index:
            path = save_failure(win, "qq-not-enough-playlists")
            raise RuntimeError(f"只识别到 {len(candidates)} 个可用歌单候选，无法选择第 {target_index} 个。截图：{path}")

        target = candidates[target_index - 1]
        self.vision.click_item(win, target, f"第{target_index}个歌单：{target.text}")
        time.sleep(1.2)

        _, page_items = self.vision.scan(win)
        blocking = self.scan_for_blocking_popup(page_items)
        if blocking:
            path = save_failure(win, "qq-blocking-after-playlist")
            raise RuntimeError(f"进入歌单后检测到需要人工处理界面“{blocking}”。截图：{path}")

        play = self.vision.find(page_items, ("播放全部",), min_score=0.43, contains=True)
        if not play:
            path = save_failure(win, "qq-no-play-all")
            raise RuntimeError(f"已经进入歌单，但OCR没有找到“播放全部”。截图：{path}")
        self.vision.click_item(win, play, "播放全部")
        time.sleep(1.5)
        self.log(f"QQ音乐：已选择第 {target_index} 个歌单并点击“播放全部”。")
        return True

    def full_flow(self):
        self.log("========== 完整流程开始 ==========")
        self.ip_flow()
        time.sleep(0.8)
        self.qq_flow()
        self.log("========== 当前虚拟机流程完成 ==========")


if __name__ == "__main__":
    MusicVMAuto().mainloop()
