from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

DEFAULT_CONFIG = {
    "base_date": "2026-08-12",
    "proxy": {
        "window_title_regex": r".*老鱼.*",
        "verify_retries": 3,
        "verify_timeout_seconds": 15,
        "post_click_wait_seconds": 2.0,
        "success_mark": "√",
    },
    "qqmusic": {
        "exe_path": "",
        "launch_timeout_seconds": 30,
        "playlist_1_relative": None,
        "playlist_2_relative": None,
        "popup_button_texts": [
            "关闭", "取消", "稍后再说", "知道了", "以后再说", "暂不升级"
        ],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path = "config.json") -> dict:
    path = Path(path)
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg, path)
        return cfg
    with path.open("r", encoding="utf-8") as f:
        user_cfg = json.load(f)
    return _deep_merge(DEFAULT_CONFIG, user_cfg)


def save_config(config: dict, path: str | Path = "config.json") -> None:
    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
