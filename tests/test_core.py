import ctypes
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import apo_manager
import device_enum
import settings
from effects import EFFECTS, build_apo_config, normalize_effect_key


class ConfigTests(unittest.TestCase):
    def test_legacy_device_setting_is_dropped_on_save(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            path = Path(directory) / "AudioEnhancer" / "settings.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"device": "obsolete", "effect": "hifi"}), encoding="utf-8")
            settings.save_settings(enabled=True)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("device", saved)
            self.assertEqual(saved["effect"], "hifi")

    def test_removed_preset_maps_to_current_soundstage(self):
        self.assertEqual(normalize_effect_key("3d"), "surround360")
        self.assertNotIn("3d", [preset.key for preset in EFFECTS])

    def test_each_preset_has_one_preamp(self):
        for preset in EFFECTS:
            with self.subTest(preset=preset.key):
                preamps = [line for line in build_apo_config(preset).splitlines()
                           if line.startswith("Preamp:")]
                self.assertEqual(preamps, [f"Preamp: {preset.preamp} dB"])
                if preset.channel_delay[1] > 0:
                    self.assertIn("Channel: R\nDelay: ", build_apo_config(preset))

    def test_guid_and_property_layout(self):
        guid = device_enum.GUID.parse("BCDE0395-E52F-467C-8E3D-C4579291692E")
        self.assertEqual(ctypes.sizeof(guid), 16)
        self.assertEqual(ctypes.sizeof(device_enum.PROPERTYKEY), 20)
        self.assertEqual(ctypes.sizeof(device_enum.PROPVARIANT), 24)
        self.assertEqual(guid.Data1, 0xBCDE0395)

    def test_reapply_preserves_original_and_restore_recovers_it(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.txt"
            original = b"Preamp: -1 dB\r\n# user config\r\n"
            config.write_bytes(original)
            with mock.patch.object(apo_manager, "is_apo_installed", return_value=True), \
                 mock.patch.object(apo_manager, "get_default_playback_device", return_value=("{0.0.0.00000000}.{d71c6436-fb3c-40f4-a90a-39116d82097e}", "Headphones")):
                self.assertTrue(apo_manager.apply_effect(config, "smart")[0])
                self.assertIn("Device: {d71c6436-fb3c-40f4-a90a-39116d82097e}", config.read_text(encoding="utf-8"))
                self.assertTrue(apo_manager.apply_effect(config, "rock")[0])
                self.assertTrue(apo_manager.disable_effect(config)[0])
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse(config.with_suffix(".original.txt").exists())

    def test_missing_backup_does_not_overwrite_active_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.txt"
            active = build_apo_config(EFFECTS[0])
            config.write_text(active, encoding="utf-8")
            with mock.patch.object(apo_manager, "is_apo_installed", return_value=True), \
                 mock.patch.object(apo_manager, "get_default_playback_device", return_value=("{0.0.0.00000000}.{d71c6436-fb3c-40f4-a90a-39116d82097e}", "Headphones")):
                self.assertFalse(apo_manager.apply_effect(config, "rock")[0])
            self.assertEqual(config.read_text(encoding="utf-8"), active)


class UiTests(unittest.TestCase):
    def test_music_animation_follows_effect_and_can_pause(self):
        from PyQt6 import QtWidgets
        from music_visualizer import MusicVisualizer

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        visualizer = MusicVisualizer()
        visualizer.show()
        app.processEvents()
        self.assertEqual(visualizer.height(), 96)
        self.assertFalse(visualizer._timer.isActive())
        self.assertFalse(visualizer.pause_button.isEnabled())
        visualizer.set_active(True)
        self.assertTrue(visualizer._timer.isActive())
        self.assertTrue(visualizer.pause_button.isEnabled())
        visualizer.pause_button.setChecked(False)
        self.assertFalse(visualizer._timer.isActive())
        self.assertEqual(visualizer.pause_button.text(), "播放动画")
        visualizer.pause_button.setChecked(True)
        self.assertTrue(visualizer._timer.isActive())
        visualizer.set_active(False)
        self.assertFalse(visualizer._timer.isActive())
        visualizer.set_active(True)
        self.assertTrue(visualizer._timer.isActive())
        visualizer.hide()
        self.assertFalse(visualizer._timer.isActive())
        visualizer.deleteLater()

    def test_startup_restores_leftover_effect_when_saved_off(self):
        from PyQt6 import QtWidgets
        import main

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        config = main.APO_CONFIG_DIR / "config.txt"
        restored = []
        with mock.patch.object(main.MainWindow, "_setup_tray"), \
             mock.patch.object(main, "is_apo_installed", return_value=True), \
             mock.patch.object(main, "list_apo_configs", return_value=[config]), \
             mock.patch.object(main, "detect_active_effect", return_value="smart"), \
             mock.patch.object(main.settings, "load_settings", return_value={"enabled": False}), \
             mock.patch.object(main.settings, "save_settings"), \
             mock.patch.object(main, "disable_effect", side_effect=lambda p: (restored.append(p) or (True, "ok"))):
            window = main.MainWindow()
            try:
                window._audio_executor.submit(lambda: None).result(timeout=5)
                app.processEvents()
                self.assertEqual(restored, [config])
                self.assertFalse(window.power_btn.isChecked())
            finally:
                window._audio_executor.shutdown(wait=True)
                window.deleteLater()

    def test_failed_apply_keeps_power_off_and_shows_warning(self):
        from PyQt6 import QtWidgets
        import main

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        config = main.APO_CONFIG_DIR / "config.txt"
        with mock.patch.object(main.MainWindow, "_setup_tray"), \
             mock.patch.object(main, "is_apo_installed", return_value=True), \
             mock.patch.object(main, "list_apo_configs", return_value=[config]), \
             mock.patch.object(main.settings, "load_settings", return_value={}), \
             mock.patch.object(main.settings, "save_settings"), \
             mock.patch.object(main, "apply_effect", return_value=(False, "写入失败")):
            window = main.MainWindow()
            try:
                window.on_card_clicked("smart")
                window._audio_executor.submit(lambda: None).result(timeout=5)
                app.processEvents()
                self.assertFalse(window.power_btn.isChecked())
                self.assertIn("⚠ 写入失败", window.apo_warning.text())
            finally:
                window._audio_executor.shutdown(wait=True)
                window.deleteLater()

    def test_refresh_reapplies_current_default_device_then_off_restores(self):
        from PyQt6 import QtWidgets
        import main

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        config = main.APO_CONFIG_DIR / "config.txt"
        operations = []
        with mock.patch.object(main.MainWindow, "_setup_tray"), \
             mock.patch.object(main, "is_apo_installed", return_value=True), \
             mock.patch.object(main, "list_apo_configs", return_value=[config]), \
             mock.patch.object(main.settings, "load_settings", return_value={}), \
             mock.patch.object(main.settings, "save_settings"), \
             mock.patch.object(main, "apply_effect", side_effect=lambda p, k: (operations.append(("apply", p, k)) or (True, "ok"))), \
             mock.patch.object(main, "disable_effect", side_effect=lambda p: (operations.append(("restore", p)) or (True, "ok"))):
            window = main.MainWindow()
            try:
                window.on_card_clicked("smart")
                window._refresh_device_list()
                window.power_btn.setChecked(False)
                window._audio_executor.submit(lambda: None).result(timeout=5)
                app.processEvents()
                self.assertEqual(operations, [
                    ("apply", config, "smart"),
                    ("apply", config, "smart"),
                    ("restore", config),
                ])
                self.assertFalse(window.power_btn.isChecked())
            finally:
                window._audio_executor.shutdown(wait=True)
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
