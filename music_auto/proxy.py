from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

try:
    from pywinauto import Desktop
except Exception:  # Allows syntax/import checks on non-Windows development machines.
    Desktop = None


class ProxyAutomationError(RuntimeError):
    pass


@dataclass
class ProxyResult:
    ok: bool
    attempts: int
    message: str


class ProxyController:
    """Controls only two allowed UI targets: 线路设置 and 验证所有IP."""

    def __init__(self, config: dict, log: Callable[[str], None] = print):
        self.config = config
        self.log = log

    def _ensure_windows(self) -> None:
        if Desktop is None:
            raise ProxyAutomationError("pywinauto 仅能在安装依赖后的 Windows 环境运行")

    def _find_window(self):
        self._ensure_windows()
        title_re = self.config.get("window_title_regex", r".*老鱼.*")

        # UIA first, because TabItem/Button names are usually exposed more clearly.
        desktop = Desktop(backend="uia")
        candidates = desktop.windows(title_re=title_re, visible_only=True)
        if not candidates:
            raise ProxyAutomationError(f"未找到代理工具窗口：{title_re}")
        win = candidates[0]
        try:
            win.set_focus()
        except Exception:
            pass
        return win

    @staticmethod
    def _visible_texts(win) -> list[str]:
        texts: list[str] = []
        try:
            for ctrl in win.descendants():
                try:
                    text = ctrl.window_text().strip()
                    if text:
                        texts.append(text)
                except Exception:
                    continue
        except Exception:
            pass
        return texts

    def _click_line_settings(self, win) -> None:
        """Always force the second tab, 线路设置."""
        # 1) Prefer exact text match.
        try:
            tab = win.child_window(title="线路设置", control_type="TabItem")
            if tab.exists(timeout=2):
                tab.click_input()
                self.log("已切换到第二个 Tab：线路设置")
                return
        except Exception:
            pass

        # 2) Fallback: select index 1 from a Tab control.
        try:
            tabs = win.descendants(control_type="Tab")
            if tabs:
                tab_ctrl = tabs[0]
                items = tab_ctrl.children(control_type="TabItem")
                if len(items) >= 2:
                    items[1].click_input()
                    self.log("已按第 2 个 Tab 切换到线路设置")
                    return
        except Exception:
            pass

        raise ProxyAutomationError("找不到“线路设置”Tab，需要现场调整控件识别")

    def _click_verify_all(self, win) -> None:
        """Safety rule: only click 验证所有IP. Never click reload/delete/other line buttons."""
        try:
            btn = win.child_window(title="验证所有IP", control_type="Button")
            if btn.exists(timeout=2):
                btn.click_input()
                self.log("已点击：验证所有IP")
                return
        except Exception:
            pass

        # Fallback: exact visible-text scan, still only exact target text.
        try:
            for ctrl in win.descendants():
                try:
                    if ctrl.window_text().strip() == "验证所有IP":
                        ctrl.click_input()
                        self.log("已点击：验证所有IP（文本兜底）")
                        return
                except Exception:
                    continue
        except Exception:
            pass

        raise ProxyAutomationError("找不到“验证所有IP”按钮")

    def _has_success_mark(self, win) -> bool:
        mark = str(self.config.get("success_mark", "√"))
        texts = self._visible_texts(win)
        return any(mark in text for text in texts)

    def verify_ip(self) -> ProxyResult:
        retries = int(self.config.get("verify_retries", 3))
        timeout = float(self.config.get("verify_timeout_seconds", 15))
        post_wait = float(self.config.get("post_click_wait_seconds", 2.0))

        win = self._find_window()
        self._click_line_settings(win)
        time.sleep(0.5)

        for attempt in range(1, retries + 1):
            self.log(f"IP 验证：第 {attempt}/{retries} 次")
            self._click_verify_all(win)
            # Important: do not instantly accept an old √ still on screen.
            time.sleep(post_wait)

            deadline = time.time() + timeout
            while time.time() < deadline:
                if self._has_success_mark(win):
                    return ProxyResult(True, attempt, "IP 可用 √")
                time.sleep(0.8)

        return ProxyResult(False, retries, f"连续 {retries} 次未检测到 √")
