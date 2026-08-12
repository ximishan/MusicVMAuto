from __future__ import annotations

import time

import pyautogui

import host_controller as base


base.VERSION = "0.5.4-three-click-ip"


def find_verify_with_retries(app, win, min_score: float, tries: int = 5, delay: float = 0.55):
    items = []
    for scan_no in range(1, tries + 1):
        _, items = app.vision.scan(win)
        verify = app.find_verify_button(items, min_score)
        if verify:
            return items, verify
        if scan_no < tries:
            app.log(f"暂未识别到“验证所有IP”，重新OCR {scan_no}/{tries}。")
            time.sleep(delay)
    return items, None


def ensure_line_settings_page(app, win, min_score: float):
    # 先判断当前是否已经在线路设置页。只以“验证所有IP”这个大文字按钮作为页面证据，
    # 不再依赖很小的 √ 符号。
    items, verify = find_verify_with_retries(app, win, min_score, tries=2, delay=0.35)
    if verify:
        app.log("当前已经在线路设置页：已识别到“验证所有IP”。")
        return verify

    # 不在目标页时，只允许点击“线路设置”。每次点击后重新OCR验证页面是否真的切换。
    for click_try in range(1, 4):
        tab = app.vision.find(
            items,
            ("线路设置",),
            min_score=max(0.38, min_score - 0.06),
            contains=True,
        )
        if not tab:
            app.log(f"切换线路设置第 {click_try}/3 次：未识别到Tab，重新OCR。")
            time.sleep(0.45)
            _, items = app.vision.scan(win)
            tab = app.vision.find(
                items,
                ("线路设置",),
                min_score=max(0.38, min_score - 0.06),
                contains=True,
            )
            if not tab:
                continue

        app.log(f"切换线路设置第 {click_try}/3 次：已定位Tab，发送点击。")
        app.vision.click_item(win, tab, "线路设置")
        time.sleep(0.55)

        items, verify = find_verify_with_retries(app, win, min_score, tries=4, delay=0.45)
        if verify:
            app.log("已确认线路设置页面切换成功：识别到“验证所有IP”。")
            return verify

        app.log("本次点击后仍未识别到“验证所有IP”，重新定位同一个Tab再试。")

    path = base.save_failure(win, "ip-line-settings-or-verify-not-found")
    raise RuntimeError(f"无法确认进入线路设置页：多次点击后仍未识别到“验证所有IP”。截图：{path}")


def ip_flow_three_click(self):
    win = self.current_vm()
    min_score = float(self.cfg["ocr_min_score"])
    wait_seconds = max(1, int(self.cfg.get("ip_result_wait_seconds", 8)))

    self.log("开始 IP 验证：进入线路设置后，固定点击“验证所有IP”3次。")
    self.log("本版不再依赖 √ 判断是否成功；√ 只做最终日志参考，避免OCR漏识别导致误报失败。")

    verify = ensure_line_settings_page(self, win, min_score)

    for attempt in range(1, 4):
        if attempt > 1:
            _, verify = find_verify_with_retries(self, win, min_score, tries=4, delay=0.45)
            if not verify:
                path = base.save_failure(win, f"ip-no-verify-button-{attempt}")
                raise RuntimeError(
                    f"准备第 {attempt}/3 次验证时，多次OCR仍未找到“验证所有IP”。"
                    f"为防止误点已停止。截图：{path}"
                )

        self.log(f"固定执行“验证所有IP”第 {attempt}/3 次。")
        self.vision.click_item(win, verify, "验证所有IP")
        pyautogui.moveTo(int(win.left + win.width - 12), int(win.top + 40), duration=0.12)

        self.log(f"第 {attempt}/3 次已点击，等待 {wait_seconds} 秒让验证完成。")
        time.sleep(wait_seconds)

    # 三次固定点击完成后，不再用 √ 决定成败。能识别到就记录，识别不到也继续。
    try:
        _, result_items = self.vision.scan(win)
        if self.vision.has_checkmark(result_items):
            self.log("固定3次验证完成；最终OCR也检测到 √。IP步骤完成。")
        else:
            self.log("固定3次验证完成；最终OCR未识别到 √，但本版不再因此判失败。IP步骤完成。")
    except Exception as e:
        self.log(f"固定3次验证已经完成；最终状态OCR读取失败（{e}），不影响IP步骤完成。")

    return True


base.MusicVMAuto.ip_flow = ip_flow_three_click


class MusicVMAuto(base.MusicVMAuto):
    def __init__(self):
        super().__init__()
        self.title("MusicVMAuto v0.5.4 - 固定三次IP验证")

    def _startup(self):
        self.log(f"版本：{base.VERSION}")
        self.log(f"配置文件：{base.CONFIG_PATH}")
        self.log("VMware最小化仍会自动恢复。")
        self.log("IP流程：进入线路设置后固定点击“验证所有IP”3次；不再依赖√作为成功门槛。")
        self.log("QQ启动仍然只允许OCR双击桌面“QQ音乐”图标。")


if __name__ == "__main__":
    MusicVMAuto().mainloop()
