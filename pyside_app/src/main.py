#!/usr/bin/env python3
"""Minimal PySide6 starter app.
Run with: python -m src.main
"""
import sys
import os
import json
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QListWidget,
    QMessageBox,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 Starter App")

        # Configuration
        self.default_spine_exe = r"C:\Program Files\Spine\Spine.exe"
        self.config = {}
        self.config_path = self._make_config_path()
        self._load_config()

        central = QWidget()
        layout = QVBoxLayout()

        # Spine exe (hardcoded display)
        exe_layout = QHBoxLayout()
        exe_label = QLabel("Spine EXE:")
        self.exe_display = QLineEdit(self.config.get("spine_exe", self.default_spine_exe))
        self.exe_display.setReadOnly(True)
        exe_layout.addWidget(exe_label)
        exe_layout.addWidget(self.exe_display)

        # Folder selection for Spine files
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Spine files folder:")
        self.folder_display = QLineEdit(self.config.get("spine_folder", ""))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_display)
        folder_layout.addWidget(browse_btn)

        # File list panel
        self.list_widget = QListWidget()

        layout.addLayout(exe_layout)
        layout.addLayout(folder_layout)
        layout.addWidget(QLabel("Spine files in folder:"))
        layout.addWidget(self.list_widget)

        central.setLayout(layout)
        self.setCentralWidget(central)

        # Populate initial file list
        if self.folder_display.text():
            self.refresh_file_list()

    def _make_config_path(self):
        loc = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        if not loc:
            loc = os.path.join(os.path.expanduser("~"), ".pyside_spine_app")
        os.makedirs(loc, exist_ok=True)
        return os.path.join(loc, "config.json")

    def _load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    self.config = json.load(fh)
        except Exception:
            self.config = {}

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(self.config, fh, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Could not save config: {e}")

    def browse_folder(self):
        start = self.folder_display.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Select Spine files folder", start)
        if folder:
            self.folder_display.setText(folder)
            self.config["spine_folder"] = folder
            # Keep the spine exe in config too (though it's hardcoded by default)
            self.config.setdefault("spine_exe", self.default_spine_exe)
            self._save_config()
            self.refresh_file_list()

    def refresh_file_list(self):
        folder = self.folder_display.text()
        self.list_widget.clear()
        if not folder or not os.path.isdir(folder):
            return
        try:
            files = sorted(os.listdir(folder), key=lambda s: s.lower())
            for name in files:
                if name.lower().endswith(".spine"):
                    self.list_widget.addItem(name)
        except Exception as e:
            QMessageBox.warning(self, "Read Error", f"Could not read folder: {e}")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
