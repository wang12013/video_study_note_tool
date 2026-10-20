from __future__ import annotations

from pathlib import Path

import httpx
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from video_notes.core import paths
from video_notes.core.config import Store


class _CheckThread(QThread):
    done = Signal(bool, str)

    def __init__(self, kind: str, key: str, base_url: str = "") -> None:
        super().__init__()
        self.kind = kind
        self.key = key
        self.base_url = base_url

    def run(self) -> None:
        try:
            if self.kind == "deepseek":
                url = (self.base_url or "https://api.deepseek.com").rstrip("/") + "/models"
                headers = {"Authorization": f"Bearer {self.key}"}
            else:
                url = "https://dashscope.aliyuncs.com/compatible-mode/v1/models"
                headers = {"Authorization": f"Bearer {self.key}"}
            response = httpx.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                self.done.emit(True, "连接成功")
            else:
                self.done.emit(False, f"HTTP {response.status_code}: {response.text[:120]}")
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, f"连接失败：{exc}")


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.store = Store()
        self._threads: list[QThread] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 16)
        outer.setSpacing(10)

        title = QLabel("设置")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        body_layout.addWidget(self._build_deepseek())
        body_layout.addWidget(self._build_dashscope())
        body_layout.addWidget(self._build_output())
        body_layout.addWidget(self._build_processing())
        body_layout.addWidget(self._build_bilibili())
        body_layout.addStretch(1)

        footer = QHBoxLayout()
        self.save_hint = QLabel("")
        self.save_hint.setStyleSheet("color: #0f766e;")
        save_button = QPushButton("保存设置")
        save_button.setFixedWidth(120)
        save_button.clicked.connect(self._save)
        footer.addWidget(self.save_hint, 1)
        footer.addWidget(save_button)
        outer.addLayout(footer)

        self._load()

    # ------------------------------------------------------------------
    def _build_deepseek(self) -> QGroupBox:
        box = QGroupBox("DeepSeek（文本生成）")
        form = QFormLayout(box)
        self.deepseek_key = QLineEdit()
        self.deepseek_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepseek_key.setPlaceholderText("sk-...")
        self.deepseek_base = QLineEdit()
        self.deepseek_model = QLineEdit()
        self.deepseek_test = QPushButton("测试连接")
        self.deepseek_test.setFixedWidth(100)
        self.deepseek_test.clicked.connect(lambda: self._check("deepseek", self.deepseek_key, self.deepseek_base, self.deepseek_test))
        key_row = QHBoxLayout()
        key_row.addWidget(self.deepseek_key, 1)
        key_row.addWidget(self.deepseek_test)
        form.addRow("API Key", key_row)
        form.addRow("Base URL", self.deepseek_base)
        form.addRow("模型", self.deepseek_model)
        return box

    def _build_dashscope(self) -> QGroupBox:
        box = QGroupBox("通义 DashScope（语音识别 + 视觉理解）")
        form = QFormLayout(box)
        self.dashscope_key = QLineEdit()
        self.dashscope_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.dashscope_key.setPlaceholderText("sk-...")
        self.dashscope_test = QPushButton("测试连接")
        self.dashscope_test.setFixedWidth(100)
        self.dashscope_test.clicked.connect(lambda: self._check("dashscope", self.dashscope_key, QLineEdit(), self.dashscope_test))
        key_row = QHBoxLayout()
        key_row.addWidget(self.dashscope_key, 1)
        key_row.addWidget(self.dashscope_test)
        form.addRow("API Key", key_row)
        self.region = QComboBox()
        self.region.addItems(["beijing（北京）", "singapore（新加坡）"])
        form.addRow("区域", self.region)
        self.asr_model = QLineEdit()
        form.addRow("语音识别模型", self.asr_model)
        self.vlm_model = QLineEdit()
        form.addRow("视觉模型", self.vlm_model)
        return box

    def _build_output(self) -> QGroupBox:
        box = QGroupBox("输出")
        form = QFormLayout(box)
        self.output_dir = QLineEdit()
        self.output_dir.setPlaceholderText(str(paths.default_library_dir()))
        browse = QPushButton("浏览…")
        browse.setFixedWidth(100)
        browse.clicked.connect(self._browse_output)
        row = QHBoxLayout()
        row.addWidget(self.output_dir, 1)
        row.addWidget(browse)
        form.addRow("笔记根目录", row)
        return box

    def _build_processing(self) -> QGroupBox:
        box = QGroupBox("处理")
        form = QFormLayout(box)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 3)
        form.addRow("同时处理视频数", self.concurrency)
        self.max_height = QComboBox()
        self.max_height.addItems(["720", "1080", "2160"])
        form.addRow("最大清晰度", self.max_height)
        self.max_slides = QSpinBox()
        self.max_slides.setRange(20, 400)
        self.max_slides.setSingleStep(10)
        form.addRow("单视频最大截图数", self.max_slides)
        self.retry = QSpinBox()
        self.retry.setRange(0, 5)
        form.addRow("失败重试次数", self.retry)
        return box

    def _build_bilibili(self) -> QGroupBox:
        box = QGroupBox("B 站账号")
        form = QFormLayout(box)
        self.login_status = QLabel("未登录")
        self.login_status.setStyleSheet("color: #b45309;")
        form.addRow("状态", self.login_status)
        self.login_button = QPushButton("扫码登录")
        self.login_button.setFixedWidth(100)
        self.login_button.setEnabled(False)
        self.login_button.setToolTip("下一步实现：扫码登录并保存 Cookie")
        self.import_button = QPushButton("导入 cookies.txt")
        self.import_button.setFixedWidth(140)
        self.import_button.clicked.connect(self._import_cookies)
        row = QHBoxLayout()
        row.addWidget(self.login_button)
        row.addWidget(self.import_button)
        row.addStretch(1)
        form.addRow("登录", row)
        return box

    # ------------------------------------------------------------------
    def _load(self) -> None:
        self.deepseek_key.setText(self.store.get_secret("deepseek_api_key"))
        self.deepseek_base.setText(self.store.get("deepseek_base_url") or "")
        self.deepseek_model.setText(self.store.get("deepseek_model") or "")
        self.dashscope_key.setText(self.store.get_secret("dashscope_api_key"))
        region = self.store.get("dashscope_region", "") or "beijing"
        self.region.setCurrentIndex(1 if region.startswith("singapore") else 0)
        self.asr_model.setText(self.store.get("asr_model") or "")
        self.vlm_model.setText(self.store.get("vlm_model") or "")
        self.output_dir.setText(self.store.get("output_dir") or "")
        self.concurrency.setValue(int(self.store.get("concurrency", "1") or 1))
        height = self.store.get("max_height", "1080") or "1080"
        self.max_height.setCurrentText(height)
        self.max_slides.setValue(int(self.store.get("max_slides", "150") or 150))
        self.retry.setValue(int(self.store.get("retry", "3") or 3))
        if self.store.get_secret("bilibili_cookie"):
            self.login_status.setText("已导入 Cookie")
            self.login_status.setStyleSheet("color: #047857;")

    def _save(self) -> None:
        self.store.set_secret("deepseek_api_key", self.deepseek_key.text().strip())
        self.store.set("deepseek_base_url", self.deepseek_base.text().strip())
        self.store.set("deepseek_model", self.deepseek_model.text().strip())
        self.store.set_secret("dashscope_api_key", self.dashscope_key.text().strip())
        self.store.set("dashscope_region", "singapore" if self.region.currentIndex() == 1 else "beijing")
        self.store.set("asr_model", self.asr_model.text().strip())
        self.store.set("vlm_model", self.vlm_model.text().strip())
        self.store.set("output_dir", self.output_dir.text().strip())
        self.store.set("concurrency", str(self.concurrency.value()))
        self.store.set("max_height", self.max_height.currentText())
        self.store.set("max_slides", str(self.max_slides.value()))
        self.store.set("retry", str(self.retry.value()))
        self.save_hint.setText("已保存")

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择笔记根目录", self.output_dir.text() or str(Path.home()))
        if path:
            self.output_dir.setText(path)

    def _import_cookies(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 cookies.txt", "", "Cookies (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore").strip()
        except OSError as exc:
            self.save_hint.setText(f"读取失败：{exc}")
            return
        if not text:
            self.save_hint.setText("文件为空")
            return
        self.store.set_secret("bilibili_cookie", text)
        self.login_status.setText("已导入 Cookie")
        self.login_status.setStyleSheet("color: #047857;")
        self.save_hint.setText("已导入 cookies.txt")

    def _check(self, kind: str, key_edit: QLineEdit, base_edit: QLineEdit, button: QPushButton) -> None:
        key = key_edit.text().strip()
        if not key:
            button.setText("请先填 Key")
            return
        button.setEnabled(False)
        button.setText("检测中…")
        thread = _CheckThread(kind, key, base_edit.text().strip() if base_edit else "")
        thread.done.connect(lambda ok, msg: self._on_check(ok, msg, button))
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_check(self, ok: bool, message: str, button: QPushButton) -> None:
        button.setEnabled(True)
        button.setText("连接成功" if ok else "连接失败")
        button.setToolTip(message)
        self.save_hint.setText(message)