from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from .proxy import ProxyController
from .qqmusic import QQMusicAdapter
from .rotation import playlist_for_day


@dataclass
class RunResult:
    ok: bool
    stage: str
    message: str
    playlist_no: int | None = None


def run_once(config: dict, log: Callable[[str], None] = print) -> RunResult:
    playlist_no = playlist_for_day(config["base_date"], date.today())
    log(f"今日应播放：歌单 {playlist_no}")

    proxy = ProxyController(config["proxy"], log=log)
    proxy_result = proxy.verify_ip()
    if not proxy_result.ok:
        return RunResult(False, "proxy", proxy_result.message, playlist_no)
    log(f"IP 验证成功：{proxy_result.message}")

    qq = QQMusicAdapter(config["qqmusic"], log=log)
    qq.launch()
    main_win = qq.wait_main_window()
    qq.close_popups(main_win)
    qq.play_playlist(playlist_no)

    return RunResult(True, "done", f"已执行歌单 {playlist_no} 双击播放", playlist_no)
