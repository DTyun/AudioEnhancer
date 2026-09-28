"""
用户设置持久化（音效 / 开关 / 动画状态）
存储于 %LOCALAPPDATA%/AudioEnhancer/settings.json
"""

import json
import os
from pathlib import Path


def _settings_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home()
    d = base / "AudioEnhancer"
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


DEFAULTS = {
    "effect": "",      # 当前音效 key
    "enabled": False,  # 总开关是否开启
    "animation_enabled": True,  # 装饰动画是否播放
}


def load_settings() -> dict:
    try:
        p = _settings_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {key: data.get(key, default) for key, default in DEFAULTS.items()}
    except Exception:
        pass
    return dict(DEFAULTS)


def save_settings(**kwargs) -> None:
    data = load_settings()
    data.update(kwargs)
    try:
        _settings_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
