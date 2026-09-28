"""
AudioEnhancer - Windows 音频增强器 GUI
单实例 / 配置读写 / 自定义图标 / 美化布局
"""

from concurrent.futures import ThreadPoolExecutor
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from apo_manager import (
    APO_CONFIG_DIR,
    apply_effect,
    auto_configure_default_device,
    detect_active_effect,
    disable_effect,
    download_apo_installer,
    install_apo,
    is_apo_installed,
    list_apo_configs,
)
from effects import EFFECTS, get_effect_by_key, normalize_effect_key
from music_visualizer import MusicVisualizer
import settings


APP_NAME = "AudioEnhancer"
SERVER_NAME = "AudioEnhancerInstanceSvc"   # 单实例本地服务名
APO_DOWNLOAD_URL = "https://sourceforge.net/projects/equalizerapo/"

# 配色
C_BG = "#14181f"
C_PANEL = "#1b2029"
C_CARD = "#20262f"
C_CARD_BORDER = "#2e3642"
C_GOLD = "#f0c060"
C_GOLD_DIM = "#b8923f"
C_TEXT = "#e8eaed"
C_SUB = "#9aa3ad"
C_DIVIDER = "#2a3140"


def resource_path(name: str) -> Path:
    """打包后从 _MEIPASS 取资源，开发时取脚本目录"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return Path(base) / name


class TrayBridge(QtCore.QObject):
    """把 pystray 的后台线程安全地桥接到 Qt 主线程。"""

    show_requested = QtCore.pyqtSignal()
    toggle_requested = QtCore.pyqtSignal()
    quit_requested = QtCore.pyqtSignal()


class EffectCard(QtWidgets.QFrame):
    """单个音效卡片（图标 + 名称 + 描述）"""

    clicked = QtCore.pyqtSignal(str)

    def __init__(self, key: str, icon: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(84)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self.icon_label = QtWidgets.QLabel(icon)
        self.icon_label.setStyleSheet("font-size: 30px;")
        self.icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedWidth(40)
        layout.addWidget(self.icon_label)

        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(4)
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {C_TEXT};"
        )
        text_col.addWidget(self.title_label)

        self.sub_label = QtWidgets.QLabel(subtitle)
        self.sub_label.setStyleSheet(f"font-size: 12px; color: {C_SUB};")
        self.sub_label.setWordWrap(True)
        text_col.addWidget(self.sub_label)
        layout.addLayout(text_col)

        self.set_inactive()

    def set_active(self):
        self.setStyleSheet(
            f"EffectCard {{ background-color: #283042; border: 2px solid {C_GOLD}; "
            f"border-radius: 12px; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {C_GOLD};"
        )

    def set_inactive(self):
        self.setStyleSheet(
            f"EffectCard {{ background-color: {C_CARD}; border: 1px solid {C_CARD_BORDER}; "
            f"border-radius: 12px; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {C_TEXT};"
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self.key)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioEnhancer · 音频增强器")
        self.setMinimumSize(780, 620)
        self.resize(820, 710)
        self.setWindowIcon(QtGui.QIcon(str(resource_path("app.ico"))))

        self.tray_icon = None
        self._tray_bridge = TrayBridge(self)
        self._tray_bridge.show_requested.connect(self.show_window)
        self._tray_bridge.toggle_requested.connect(self.toggle_power)
        self._tray_bridge.quit_requested.connect(self.quit_app)
        self._setup_tray()

        self.active_key = None
        self._pending_close = False
        self._quitting = False
        self._installing = False
        self._audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-config")
        self._audio_request_id = 0
        self._managed_config_path: Path | None = None
        self._managed_key: str | None = None
        self._available_config_path: Path | None = None

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll_area)
        central = QtWidgets.QWidget()
        scroll_area.setWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(24, 22, 24, 18)
        main_layout.setSpacing(12)

        # ---- 顶部标题栏 ----
        header = QtWidgets.QHBoxLayout()
        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setPixmap(QtGui.QIcon(str(resource_path("app.ico"))).pixmap(40, 40))
        header.addWidget(icon_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(2)
        t = QtWidgets.QLabel("AudioEnhancer")
        t.setStyleSheet(f"font-size: 19px; font-weight: 800; color: {C_GOLD};")
        title_col.addWidget(t)
        st = QtWidgets.QLabel("Windows 系统级音频增强器")
        st.setStyleSheet(f"font-size: 11px; color: {C_SUB};")
        title_col.addWidget(st)
        header.addLayout(title_col)
        header.addStretch()

        self.power_btn = QtWidgets.QPushButton("音效：关")
        self.power_btn.setCheckable(True)
        self.power_btn.setMinimumSize(110, 38)
        self.power_btn.setStyleSheet(self._power_style(False))
        self.power_btn.toggled.connect(self.on_power_toggled)
        header.addWidget(self.power_btn)
        main_layout.addLayout(header)

        # 分隔线
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C_DIVIDER};")
        main_layout.addWidget(line)

        self.visualizer = MusicVisualizer()
        main_layout.addWidget(self.visualizer)

        # APO 状态
        self.apo_warning = QtWidgets.QLabel()
        self.apo_warning.setStyleSheet(f"color: {C_GOLD}; font-size: 12px;")
        self.apo_warning.setWordWrap(True)
        main_layout.addWidget(self.apo_warning)

        # 安装与设备维护放在同一行；正常使用时退为次要操作。
        setup_row = QtWidgets.QHBoxLayout()
        setup_row.addStretch()
        self.install_btn = QtWidgets.QPushButton("安装 Equalizer APO")
        self.install_btn.setMinimumHeight(32)
        self.install_btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.install_btn.clicked.connect(self.on_install_and_setup)
        setup_row.addWidget(self.install_btn)

        self.refresh_btn = QtWidgets.QPushButton("刷新设备")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.refresh_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C_PANEL}; color: {C_TEXT}; "
            f"border: 1px solid {C_CARD_BORDER}; border-radius: 8px; padding: 5px 12px; }}"
            f"QPushButton:hover {{ border-color: {C_GOLD}; }}"
        )
        self.refresh_btn.clicked.connect(lambda: self._refresh_device_list())
        setup_row.addWidget(self.refresh_btn)
        main_layout.addLayout(setup_row)

        # 音效区标题
        sec = QtWidgets.QHBoxLayout()
        sec_lbl = QtWidgets.QLabel("音效预设")
        sec_lbl.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {C_TEXT};")
        sec.addWidget(sec_lbl)
        main_layout.addLayout(sec)

        # 两列四行，让八个预设形成完整、对称的网格。
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(14)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.cards = {}
        cols = 2
        for idx, effect in enumerate(EFFECTS):
            row = idx // cols
            col = idx % cols
            card = EffectCard(effect.key, effect.icon, effect.name, effect.subtitle)
            card.clicked.connect(self.on_card_clicked)
            grid.addWidget(card, row, col)
            self.cards[effect.key] = card
        main_layout.addLayout(grid)
        main_layout.addStretch(1)

        self.setStyleSheet(f"QMainWindow {{ background-color: {C_BG}; }}")
        central.setStyleSheet(f"background-color: {C_BG};")
        scroll_area.viewport().setStyleSheet(f"background-color: {C_BG};")

        self._refresh_device_list()
        self._restore_settings()
        self.visualizer.motion_changed.connect(
            lambda enabled: settings.save_settings(animation_enabled=enabled)
        )

    # ---------------- 电源开关样式 ----------------
    def _power_style(self, on: bool) -> str:
        if on:
            return (
                f"QPushButton {{ background-color: {C_GOLD}; color: #1a1a1a; "
                f"border-radius: 19px; padding: 6px 16px; font-weight: 800; font-size: 13px; }}"
            )
        return (
            f"QPushButton {{ background-color: {C_PANEL}; color: {C_SUB}; "
            f"border: 1px solid {C_CARD_BORDER}; border-radius: 19px; "
            f"padding: 6px 16px; font-weight: 700; font-size: 13px; }}"
        )

    # ---------------- 设备列表 ----------------
    def _set_setup_action(self, label: str, primary: bool) -> None:
        self.install_btn.setText(label)
        self.install_btn.setStyleSheet(
            f"QPushButton {{ background-color: {C_GOLD if primary else C_PANEL}; "
            f"color: {'#1a1a1a' if primary else C_TEXT}; "
            f"border: 1px solid {C_GOLD if primary else C_CARD_BORDER}; "
            "border-radius: 8px; padding: 5px 12px; font-weight: 700; font-size: 12px; }"
        )

    def _refresh_device_list(self):
        previous_path = self.current_config_path()
        if not is_apo_installed():
            self._available_config_path = None
            self.apo_warning.setText(
                "⚠ 未检测到 Equalizer APO。安装后请启用默认播放设备。"
            )
            self.apo_warning.setStyleSheet(f"color: #ffaa44; font-size: 12px;")
            self._set_setup_action("安装 Equalizer APO", True)
            self.refresh_btn.setVisible(False)
            if previous_path and self.power_btn.isChecked():
                self._queue_audio_action(None, None)
            return

        configs = list_apo_configs()
        if not configs:
            self._available_config_path = None
            self.apo_warning.setText(
                "⚠ 未找到 Equalizer APO 主配置，请检查设备安装。"
            )
            self.apo_warning.setStyleSheet(f"color: {C_GOLD}; font-size: 12px;")
            self._set_setup_action("打开设备选择器", True)
            self.refresh_btn.setVisible(True)
            if previous_path and self.power_btn.isChecked():
                self._queue_audio_action(None, None)
            return

        self._available_config_path = configs[0]
        self.apo_warning.setText("✓ Equalizer APO 已就绪")
        self.apo_warning.setStyleSheet(f"color: #6fcf7f; font-size: 12px;")
        self._set_setup_action("设备设置", False)
        self.refresh_btn.setVisible(True)
        # 刷新时也重新生成 Device 指令，跟随 Windows 默认播放设备变化。
        if self.power_btn.isChecked() and self.active_key:
            self._queue_audio_action(self.active_key, self.current_config_path())

    # ---------------- 配置读写 / 恢复 ----------------
    def _restore_settings(self):
        s = settings.load_settings()
        self.visualizer.set_motion_enabled(s.get("animation_enabled", True))
        config_path = self.current_config_path()
        detected = detect_active_effect(config_path) if config_path else None
        detected = normalize_effect_key(detected)
        if detected and get_effect_by_key(detected):
            self._managed_config_path = config_path
            self._managed_key = detected

        eff = normalize_effect_key(s.get("effect", ""))
        enabled = s.get("enabled", False)
        if eff and get_effect_by_key(eff):
            self.active_key = eff
            if enabled and config_path is not None:
                self.power_btn.setChecked(True)
            else:
                # 仅高亮，不写入
                self.cards[eff].set_active()
        if detected and not (enabled and eff and get_effect_by_key(eff)):
            self._queue_audio_action(None, None)

    # ---------------- 安装 / 接管 ----------------
    def on_install_and_setup(self):
        if self._installing:
            return
        self._installing = True
        self.install_btn.setEnabled(False)
        self.install_btn.setText("正在处理，请稍候...")

        def status(msg):
            QtCore.QMetaObject.invokeMethod(
                self.install_btn, "setText",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, msg),
            )

        def worker():
            ok, msg = True, ""
            if not is_apo_installed():
                tmp = Path(tempfile.gettempdir()) / "EqualizerAPO_setup.exe"
                if not download_apo_installer(tmp, status):
                    ok = False
                    msg = ("下载 APO 失败（当前网络无法访问官方源）。\n"
                           "请从官方页面下载 1.4.2 x64 安装包，放到本程序同目录并命名为 EqualizerAPO_setup.exe，再重试：\n"
                           + APO_DOWNLOAD_URL)
                else:
                    ok, msg = install_apo(tmp, status)

            if ok:
                ok, msg = auto_configure_default_device(status)

            QtCore.QMetaObject.invokeMethod(
                self, "_on_setup_done",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, ok),
                QtCore.Q_ARG(str, msg),
            )

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.pyqtSlot(bool, str)
    def _on_setup_done(self, ok: bool, msg: str):
        self._installing = False
        self.install_btn.setEnabled(True)
        self._refresh_device_list()
        if ok:
            self._restore_settings()
        self._show_status(ok, msg)

    def current_config_path(self) -> Path | None:
        return self._available_config_path

    # ---------------- 图标 ----------------
    def _create_tray_image(self) -> Image.Image:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((2, 2, size - 2, size - 2), fill=(18, 22, 29, 255))
        bars = [0.4, 0.8, 0.55, 1.0, 0.65, 0.45]
        n = len(bars)
        pad = 14
        inner = size - 2 * pad
        gap = inner / (n * 2.2)
        bw = (inner - gap * (n - 1)) / n
        base = size - pad
        for i, h in enumerate(bars):
            x0 = pad + i * (bw + gap)
            x1 = x0 + bw
            y0 = base - (base - 16) * h
            r = max(1, bw * 0.45)
            fill = (240, 192, 96, 255) if i in (1, 3, 4) else (150, 120, 64, 255)
            d.rounded_rectangle([x0, y0, x1, base], radius=r, fill=fill)
        return img

    def _setup_tray(self):
        # pystray 的回调运行在它自己的线程，不能直接操作 Qt 控件。
        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", lambda *_: self._tray_bridge.show_requested.emit()),
            pystray.MenuItem("切换音效开关", lambda *_: self._tray_bridge.toggle_requested.emit()),
            pystray.MenuItem("退出", lambda *_: self._tray_bridge.quit_requested.emit()),
        )
        self.tray_icon = pystray.Icon(APP_NAME, self._create_tray_image(), APP_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True, name="tray").start()

    @QtCore.pyqtSlot()
    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @QtCore.pyqtSlot()
    def toggle_power(self):
        self.power_btn.toggle()

    # ---------------- 电源 / 卡片 ----------------
    def on_power_toggled(self, checked: bool):
        self.power_btn.setText("音效：开" if checked else "音效：关")
        self.power_btn.setStyleSheet(self._power_style(checked))
        if not checked:
            self.visualizer.set_active(False)
        if checked:
            if self.active_key is None:
                self.active_key = EFFECTS[0].key
            self._apply(self.active_key)
        else:
            self._disable()

    def on_card_clicked(self, key: str):
        self.active_key = key
        if not self.power_btn.isChecked():
            self.power_btn.setChecked(True)
        else:
            self._apply(key)

    def _apply(self, key: str):
        for k, card in self.cards.items():
            card.set_active() if k == key else card.set_inactive()

        config_path = self.current_config_path()
        if config_path is None:
            self.power_btn.blockSignals(True)
            self.power_btn.setChecked(False)
            self.power_btn.blockSignals(False)
            self.power_btn.setText("音效：关")
            self.power_btn.setStyleSheet(self._power_style(False))
            self.visualizer.set_active(False)
            self.apo_warning.setText("⚠ 请先选择扬声器设备")
            self.apo_warning.setStyleSheet(f"color: #ffaa44; font-size: 12px;")
            settings.save_settings(enabled=False, effect=self.active_key or "")
            return
        self._queue_audio_action(key, config_path)

    def _queue_audio_action(self, key: str | None, config_path: Path | None):
        """串行写入 APO；只展示最后一次用户操作的结果。"""
        self._audio_request_id += 1
        request_id = self._audio_request_id

        def worker():
            try:
                previous = self._managed_config_path
                if previous and (key is None or previous != config_path):
                    ok, msg = disable_effect(previous)
                    if not ok:
                        self._report_audio_result(request_id, False, msg)
                        return
                    self._managed_config_path = None
                    self._managed_key = None
                if key and config_path:
                    ok, msg = apply_effect(config_path, key)
                    if ok:
                        self._managed_config_path = config_path
                        self._managed_key = key
                else:
                    ok, msg = True, "已恢复默认音质"
                self._report_audio_result(request_id, ok, msg)
            except Exception as exc:
                self._report_audio_result(request_id, False, f"音效操作失败：{exc}")

        self._audio_executor.submit(worker)

    def _report_audio_result(self, request_id: int, ok: bool, msg: str):
        QtCore.QMetaObject.invokeMethod(
            self, "_on_audio_result", QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(int, request_id), QtCore.Q_ARG(bool, ok),
            QtCore.Q_ARG(str, msg),
            QtCore.Q_ARG(str, self._managed_key or ""),
        )

    @QtCore.pyqtSlot(int, bool, str, str)
    def _on_audio_result(self, request_id: int, ok: bool, msg: str, applied_key: str):
        if request_id != self._audio_request_id:
            return
        enabled = bool(applied_key)
        self.power_btn.blockSignals(True)
        self.power_btn.setChecked(enabled)
        self.power_btn.blockSignals(False)
        self.power_btn.setText("音效：开" if enabled else "音效：关")
        self.power_btn.setStyleSheet(self._power_style(enabled))
        self.visualizer.set_active(enabled)
        if applied_key:
            self.active_key = applied_key
        for key, card in self.cards.items():
            card.set_active() if key == applied_key else card.set_inactive()
        settings.save_settings(enabled=enabled, effect=self.active_key or "")
        self._show_status(ok, msg)

    def _show_status(self, ok: bool, msg: str):
        self.apo_warning.setText(("✓ " if ok else "⚠ ") + msg)
        color = "#6fcf7f" if ok else "#ffaa44"
        self.apo_warning.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _disable(self):
        for card in self.cards.values():
            card.set_inactive()

        self._queue_audio_action(None, None)

    # ---------------- 关闭 / 退出 ----------------
    def closeEvent(self, event):
        if self._pending_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        if self.tray_icon:
            try:
                self.tray_icon.notify("AudioEnhancer 已最小化到托盘", "点击托盘图标可重新打开")
            except Exception:
                pass

    @QtCore.pyqtSlot()
    def quit_app(self):
        # 恢复配置可能涉及磁盘/权限操作，不能阻塞 Qt 主线程。
        if self._quitting:
            return
        self._quitting = True
        self._pending_close = True
        def worker():
            if self._managed_config_path:
                ok, msg = disable_effect(self._managed_config_path)
                if not ok:
                    self._report_audio_result(self._audio_request_id, False, msg)
                    self._quitting = False
                    self._pending_close = False
                    return
                self._managed_config_path = None
                self._managed_key = None
            QtCore.QMetaObject.invokeMethod(
                self, "_finish_quit", QtCore.Qt.ConnectionType.QueuedConnection
            )

        self._audio_executor.submit(worker)

    @QtCore.pyqtSlot()
    def _finish_quit(self):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        QtWidgets.QApplication.quit()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # -------- 单实例检查（命名管道探测，跨进程可靠）--------
    if _is_already_running():
        _notify_existing_instance()   # 尽力激活已运行的实例
        sys.exit(0)

    # 确认自己是第一个后，尽早创建本地服务，缩短竞态窗口
    server = QLocalServer()
    server.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    window = MainWindow()

    def on_new_connection():
        # 不要在 GUI 线程 waitForReadyRead；第二次启动时会造成明显卡顿。
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            window.show_window()
            conn.disconnectFromServer()

    server.newConnection.connect(on_new_connection)

    window.show()
    sys.exit(app.exec())


# ----------------------- 单实例辅助 -----------------------
def _is_already_running() -> bool:
    """用 QLocalSocket 探测已有实例的本地服务（命名管道，跨进程可靠）。"""
    for _ in range(3):
        try:
            sock = QLocalSocket()
            sock.connectToServer(SERVER_NAME)
            ok = sock.waitForConnected(200)
            sock.close()
            if ok:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def _notify_existing_instance():
    """尽力通知已运行实例把窗口提到前台。"""
    try:
        sock = QLocalSocket()
        sock.connectToServer(SERVER_NAME)
        if sock.waitForConnected(500):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(500)
        sock.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
