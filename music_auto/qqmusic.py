from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

try:
    import psutil
    import pyautogui
    from pywinauto import Desktop
except Exception:  # Import guard for non-Windows syntax checks.
    psutil = None
    pyautogui = None
    Desktop = None


class QQMusicAutomationError(RuntimeError):
    pass


class QQMusicAdapter:
    process_names = {"qqmusic.exe"}

    def __init__(self, config: dict, log: Callable[[str], None] = print):
        self.config = config
        self.log = log

    def _ensure_runtime(self) -> None:
        if psutil is None or pyautogui is None or Desktop is None:
            raise QQMusicAutomationError("QQ音乐自动化需要在 Windows 安装 requirements.txt 后运行")

    @staticmethod
    def _shortcut_candidates() -> list[Path]:
        home = Path(os.environ.get("USERPROFILE", str(Path.home())))
        public = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
        appdata = Path(os.environ.get("APPDATA", ""))
        programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        roots = [
            home / "Desktop",
            public / "Desktop",
            appdata / r"Microsoft\Windows\Start Menu\Programs",
            programdata / r"Microsoft\Windows\Start Menu\Programs",
        ]
        out: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("*.lnk"):
                    name = p.stem.lower()
                    if "qq音乐" in name or "qqmusic" in name:
                        out.append(p)
            except Exception:
                continue
        return out

    def _running_pids(self) -> list[int]:
        self._ensure_runtime()
        pids: list[int] = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if (proc.info["name"] or "").lower() in self.process_names:
                    pids.append(int(proc.info["pid"]))
            except Exception:
                continue
        return pids

    def launch(self) -> None:
        self._ensure_runtime()
        existing = self._running_pids()
        if existing:
            self.log("QQ音乐进程已经存在，直接等待主窗口")
            return

        exe_path = str(self.config.get("exe_path", "")).strip()
        if exe_path and Path(exe_path).exists():
            os.startfile(exe_path)  # type: ignore[attr-defined]
            self.log(f"已直接启动 QQ音乐：{exe_path}")
            return

        shortcuts = self._shortcut_candidates()
        if shortcuts:
            os.startfile(str(shortcuts[0]))  # type: ignore[attr-defined]
            self.log(f"已通过快捷方式启动 QQ音乐：{shortcuts[0].name}")
            return

        raise QQMusicAutomationError(
            "未找到 QQ音乐快捷方式。可在界面里填写 QQMusic.exe 路径后重试。"
        )

    def wait_main_window(self):
        self._ensure_runtime()
        timeout = float(self.config.get("launch_timeout_seconds", 30))
        deadline = time.time() + timeout
        best = None

        while time.time() < deadline:
            for pid in self._running_pids():
                try:
                    wins = Desktop(backend="uia").windows(process=pid, visible_only=True)
                except Exception:
                    continue
                for win in wins:
                    try:
                        rect = win.rectangle()
                        area = max(0, rect.width()) * max(0, rect.height())
                        if area < 120_000:
                            continue
                        if best is None or area > best[0]:
                            best = (area, win)
                    except Exception:
                        continue
            if best is not None:
                win = best[1]
                try:
                    win.set_focus()
                except Exception:
                    pass
                self.log("QQ音乐主窗口已出现")
                return win
            time.sleep(0.8)

        raise QQMusicAutomationError(f"等待 QQ音乐主窗口超时（{timeout:.0f}s）")

    def close_popups(self, main_window) -> int:
        """Close only separate/smaller QQMusic windows. Never click the main window's close button."""
        self._ensure_runtime()
        closed = 0
        main_rect = main_window.rectangle()
        main_area = max(1, main_rect.width() * main_rect.height())
        pids = self._running_pids()
        button_texts = set(self.config.get("popup_button_texts", []))

        for pid in pids:
            try:
                wins = Desktop(backend="uia").windows(process=pid, visible_only=True)
            except Exception:
                continue
            for win in wins:
                try:
                    if win.handle == main_window.handle:
                        continue
                    rect = win.rectangle()
                    area = max(0, rect.width() * rect.height())
                    # Only treat clearly smaller secondary windows as popups.
                    if area <= 0 or area >= main_area * 0.85:
                        continue

                    clicked = False
                    for btn in win.descendants(control_type="Button"):
                        try:
                            text = btn.window_text().strip()
                            if text in button_texts:
                                btn.click_input()
                                self.log(f"已关闭 QQ音乐弹窗：{text}")
                                closed += 1
                                clicked = True
                                time.sleep(0.3)
                                break
                        except Exception:
                            continue

                    if not clicked:
                        # ESC is safer than blindly clicking an X coordinate.
                        try:
                            win.set_focus()
                            pyautogui.press("esc")
                            self.log("检测到独立 QQ音乐弹窗，已尝试按 Esc 关闭")
                            closed += 1
                            time.sleep(0.3)
                        except Exception:
                            pass
                except Exception:
                    continue
        return closed

    @staticmethod
    def _relative_from_screen(main_window, screen_x: int, screen_y: int) -> dict:
        rect = main_window.rectangle()
        w = max(1, rect.width())
        h = max(1, rect.height())
        return {
            "x": round((screen_x - rect.left) / w, 6),
            "y": round((screen_y - rect.top) / h, 6),
        }

    @staticmethod
    def _screen_from_relative(main_window, rel: dict) -> tuple[int, int]:
        rect = main_window.rectangle()
        x = int(rect.left + float(rel["x"]) * rect.width())
        y = int(rect.top + float(rel["y"]) * rect.height())
        return x, y

    def capture_playlist_position(self, playlist_no: int, countdown_seconds: int = 3) -> dict:
        self._ensure_runtime()
        win = self.wait_main_window()
        try:
            win.set_focus()
        except Exception:
            pass
        self.log(f"请在 {countdown_seconds} 秒内把鼠标移动到歌单 {playlist_no} 文字中央…")
        for remaining in range(countdown_seconds, 0, -1):
            self.log(f"{remaining}…")
            time.sleep(1)
        pos = pyautogui.position()
        rel = self._relative_from_screen(win, int(pos.x), int(pos.y))
        self.log(f"歌单 {playlist_no} 已记录：相对位置 {rel}")
        return rel

    def play_playlist(self, playlist_no: int) -> None:
        self._ensure_runtime()
        if playlist_no not in (1, 2):
            raise QQMusicAutomationError("Demo 目前仅支持两个歌单")

        key = f"playlist_{playlist_no}_relative"
        rel = self.config.get(key)
        if not rel:
            raise QQMusicAutomationError(f"尚未校准歌单 {playlist_no} 的位置")

        win = self.wait_main_window()
        self.close_popups(win)
        try:
            win.set_focus()
        except Exception:
            pass
        time.sleep(0.5)
        x, y = self._screen_from_relative(win, rel)
        pyautogui.doubleClick(x=x, y=y, interval=0.15)
        self.log(f"已双击歌单 {playlist_no}：({x}, {y})")
