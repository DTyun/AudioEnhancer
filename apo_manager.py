"""Equalizer APO 主配置管理、安装包校验和设备选择器入口。"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import hashlib
from pathlib import Path

from device_enum import get_default_playback_device
from effects import build_apo_config, get_effect_by_key


# Equalizer APO 默认安装路径
APO_DEFAULT_PATH = Path(r"C:\Program Files\EqualizerAPO")
APO_CONFIG_DIR = APO_DEFAULT_PATH / "config"
APO_CONFIG_TXT = APO_CONFIG_DIR / "config.txt"
APO_EDITOR_EXE = APO_DEFAULT_PATH / "Editor.exe"
APO_DEVICE_SELECTOR_EXE = APO_DEFAULT_PATH / "DeviceSelector.exe"

# APO 安装包下载源（任选其一，按顺序尝试）
DOWNLOAD_URLS = [
    "https://downloads.sourceforge.net/project/equalizerapo/1.4.2/EqualizerAPO-x64-1.4.2.exe",
]
INSTALLER_SHA256 = "7403be7427bbe1936a40dded082829b6e217fc4f5990fee5cba501f0ae055afa"

# 与本程序同目录放置的安装包会被优先使用（避免运行时联网）
LOCAL_SETUP_NAME = "EqualizerAPO_setup.exe"

def is_apo_installed() -> bool:
    """检测 Equalizer APO 是否已安装"""
    return APO_DEFAULT_PATH.exists() and APO_EDITOR_EXE.exists()


def list_apo_configs() -> list[Path]:
    """Equalizer APO 自动加载的主配置文件。"""
    return [APO_CONFIG_TXT] if APO_CONFIG_TXT.is_file() else []


# ----------------------- 安装 APO -----------------------

def download_apo_installer(dest: Path, status_cb=None) -> bool:
    """下载或复用本地 APO 安装包。成功返回 True。"""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    local = base / LOCAL_SETUP_NAME
    if local.is_file() and _installer_hash_matches(local):
        try:
            shutil.copy2(local, dest)
            if status_cb:
                status_cb("已使用本地安装包")
            return True
        except Exception:
            pass

    for url in DOWNLOAD_URLS:
        try:
            if status_cb:
                status_cb(f"正在下载 Equalizer APO：{url}")
            urllib.request.urlretrieve(url, dest)
            if _installer_hash_matches(dest):
                return True
        except Exception:
            continue
    dest.unlink(missing_ok=True)
    return False


def _installer_hash_matches(path: Path) -> bool:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest() == INSTALLER_SHA256


def install_apo(setup_path: Path, status_cb=None) -> tuple[bool, str]:
    """
    静默安装 Equalizer APO（NSIS /S 参数）。
    返回 (success, message)
    """
    if not setup_path.exists():
        return False, "安装包不存在"
    if not _installer_hash_matches(setup_path):
        return False, "安装包校验失败，请从 Equalizer APO 官方页面获取 1.4.2 x64 版本。"
    try:
        if status_cb:
            status_cb("正在静默安装 APO...")
        # 0x08000000 = CREATE_NO_WINDOW
        proc = subprocess.run(
            [str(setup_path), "/S"],
            capture_output=True,
            text=True,
            creationflags=0x08000000,
            timeout=180,
        )
        # 3010 表示需要重启
        if proc.returncode not in (0, 3010):
            return False, f"安装返回错误码 {proc.returncode}\n{proc.stderr[:300]}"
        time.sleep(2)
        if is_apo_installed():
            return True, "Equalizer APO 安装成功"
        return False, "安装程序已结束，但未检测到 Equalizer APO。请检查安装路径。"
    except Exception as e:
        return False, f"安装异常：{e}"


def auto_configure_default_device(status_cb=None) -> tuple[bool, str]:
    """打开官方设备选择器，由用户启用默认播放设备。"""
    if not is_apo_installed():
        return False, "APO 尚未安装"
    if not APO_DEVICE_SELECTOR_EXE.is_file():
        return False, "未找到 Equalizer APO 设备选择器，请检查安装。"
    _, name = get_default_playback_device()
    try:
        subprocess.Popen([str(APO_DEVICE_SELECTOR_EXE)], cwd=str(APO_DEFAULT_PATH))
        label = name or "默认播放设备"
        return True, f"请在 Equalizer APO 设备选择器中勾选「{label}」，保存后按提示重启。"
    except OSError as exc:
        return False, f"打开设备选择器失败：{exc}"


# ----------------------- 配置写入 / 应用 / 恢复 -----------------------

def backup_original_config(config_path: Path) -> Path | None:
    """备份本次会话的原始配置；失败时禁止覆盖用户配置。"""
    backup = config_path.with_suffix(".original.txt")
    try:
        # 崩溃后仍带有本程序标记时，保留上次会话的原始备份。
        if detect_active_effect(config_path):
            return backup if backup.exists() else None
        shutil.copy2(config_path, backup)
        return backup
    except OSError:
        return None


def restore_original_config(config_path: Path) -> bool:
    """用原始备份恢复配置"""
    backup = config_path.with_suffix(".original.txt")
    if not backup.exists():
        return False
    try:
        fd, tmp = tempfile.mkstemp(dir=config_path.parent, suffix=".txt")
        os.close(fd)
        try:
            shutil.copy2(backup, tmp)
            os.replace(tmp, config_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        backup.unlink()
        return True
    except OSError:
        return False


def write_config(config_path: Path, text: str) -> bool:
    """写入 APO 配置，失败返回 False"""
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=config_path.parent, suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, config_path)
            return True
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        print(f"写入 APO 配置失败: {e}", file=sys.stderr)
        return False


def apply_effect(config_path: Path, key: str) -> tuple[bool, str]:
    """在指定 APO 配置文件上应用指定音效。"""
    if not is_apo_installed():
        return False, "未检测到 Equalizer APO。\n请先安装：https://sourceforge.net/projects/equalizerapo/"

    effect = get_effect_by_key(key)
    if effect is None:
        return False, "未知音效预设"
    endpoint_id, _ = get_default_playback_device()
    device_guid = re.search(r"\{[0-9a-fA-F-]{36}\}$", endpoint_id or "")
    if device_guid is None:
        return False, "无法识别默认播放设备，请检查 Windows 音频设备。"
    cfg_text = build_apo_config(effect, device_guid.group())

    if backup_original_config(config_path) is None:
        return False, "备份原始配置失败，未修改音效。请检查管理员权限。"

    if write_config(config_path, cfg_text):
        name = effect.name if effect else "原声"
        return True, f"已应用：{name}"
    else:
        return False, "写入配置失败，请右键「以管理员身份运行」本程序后重试。"


def disable_effect(config_path: Path) -> tuple[bool, str]:
    """关闭指定配置文件上的音效，恢复默认"""
    if not is_apo_installed():
        return True, "APO 未安装，无需恢复。"

    if restore_original_config(config_path):
        return True, "已恢复默认音质"
    else:
        return False, "恢复默认失败，请右键「以管理员身份运行」本程序后重试。"


def detect_active_effect(config_path: Path) -> str | None:
    """读取 APO 配置文件，识别当前生效的音效 key。无则返回 None。"""
    try:
        text = config_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = re.search(r"#\s*ActiveEffect:\s*([A-Za-z0-9_-]+)", text)
    if m:
        return m.group(1)
    return None
