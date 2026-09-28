"""Qt 绘制的装饰性音柱和漂浮音符，不采集系统音频。"""

import math
import time

from PyQt6 import QtCore, QtGui, QtWidgets


class MusicVisualizer(QtWidgets.QWidget):
    motion_changed = QtCore.pyqtSignal(bool)

    _BASE_HEIGHTS = (10, 17, 30, 42, 57, 72, 46, 80, 62, 104,
                     74, 58, 47, 66, 39, 27, 17, 10)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(96)
        self.setMinimumWidth(700)
        self.setAccessibleName("彩色音柱和音符动画")
        self._active = False
        self._started_at = time.monotonic()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.update)

        self.pause_button = QtWidgets.QPushButton("暂停动画", self)
        self.pause_button.setCheckable(True)
        self.pause_button.setChecked(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setFixedSize(84, 24)
        self.pause_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.pause_button.setToolTip("暂停或播放装饰动画")
        self.pause_button.setStyleSheet(
            "QPushButton { color: #b8c1cc; background: #27303d; border: 1px solid #455064; "
            "border-radius: 14px; font-size: 11px; }"
            "QPushButton:hover, QPushButton:focus { border-color: #b6a3fa; color: #ffffff; }"
        )
        self.pause_button.toggled.connect(self._on_motion_toggled)
        overlay = QtWidgets.QHBoxLayout(self)
        overlay.setContentsMargins(12, 8, 12, 8)
        overlay.addStretch()
        overlay.addWidget(self.pause_button, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        overlay.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

    def set_active(self, active: bool) -> None:
        if active and not self._active:
            self._started_at = time.monotonic()
        self._active = active
        self.pause_button.setEnabled(active)
        self._sync_timer()
        self.update()

    def set_motion_enabled(self, enabled: bool) -> None:
        self.pause_button.setChecked(enabled)

    def _on_motion_toggled(self, enabled: bool) -> None:
        self.pause_button.setText("暂停动画" if enabled else "播放动画")
        self._sync_timer()
        self.update()
        self.motion_changed.emit(enabled)

    def _sync_timer(self) -> None:
        if self._active and self.pause_button.isChecked() and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    @staticmethod
    def _bar_color(index: int) -> QtGui.QColor:
        midpoint = 9
        if index < midpoint:
            start, end = QtGui.QColor("#ff3f88"), QtGui.QColor("#d078ff")
            fraction = index / midpoint
        elif index == midpoint:
            return QtGui.QColor("#a6aaff")
        else:
            start, end = QtGui.QColor("#3cdec8"), QtGui.QColor("#3e66fa")
            fraction = (index - midpoint - 1) / 7
        return QtGui.QColor.fromRgb(
            round(start.red() + (end.red() - start.red()) * fraction),
            round(start.green() + (end.green() - start.green()) * fraction),
            round(start.blue() + (end.blue() - start.blue()) * fraction),
        )

    @staticmethod
    def _note(painter: QtGui.QPainter, x: float, y: float, color: QtGui.QColor,
              scale: float, double: bool = False) -> None:
        painter.save()
        painter.translate(x, y)
        painter.scale(scale, scale)
        painter.rotate(-13)
        pen = QtGui.QPen(color, 2.1)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QRectF(-7, 5, 8, 5))
        painter.drawLine(QtCore.QPointF(1, 7), QtCore.QPointF(1, -12))
        if double:
            painter.drawEllipse(QtCore.QRectF(4, 3, 8, 5))
            painter.drawLine(QtCore.QPointF(12, 5), QtCore.QPointF(12, -14))
            painter.drawLine(QtCore.QPointF(1, -12), QtCore.QPointF(12, -14))
        else:
            flag = QtGui.QPainterPath(QtCore.QPointF(1, -12))
            flag.cubicTo(11, -10, 10, -3, 5, -1)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(flag)
        painter.restore()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        bounds = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QtGui.QPen(QtGui.QColor("#303747"), 1))
        painter.setBrush(QtGui.QColor("#10141c"))
        painter.drawRoundedRect(bounds, 15, 15)
        painter.setClipPath(self._rounded_clip(bounds))

        moving = self._timer.isActive()
        t = time.monotonic() - self._started_at if moving else 0.0
        energy = 1.0 if self._active else 0.34
        center_x = self.width() / 2
        center_y = self.height() * 0.55
        step = min(20.0, (self.width() - 70) / (len(self._BASE_HEIGHTS) - 1))
        first_x = center_x - step * (len(self._BASE_HEIGHTS) - 1) / 2

        # 120 BPM 的四拍循环：低频落在一、三拍，高频在二、四拍回应。
        # 这是视觉节奏，不读取播放中的音频。
        beat = t * 2.0
        beat_index = int(beat) % 4
        beat_phase = beat % 1.0
        kick = math.exp(-beat_phase * 7.0) if beat_index in (0, 2) else 0.0
        snare = math.exp(-beat_phase * 8.0) if beat_index in (1, 3) else 0.0
        hat = math.exp(-((beat * 2.0) % 1.0) * 12.0)

        # 三层半透明线条形成柔和光晕；中心音柱保持画面的视觉锚点。
        for index, base_height in enumerate(self._BASE_HEIGHTS):
            bass_weight = max(0.0, 1.0 - abs(index - 8.5) / 9.0)
            if moving:
                wave = math.sin(t * 4.2 + index * 0.72)
                height = base_height * 0.56 * (
                    0.76 + 0.12 * wave + 0.68 * kick * bass_weight
                    + 0.55 * snare * (1.0 - bass_weight / 2.0)
                    + 0.18 * hat * (1.0 - bass_weight)
                )
            else:
                height = base_height * 0.43
            height = min(height, 70.0)
            x = first_x + index * step
            top = center_y - height / 2
            bottom = center_y + height / 2
            color = self._bar_color(index)
            for width, alpha in ((26, 13), (18, 27), (12, 60), (8, 235)):
                glow = QtGui.QColor(color)
                glow.setAlpha(round(alpha * energy))
                pen = QtGui.QPen(glow, width)
                pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, bottom))

        note_specs = (
            (-90, 21, "#ffb8e8", 0.82, False, 0.0),
            (78, 25, "#81eada", 0.72, True, 1.7),
            (145, 18, "#6599ef", 0.62, False, 3.2),
        )
        for dx, y, hex_color, scale, double, phase in note_specs:
            float_y = 3 * math.sin(t * 2.1 + phase) - 2 * (kick + snare) if moving else 0
            color = QtGui.QColor(hex_color)
            color.setAlpha(round(220 * energy))
            self._note(painter, center_x + dx, y + float_y, color, scale, double)
        painter.end()

    @staticmethod
    def _rounded_clip(bounds: QtCore.QRectF) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        path.addRoundedRect(bounds, 15, 15)
        return path
