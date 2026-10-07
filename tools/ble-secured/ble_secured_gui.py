#!/usr/bin/env python3
"""电表加密 BLE 体验工具（客户版 · Lite/Pro）

安全通道: A003 / 写 C313 / 读 C314 / 通知 C315。
配网码：机身二维码下方 11 位（或 8 位 PIN）。Wi-Fi 仅 2.4 GHz。不含未发布通断器。

  py -3 -m pip install -r requirements.txt
  py -3 ble_secured_gui.py
"""

from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ble_crypto_core import (  # noqa: E402
    ADV_COMPANY_ID,
    PROTOCOL_VERSION_FALLBACK,
    SERVICE_UUID,
    BleSecureClient,
    CacheStore,
    ProtocolError,
    decrypt_long_manufacturer,
    default_cache_path,
    pin_from_manual_pairing_code,
    extract_manufacturer_blob,
    infer_sn,
    parse_long_adv_fields,
)
from command_help import (  # noqa: E402
    decode_function_map,
    format_comm_config,
    format_model_snapshot,
    help_text,
    meter_rows,
    one_click_buttons,
    wifi_ip_status,
)

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont, QTextOption
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("py -3 -m pip install PyQt6") from exc

try:
    from bleak import BleakClient, BleakScanner
except ImportError as exc:  # pragma: no cover
    raise SystemExit("py -3 -m pip install bleak") from exc

DEVICE_NAME_FILTERS = ("SDM", "SPM", "SXM", "Pulse")
GATT_DROP = "__GATT_DROP__"


def parse_wifi_list(response: dict[str, Any]) -> list[tuple[str, int]]:
    data = response.get("d") or {}
    raw = str(data.get("list") or "") if isinstance(data, dict) else str(data)
    items: list[tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "|" in part:
            ssid, rssi_s = part.rsplit("|", 1)
            try:
                items.append((ssid, int(rssi_s)))
            except ValueError:
                items.append((part, 0))
        else:
            items.append((part, 0))
    return items


class BleSecuredWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("电表加密 BLE 体验工具（Lite/Pro · A003）")
        self.resize(1180, 860)
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        self._client: Optional[BleakClient] = None
        self._transport: Optional[BleSecureClient] = None
        self._devices: list[Any] = []
        self._want_link = False
        self._reconnect_busy = False
        self._last_address = ""
        self._last_name = ""
        self._status_ble = "未连接"
        self._status_wifi = "尚未查询"
        self._status_comm = "尚未查询"
        self._model_d: dict[str, Any] = {}
        self._mqtt_d: dict[str, Any] = {}
        self._udp_d: Any = None
        self._fmap_raw: Any = None
        self._lang = "zh"
        self._quick_btns: list[tuple[QPushButton, str]] = []
        self._cache = CacheStore(default_cache_path())
        self._adv_scanner: Optional[BleakScanner] = None
        self._adv_watching = False
        self._adv_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._broadcast_key: Optional[bytes] = None
        self._build_ui()
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(120)
        self._adv_timer = QTimer(self)
        self._adv_timer.timeout.connect(self._drain_adv_queue)
        self._adv_timer.start(200)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro: Any) -> asyncio.Future[Any]:
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _hint(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet("color:#666;font-size:12px;")
        return lab

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left_host = QWidget()
        left = QVBoxLayout(left_host)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language / 语言"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("中文", "zh")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        left.addLayout(lang_row)

        self.conn_box = QGroupBox("设备连接（加密服务 0xA003 · 勿用 A002）")
        conn_layout = QVBoxLayout(self.conn_box)
        row1 = QHBoxLayout()
        self.pin_lbl = QLabel("配网码（11 位）")
        row1.addWidget(self.pin_lbl)
        self.pin_edit = QLineEdit()
        self.pin_edit.setPlaceholderText("二维码下方 11 位，或 8 位 PIN")
        self.pin_edit.setMaxLength(11)
        row1.addWidget(self.pin_edit)
        row1.addWidget(QLabel("SN"))
        self.sn_edit = QLineEdit()
        self.sn_edit.setPlaceholderText("可空=从广播名推断")
        row1.addWidget(self.sn_edit)
        row1.addWidget(QLabel("扫描(秒)"))
        self.scan_timeout_spin = QSpinBox()
        self.scan_timeout_spin.setRange(3, 60)
        self.scan_timeout_spin.setValue(8)
        row1.addWidget(self.scan_timeout_spin)
        conn_layout.addLayout(row1)
        self.auto_reconnect_chk = QCheckBox("设备重启后自动重连 GATT（推荐）")
        self.auto_reconnect_chk.setChecked(True)
        conn_layout.addWidget(self.auto_reconnect_chk)
        self.debug_keys_chk = QCheckBox("调试模式：日志可含密钥材料（默认关）")
        self.debug_keys_chk.setChecked(False)
        conn_layout.addWidget(self.debug_keys_chk)
        row2 = QHBoxLayout()
        self.scan_btn = QPushButton("扫描")
        self.scan_btn.clicked.connect(self._on_scan)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._on_connect)
        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.clicked.connect(self._on_user_disconnect)
        self.hs_btn = QPushButton("安全握手")
        self.hs_btn.clicked.connect(self._on_handshake)
        for b in (self.scan_btn, self.connect_btn, self.disconnect_btn, self.hs_btn):
            row2.addWidget(b)
        self.conn_label = QLabel("未连接")
        self.conn_label.setStyleSheet("color:#888;")
        row2.addWidget(self.conn_label)
        row2.addStretch()
        conn_layout.addLayout(row2)
        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(90)
        self.device_list.currentRowChanged.connect(self._on_device_row)
        conn_layout.addWidget(self.device_list)
        left.addWidget(self.conn_box)

        self.wifi_box = QGroupBox("Wi-Fi 配网（2.4 GHz · 加密信封）")
        wifi_form = QFormLayout(self.wifi_box)
        self.wifi_ssid_edit = QLineEdit()
        self.wifi_ssid_edit.setPlaceholderText("路由器 SSID")
        self.wifi_pass_edit = QLineEdit()
        self.wifi_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        wifi_form.addRow("SSID", self.wifi_ssid_edit)
        wifi_form.addRow("Wi-Fi 密码（不是 PIN）", self.wifi_pass_edit)
        grid = QGridLayout()
        self.send_wifi_btn = QPushButton("发送 Wi-Fi")
        self.send_wifi_btn.clicked.connect(self._on_send_wifi)
        self.wifi_scan_btn = QPushButton("扫描热点")
        self.wifi_scan_btn.clicked.connect(self._on_wifi_scan)
        self.wifi_list_btn = QPushButton("获取列表")
        self.wifi_list_btn.clicked.connect(self._on_get_wifi_list)
        self.read_btn = QPushButton("读 IP / 电参")
        self.read_btn.clicked.connect(self._on_read_data)
        grid.addWidget(self.send_wifi_btn, 0, 0)
        grid.addWidget(self.wifi_scan_btn, 0, 1)
        grid.addWidget(self.wifi_list_btn, 1, 0)
        grid.addWidget(self.read_btn, 1, 1)
        wifi_form.addRow(grid)
        wifi_form.addRow(self._hint(
            "须先「安全握手」。业务写 0xC313 为加密信封；应答 Notify 0xC315 解密后显示。\n"
            "读 IP / 电参：GATT Read 0xC314（可能为密文，工具自动解密）。"
        ))
        left.addWidget(self.wifi_box)

        self.quick_box = QGroupBox("常用一键命令（加密后写 0xC313）")
        quick_layout = QVBoxLayout(self.quick_box)
        self._quick_grid = QGridLayout()
        self._quick_btns = []
        for i, (label, cmd) in enumerate(one_click_buttons(self._lang)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, c=cmd: self._on_quick(c))
            self._quick_grid.addWidget(btn, i // 3, i % 3)
            self._quick_btns.append((btn, cmd))
        quick_layout.addLayout(self._quick_grid)
        mb_row = QHBoxLayout()
        self.mb_lbl = QLabel("写 Modbus RTU（485）")
        mb_row.addWidget(self.mb_lbl)
        self.mb_addr = QSpinBox()
        self.mb_addr.setRange(1, 247)
        self.mb_addr.setValue(1)
        self.mb_baud = QLineEdit("9600")
        self.mb_baud.setMaximumWidth(80)
        self.mb_parity = QComboBox()
        self.mb_parity.addItem("0 = N, 8, 1", 0)
        self.mb_parity.addItem("1 = E, 8, 1", 1)
        self.mb_parity.addItem("2 = O, 8, 1", 2)
        self.mb_parity.addItem("3 = N, 8, 2", 3)
        self.mb_parity.setCurrentIndex(0)
        mb_go = QPushButton("下发 modbus")
        mb_go.clicked.connect(self._on_set_modbus)
        mb_row.addWidget(QLabel("地址"))
        mb_row.addWidget(self.mb_addr)
        mb_row.addWidget(QLabel("波特率"))
        mb_row.addWidget(self.mb_baud)
        mb_row.addWidget(QLabel("Parity/Stop"))
        mb_row.addWidget(self.mb_parity)
        mb_row.addWidget(mb_go)
        mb_row.addStretch()
        quick_layout.addLayout(mb_row)
        left.addWidget(self.quick_box)

        self.custom_box = QGroupBox("自定义业务 JSON（工具自动加密封装）")
        custom_layout = QVBoxLayout(self.custom_box)
        custom_layout.addWidget(self._hint(
            "输入明文业务对象，例如 {\"cmd\":\"model\",\"type\":1}。握手明文命令请用左侧「安全握手」。"
        ))
        self.custom_cmd_edit = QPlainTextEdit()
        self.custom_cmd_edit.setMaximumHeight(88)
        self.custom_cmd_edit.setPlaceholderText('{"cmd":"..."}')
        custom_layout.addWidget(self.custom_cmd_edit)
        self.custom_send_btn = QPushButton("发送（加密）")
        self.custom_send_btn.clicked.connect(self._on_custom_cmd)
        custom_layout.addWidget(self.custom_send_btn)
        left.addWidget(self.custom_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_host)
        splitter.addWidget(scroll)

        self.right_tabs = QTabWidget()
        status = QWidget()
        status_l = QVBoxLayout(status)
        self.dev_status = QLabel("设备：未连接")
        self.dev_status.setWordWrap(True)
        self.dev_status.setStyleSheet("background:#f4f7fb;padding:8px;border:1px solid #dde;")
        status_l.addWidget(self.dev_status)
        self.refresh_status_btn = QPushButton("刷新名称 / BLE / Wi-Fi / 通讯")
        self.refresh_status_btn.clicked.connect(self._on_refresh_status)
        status_l.addWidget(self.refresh_status_btn)
        self.wifi_list_box = QGroupBox("Wi-Fi 扫描结果（双击填入 SSID）")
        wifi_list_layout = QVBoxLayout(self.wifi_list_box)
        self.wifi_table = QTableWidget(0, 2)
        self.wifi_table.setHorizontalHeaderLabels(["SSID", "RSSI (dBm)"])
        self.wifi_table.horizontalHeader().setStretchLastSection(True)
        self.wifi_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.wifi_table.itemDoubleClicked.connect(self._on_wifi_row_double_click)
        wifi_list_layout.addWidget(self.wifi_table)
        status_l.addWidget(self.wifi_list_box)
        self.right_tabs.addTab(status, "运行状态")

        meter_tab = QWidget()
        meter_l = QVBoxLayout(meter_tab)
        self.meter_hint = QLabel("GATT Read 0xC314（解密后）。")
        meter_l.addWidget(self.meter_hint)
        self.meter_table = QTableWidget(0, 3)
        self.meter_table.setHorizontalHeaderLabels(["键", "含义", "值"])
        self.meter_table.horizontalHeader().setStretchLastSection(True)
        self.meter_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        meter_l.addWidget(self.meter_table)
        self.meter_refresh_btn = QPushButton("刷新电参")
        self.meter_refresh_btn.clicked.connect(self._on_read_data)
        meter_l.addWidget(self.meter_refresh_btn)
        self.right_tabs.addTab(meter_tab, "电参")

        adv_tab = QWidget()
        adv_l = QVBoxLayout(adv_tab)
        self.adv_hint = QLabel(
            "业务广播（§9 长包）：握手后派生 broadcast_key，扫描解密 V/I/P/FE/RE。约 200ms 刷新。"
        )
        self.adv_hint.setWordWrap(True)
        adv_l.addWidget(self.adv_hint)
        adv_btn_row = QHBoxLayout()
        self.adv_start_btn = QPushButton("开始监听广播")
        self.adv_start_btn.clicked.connect(self._on_adv_start)
        self.adv_stop_btn = QPushButton("停止")
        self.adv_stop_btn.clicked.connect(self._on_adv_stop)
        self.adv_stop_btn.setEnabled(False)
        adv_btn_row.addWidget(self.adv_start_btn)
        adv_btn_row.addWidget(self.adv_stop_btn)
        adv_btn_row.addStretch()
        adv_l.addLayout(adv_btn_row)
        self.adv_table = QTableWidget(0, 2)
        self.adv_table.setHorizontalHeaderLabels(["项", "值"])
        self.adv_table.horizontalHeader().setStretchLastSection(True)
        self.adv_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        adv_l.addWidget(self.adv_table)
        self.adv_log = QPlainTextEdit()
        self.adv_log.setReadOnly(True)
        self.adv_log.setMaximumHeight(140)
        self.adv_log.setFont(QFont("Consolas", 9))
        self.adv_log.setPlaceholderText("解密后的广播摘要…")
        adv_l.addWidget(self.adv_log)
        self.right_tabs.addTab(adv_tab, "业务广播")

        comm_tab = QWidget()
        comm_l = QVBoxLayout(comm_tab)
        self.comm_hint = QLabel("Modbus RTU、MQTT、UDP 当前配置")
        comm_l.addWidget(self.comm_hint)
        self.comm_view = QPlainTextEdit()
        self.comm_view.setReadOnly(True)
        self.comm_view.setFont(QFont("Consolas", 10))
        self.comm_view.setPlainText("尚未查询。握手成功后可刷新。")
        comm_l.addWidget(self.comm_view)
        self.comm_refresh_btn = QPushButton("刷新通讯配置")
        self.comm_refresh_btn.clicked.connect(self._on_refresh_comm)
        comm_l.addWidget(self.comm_refresh_btn)
        self.right_tabs.addTab(comm_tab, "通讯配置")

        help_tab = QWidget()
        help_l = QVBoxLayout(help_tab)
        self.help_hint = QLabel("命令、握手、缩写、错误码（含加密说明）")
        help_l.addWidget(self.help_hint)
        self.help_filter = QLineEdit()
        self.help_filter.setPlaceholderText("过滤：wifi、jpake、replay、MI…")
        self.help_filter.textChanged.connect(self._filter_help)
        help_l.addWidget(self.help_filter)
        self.help_view = QPlainTextEdit()
        self.help_view.setReadOnly(True)
        self.help_view.setPlainText(help_text(self._lang))
        self.help_view.setFont(QFont("Consolas", 10))
        help_l.addWidget(self.help_view)
        self.right_tabs.addTab(help_tab, "命令/缩写速查")

        log_tab = QWidget()
        log_l = QVBoxLayout(log_tab)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 10))
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.log_edit.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        log_l.addWidget(self.log_edit)
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.clicked.connect(self.log_edit.clear)
        log_l.addWidget(self.clear_log_btn)
        self.right_tabs.addTab(log_tab, "日志")

        splitter.addWidget(self.right_tabs)
        splitter.setSizes([560, 620])
        self._refresh_dev_status()
        self._log("服务 UUID: " + SERVICE_UUID + "  （明文工具是 A002，勿混用）")

    def _on_device_row(self, row: int) -> None:
        if row < 0 or row >= len(self._devices):
            return
        name = self._devices[row].name or ""
        if not self.sn_edit.text().strip():
            try:
                self.sn_edit.setText(infer_sn(None, name))
            except ProtocolError:
                pass

    def _refresh_dev_status(self) -> None:
        name = self._last_name or "—"
        mac = self._last_address or "—"
        sn = self.sn_edit.text().strip() or "—"
        secured = "yes" if (self._transport and self._transport.session) else "no"
        if self._lang == "en":
            self.dev_status.setText(
                f"Name: {name}\nMAC: {mac}\nSN: {sn}\nBLE: {self._status_ble}\n"
                f"Secure session: {secured}\nWi-Fi: {self._status_wifi}\nComm: {self._status_comm}\n"
                f"GATT: A003 (secured)"
            )
        else:
            self.dev_status.setText(
                f"名称：{name}\nMAC：{mac}\nSN：{sn}\nBLE：{self._status_ble}\n"
                f"安全会话：{secured}\nWi-Fi：{self._status_wifi}\n通讯：{self._status_comm}\n"
                f"GATT：A003（加密）"
            )

    def _fill_meter(self, data: dict[str, Any]) -> None:
        rows = meter_rows(data, self._lang)
        self.meter_table.setRowCount(len(rows))
        for i, (key, meaning, shown) in enumerate(rows):
            self.meter_table.setItem(i, 0, QTableWidgetItem(key))
            self.meter_table.setItem(i, 1, QTableWidgetItem(meaning))
            self.meter_table.setItem(i, 2, QTableWidgetItem(shown))
        self.meter_table.resizeColumnToContents(0)
        self.meter_table.resizeColumnToContents(1)

    def _paint_comm(self) -> None:
        self.comm_view.setPlainText(
            format_comm_config(
                model=self._model_d,
                mqtt=self._mqtt_d,
                udp=self._udp_d,
                function_map=self._fmap_raw,
                lang=self._lang,
            )
        )

    def _filter_help(self, text: str) -> None:
        body = help_text(self._lang)
        q = text.strip().lower()
        if not q:
            self.help_view.setPlainText(body)
            return
        lines = [ln for ln in body.splitlines() if q in ln.lower()]
        empty = "(no match)" if self._lang == "en" else "(无匹配)"
        self.help_view.setPlainText("\n".join(lines) if lines else empty)

    def _on_lang_changed(self, _index: int = 0) -> None:
        data = self.lang_combo.currentData()
        self._lang = data if data in ("zh", "en") else "zh"
        self._apply_language()

    def _t(self, zh: str, en: str) -> str:
        return en if self._lang == "en" else zh

    def _apply_language(self) -> None:
        self.setWindowTitle(self._t(
            "电表加密 BLE 体验工具（Lite/Pro · A003）",
            "Energy Meter Secured BLE Console (Lite/Pro · A003)",
        ))
        self.conn_box.setTitle(self._t(
            "设备连接（加密服务 0xA003 · 勿用 A002）",
            "Device connection (secured 0xA003 · not A002)",
        ))
        self.auto_reconnect_chk.setText(self._t(
            "设备重启后自动重连 GATT（推荐）",
            "Auto-reconnect GATT after device restart (recommended)",
        ))
        self.debug_keys_chk.setText(self._t(
            "调试模式：日志可含密钥材料（默认关）",
            "Debug: allow key material in logs (off by default)",
        ))
        self.scan_btn.setText(self._t("扫描", "Scan"))
        self.connect_btn.setText(self._t("连接", "Connect"))
        self.disconnect_btn.setText(self._t("断开", "Disconnect"))
        self.hs_btn.setText(self._t("安全握手", "Secure handshake"))
        if not (self._client and self._client.is_connected):
            self.conn_label.setText(self._t("未连接", "Disconnected"))
        self.wifi_box.setTitle(self._t(
            "Wi-Fi 配网（2.4 GHz · 加密信封）",
            "Wi-Fi provisioning (2.4 GHz · encrypted envelope)",
        ))
        self.send_wifi_btn.setText(self._t("发送 Wi-Fi", "Send Wi-Fi"))
        self.wifi_scan_btn.setText(self._t("扫描热点", "Scan APs"))
        self.wifi_list_btn.setText(self._t("获取列表", "Get list"))
        self.read_btn.setText(self._t("读 IP / 电参", "Read IP / meter"))
        self.quick_box.setTitle(self._t(
            "常用一键命令（加密后写 0xC313）",
            "Quick commands (encrypted write 0xC313)",
        ))
        for btn, cmd in self._quick_btns:
            for label, c in one_click_buttons(self._lang):
                if c == cmd:
                    btn.setText(label)
                    break
        self.custom_box.setTitle(self._t(
            "自定义业务 JSON（工具自动加密封装）",
            "Custom business JSON (auto-encrypted)",
        ))
        self.custom_send_btn.setText(self._t("发送（加密）", "Send (encrypted)"))
        self.right_tabs.setTabText(0, self._t("运行状态", "Status"))
        self.right_tabs.setTabText(1, self._t("电参", "Meter"))
        self.right_tabs.setTabText(2, self._t("业务广播", "Broadcast"))
        self.right_tabs.setTabText(3, self._t("通讯配置", "Comm"))
        self.right_tabs.setTabText(4, self._t("命令/缩写速查", "Commands"))
        self.right_tabs.setTabText(5, self._t("日志", "Log"))
        self.refresh_status_btn.setText(self._t("刷新名称 / BLE / Wi-Fi / 通讯", "Refresh name / BLE / Wi-Fi / comm"))
        self.wifi_list_box.setTitle(self._t("Wi-Fi 扫描结果（双击填入 SSID）", "Wi-Fi scan results (double-click SSID)"))
        self.meter_hint.setText(self._t("GATT Read 0xC314（解密后）。", "GATT Read 0xC314 (after decrypt)."))
        self.adv_hint.setText(self._t(
            "业务广播（§9 长包）：握手后派生 broadcast_key，扫描解密 V/I/P/FE/RE。约 200ms 刷新。",
            "Business broadcast (§9 long): after handshake, scan & decrypt V/I/P/FE/RE with broadcast_key (~200ms).",
        ))
        self.adv_start_btn.setText(self._t("开始监听广播", "Start adv watch"))
        self.adv_stop_btn.setText(self._t("停止", "Stop"))
        self.adv_table.setHorizontalHeaderLabels([self._t("项", "Field"), self._t("值", "Value")])
        self.meter_table.setHorizontalHeaderLabels([
            self._t("键", "Key"), self._t("含义", "Meaning"), self._t("值", "Value"),
        ])
        self.meter_refresh_btn.setText(self._t("刷新电参", "Refresh meter"))
        self.comm_hint.setText(self._t("Modbus RTU、MQTT、UDP 当前配置", "Modbus RTU, MQTT, UDP settings"))
        self.comm_refresh_btn.setText(self._t("刷新通讯配置", "Refresh communication"))
        self.help_hint.setText(self._t(
            "命令、握手、缩写、错误码（含加密说明）",
            "Commands, handshake, abbreviations, errors (secured)",
        ))
        self.clear_log_btn.setText(self._t("清空日志", "Clear log"))
        if self._status_ble in ("未连接", "Disconnected"):
            self._status_ble = self._t("未连接", "Disconnected")
        if self._status_wifi in ("尚未查询", "Not queried"):
            self._status_wifi = self._t("尚未查询", "Not queried")
        if self._status_comm in ("尚未查询", "Not queried"):
            self._status_comm = self._t("尚未查询", "Not queried")
        self._filter_help(self.help_filter.text())
        self._paint_comm()
        self._refresh_dev_status()

    def _log(self, text: str) -> None:
        self._log_queue.put(text)

    def _drain_log_queue(self) -> None:
        reconnect = False
        while True:
            try:
                line = self._log_queue.get_nowait()
            except queue.Empty:
                break
            if line == GATT_DROP:
                reconnect = True
                self.log_edit.appendPlainText("[GATT] disconnected")
                continue
            self.log_edit.appendPlainText(line)
        if reconnect:
            self._handle_gatt_drop()

    def _on_ble_disconnected(self, _client: Any) -> None:
        self._log_queue.put(GATT_DROP)

    def _handle_gatt_drop(self) -> None:
        self._transport = None
        self._client = None
        self._set_connected_ui(False)
        if self._want_link and self.auto_reconnect_chk.isChecked() and not self._reconnect_busy:
            self._log(self._t("将自动重连…", "Auto-reconnecting…"))
            self._submit(self._auto_reconnect())

    def _set_connected_ui(self, connected: bool) -> None:
        if connected:
            self.conn_label.setText(self._t("已连接", "Connected"))
            self.conn_label.setStyleSheet("color:#2a7;font-weight:bold;")
            self._status_ble = self._t("已连接", "Connected")
        else:
            self.conn_label.setText(self._t("未连接", "Disconnected"))
            self.conn_label.setStyleSheet("color:#888;")
            self._status_ble = self._t("未连接", "Disconnected")
            self._status_wifi = self._t("尚未查询", "Not queried")
            self._status_comm = self._t("尚未查询", "Not queried")
        self._refresh_dev_status()

    def _require_transport(self, need_session: bool = False) -> bool:
        if not (self._transport and self._client and self._client.is_connected):
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请先连接 BLE 设备", "Connect a BLE device first"))
            return False
        if need_session and self._transport.session is None:
            QMessageBox.warning(
                self,
                self._t("提示", "Notice"),
                self._t("请先完成安全握手", "Complete secure handshake first"),
            )
            return False
        return True

    def _on_scan(self) -> None:
        self._submit(self._scan_devices(disconnect_first=True))

    async def _scan_devices(self, disconnect_first: bool = True) -> list[Any]:
        if disconnect_first and self._client and self._client.is_connected:
            await self._disconnect(keep_want=False)
        self.device_list.clear()
        self._devices.clear()
        timeout = float(self.scan_timeout_spin.value())
        self._log(f"scan {timeout:.0f}s …")
        found: list[Any] = []
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            for device in devices:
                name = device.name or ""
                if any(tag in name for tag in DEVICE_NAME_FILTERS):
                    self.device_list.addItem(f"{name} - {device.address}")
                    self._devices.append(device)
                    found.append(device)
            self._log(f"found {len(self._devices)}")
        except Exception as exc:
            self._log(f"scan failed: {exc}")
        return found

    def _on_connect(self) -> None:
        row = self.device_list.currentRow()
        if row < 0 or row >= len(self._devices):
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请先选择一台设备", "Select a device first"))
            return
        device = self._devices[row]
        self._want_link = True
        self._submit(self._connect_device(device.address, device.name or device.address, auto_hs=True))

    async def _connect_device(self, address: str, name: str, auto_hs: bool = True) -> bool:
        self._log(f"connecting {name} ({address})…")
        try:
            if self._client:
                await self._silent_close()
            try:
                sn = infer_sn(self.sn_edit.text().strip() or None, name)
                self.sn_edit.setText(sn)
            except ProtocolError as exc:
                self._log(str(exc))
                QMessageBox.warning(self, "SN", str(exc))
                return False
            client = BleakClient(address, disconnected_callback=self._on_ble_disconnected)
            await client.connect()
            self._client = client
            self._transport = BleSecureClient(
                client,
                sn,
                self._cache,
                log=self._log,
                debug_keys=self.debug_keys_chk.isChecked(),
            )
            await self._transport.start()
            self._last_address = address
            self._last_name = name
            self._want_link = True
            self._set_connected_ui(True)
            self._log("connected; notify C315 started")
            if auto_hs:
                ok = await self._do_handshake()
                if ok:
                    await self._refresh_link_snapshot()
            return True
        except Exception as exc:
            self._log(f"connect failed: {exc}")
            await self._silent_close()
            self._set_connected_ui(False)
            return False

    async def _silent_close(self) -> None:
        if self._transport:
            try:
                await self._transport.stop()
            except Exception:
                pass
            self._transport = None
        if self._client:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _on_user_disconnect(self) -> None:
        self._want_link = False
        self._submit(self._disconnect(keep_want=False))

    async def _disconnect(self, keep_want: bool) -> None:
        if not keep_want:
            self._want_link = False
        await self._stop_adv_scanner()
        await self._silent_close()
        self._set_connected_ui(False)
        self._log("disconnected")

    def _on_adv_start(self) -> None:
        if not self._broadcast_key:
            QMessageBox.warning(
                self,
                self._t("提示", "Notice"),
                self._t(
                    "需要完整 J-PAKE 后的 broadcast_key（仅 session-nonce 恢复且无缓存时可能没有）。",
                    "Need broadcast_key from full J-PAKE (session-nonce resume may lack it without cache).",
                ),
            )
            return
        self._submit(self._start_adv_scanner())

    def _on_adv_stop(self) -> None:
        self._submit(self._stop_adv_scanner())

    async def _start_adv_scanner(self) -> None:
        await self._stop_adv_scanner()
        sn = (self.sn_edit.text() or "").strip().upper()
        name_hint = (self._last_name or "").strip()

        def _cb(device: Any, adv: Any) -> None:
            try:
                if not self._broadcast_key:
                    return
                name = (getattr(adv, "local_name", None) or device.name or "") or ""
                if name:
                    name_u = name.upper()
                    ok_name = False
                    if name_hint and name_hint.upper() in name_u:
                        ok_name = True
                    if sn and sn.upper() in name_u:
                        ok_name = True
                    if not ok_name and (name_hint or sn):
                        return
                md = getattr(adv, "manufacturer_data", None) or {}
                extracted = extract_manufacturer_blob(md)
                if not extracted or extracted[0] != "long26":
                    return
                blob = extracted[1]
                plain = decrypt_long_manufacturer(blob, self._broadcast_key, log=lambda *_: None)
                fields = parse_long_adv_fields(blob[2], plain)
                fields["counter"] = int.from_bytes(blob[3:7], "little")
                fields["rssi"] = getattr(adv, "rssi", None)
                fields["name"] = name
                self._adv_queue.put(fields)
            except Exception:
                return

        self._adv_scanner = BleakScanner(detection_callback=_cb)
        await self._adv_scanner.start()
        self._adv_watching = True
        self.adv_start_btn.setEnabled(False)
        self.adv_stop_btn.setEnabled(True)
        self._log(self._t("已开始监听业务广播", "Broadcast watch started"))

    async def _stop_adv_scanner(self) -> None:
        if self._adv_scanner is not None:
            try:
                await self._adv_scanner.stop()
            except Exception:
                pass
            self._adv_scanner = None
        self._adv_watching = False
        self.adv_start_btn.setEnabled(bool(self._broadcast_key))
        self.adv_stop_btn.setEnabled(False)

    def _drain_adv_queue(self) -> None:
        latest: Optional[dict[str, Any]] = None
        while True:
            try:
                latest = self._adv_queue.get_nowait()
            except queue.Empty:
                break
        if not latest:
            return
        rows = [
            ("phase", latest.get("phase")),
            ("product", latest.get("product")),
            ("V", latest.get("V")),
            ("I", latest.get("I")),
            ("P", latest.get("P")),
            ("FE", latest.get("FE")),
            ("RE", latest.get("RE")),
            ("counter", latest.get("counter")),
            ("RSSI", latest.get("rssi")),
        ]
        self.adv_table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.adv_table.setItem(i, 0, QTableWidgetItem(str(k)))
            self.adv_table.setItem(i, 1, QTableWidgetItem("" if v is None else str(v)))
        self.adv_log.appendPlainText(
            f"{latest.get('phase')} V={latest.get('V')} I={latest.get('I')} P={latest.get('P')} "
            f"ctr={latest.get('counter')} rssi={latest.get('rssi')}"
        )

    async def _auto_reconnect(self) -> None:
        if self._reconnect_busy:
            return
        self._reconnect_busy = True
        try:
            for attempt in range(1, 13):
                if not self._want_link or not self.auto_reconnect_chk.isChecked():
                    return
                wait = 4.0 if attempt == 1 else 2.5
                self._log(f"reconnect {attempt}/12, wait {wait:.0f}s…")
                await asyncio.sleep(wait)
                if self._last_address:
                    if await self._connect_device(self._last_address, self._last_name or self._last_address):
                        self._log("reconnect ok")
                        return
                devices = await BleakScanner.discover(timeout=6.0)
                last = (self._last_name or "").strip()
                target = None
                for device in devices:
                    name = device.name or ""
                    if last and name == last:
                        target = device
                        break
                    if last and last in name:
                        target = device
                    elif any(tag in name for tag in DEVICE_NAME_FILTERS) and not target:
                        target = device
                if target is None:
                    continue
                if await self._connect_device(target.address, target.name or target.address):
                    self._log("reconnect ok")
                    return
            self._log(self._t("自动重连失败，请手动扫描", "Auto-reconnect failed; scan manually"))
        finally:
            self._reconnect_busy = False

    def _on_handshake(self) -> None:
        if not self._require_transport(need_session=False):
            return
        self._submit(self._do_handshake())

    async def _do_handshake(self) -> bool:
        assert self._transport
        try:
            pin = pin_from_manual_pairing_code(self.pin_edit.text().strip())
            self._log(f"PIN={pin}")
            ver, step = await self._transport.get_protocol_version()
            self._log(f"ble-crypto-ver ver={ver} step={step}")
            if step == 1:
                self._log("step=1 mid-handshake → ble-crypto-reset")
                await self._transport.reset_handshake()
                ver, step = await self._transport.get_protocol_version()
            state = await self._transport.open_secure_channel(pin if pin else None)
            self._broadcast_key = state.broadcast_key
            if self.debug_keys_chk.isChecked():
                bk = state.broadcast_key.hex() if state.broadcast_key else "(none)"
                self._log(
                    f"[debug] LTK={state.ltk.hex()} session={state.session_key.hex()} broadcast={bk}"
                )
            else:
                self._log(f"secure channel OK (ver={state.protocol_version}, keys hidden)")
            self._status_ble = self._t("已连接，已建链", "Connected, secured")
            self._refresh_dev_status()
            self.adv_start_btn.setEnabled(bool(self._broadcast_key))
            return True
        except ProtocolError as exc:
            self._log(f"handshake failed: {exc}")
            self._status_ble = self._t("已连接，未建链", "Connected, not secured")
            self._refresh_dev_status()
            if "PIN" in str(exc) or "pin" in str(exc).lower() or "J-PAKE" in str(exc):
                QMessageBox.warning(self, "PIN", str(exc))
            return False
        except Exception as exc:
            self._log(f"handshake error: {exc}")
            return False

    def _on_refresh_status(self) -> None:
        if not self._require_transport(need_session=True):
            return
        self._submit(self._refresh_link_snapshot())

    def _on_refresh_comm(self) -> None:
        if not self._require_transport(need_session=True):
            return
        self._submit(self._refresh_comm())

    async def _refresh_comm(self) -> None:
        assert self._transport
        try:
            fmap = await self._transport.send_secure_command({"cmd": "getFunctionMap"}, "getFunctionMap")
            data = fmap.get("d") if isinstance(fmap.get("d"), dict) else {}
            self._fmap_raw = data.get("functionMap", fmap.get("functionMap"))
            try:
                self._status_comm = decode_function_map(int(self._fmap_raw), self._lang)
            except (TypeError, ValueError):
                pass
        except Exception as exc:
            self._log(f"getFunctionMap: {exc}")
        try:
            model = await self._transport.send_secure_command({"cmd": "model", "type": 1}, "model")
            md = model.get("d") if isinstance(model.get("d"), dict) else {}
            if md:
                self._model_d = md
        except Exception as exc:
            self._log(f"model: {exc}")
        try:
            mqtt = await self._transport.send_secure_command({"cmd": "mqttdata"}, "mqttdata")
            self._mqtt_d = mqtt.get("d") if isinstance(mqtt.get("d"), dict) else {}
        except Exception as exc:
            self._log(f"mqttdata: {exc}")
        try:
            udp = await self._transport.send_secure_command({"cmd": "udpdata"}, "udpdata")
            self._udp_d = udp.get("d") if isinstance(udp.get("d"), dict) else udp
        except Exception as exc:
            self._log(f"udpdata: {exc}")
        self._paint_comm()
        self._refresh_dev_status()

    def _on_send_wifi(self) -> None:
        if not self._require_transport(need_session=True):
            return
        ssid = self.wifi_ssid_edit.text().strip()
        if not ssid:
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请输入 Wi-Fi SSID", "Enter Wi-Fi SSID"))
            return
        self._submit(self._send_wifi(ssid, self.wifi_pass_edit.text()))

    async def _send_wifi(self, ssid: str, wifi_pass: str) -> None:
        assert self._transport
        resp = await self._transport.send_secure_command(
            {"cmd": "wifi", "ssid": ssid, "pass": wifi_pass},
            "wifi",
            timeout=30.0,
        )
        self._log(json.dumps(resp, ensure_ascii=False))
        if resp.get("ok"):
            self._log(self._t("已接受 Wi-Fi，请读 IP 确认 IPv4（成功后 LTK 才落盘）",
                              "Wi-Fi accepted; read IP for IPv4 (LTK persists after STA OK)"))
        else:
            self._log(f"wifi failed: {resp.get('msg', resp)}")

    def _on_wifi_scan(self) -> None:
        if not self._require_transport(need_session=True):
            return
        self._submit(self._wifi_scan())

    async def _wifi_scan(self) -> None:
        assert self._transport
        resp = await self._transport.send_secure_command({"cmd": "wifiscan"}, "wifiscan")
        self._log(f"wifiscan: {resp.get('msg', resp)}")

    def _on_get_wifi_list(self) -> None:
        if not self._require_transport(need_session=True):
            return
        self._submit(self._get_wifi_list())

    async def _get_wifi_list(self) -> None:
        assert self._transport
        resp = await self._transport.send_secure_command({"cmd": "getwifilist"}, "getwifilist")
        if not resp.get("ok"):
            self._log(f"getwifilist failed: {resp.get('msg', resp)}")
            return
        items = parse_wifi_list(resp)
        self._update_wifi_table(items)
        self._log(f"APs: {len(items)}")

    def _update_wifi_table(self, items: list[tuple[str, int]]) -> None:
        self.wifi_table.setRowCount(len(items))
        for row, (ssid, rssi) in enumerate(items):
            self.wifi_table.setItem(row, 0, QTableWidgetItem(ssid))
            rssi_item = QTableWidgetItem(str(rssi))
            rssi_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.wifi_table.setItem(row, 1, rssi_item)

    def _on_wifi_row_double_click(self, item: QTableWidgetItem) -> None:
        ssid_item = self.wifi_table.item(item.row(), 0)
        if ssid_item:
            self.wifi_ssid_edit.setText(ssid_item.text())

    def _on_quick(self, cmd: str) -> None:
        if not self._require_transport(need_session=True):
            return
        title = next((lab for lab, c in one_click_buttons(self._lang) if c == cmd), cmd)
        if cmd == "reset":
            if QMessageBox.question(
                self, self._t("确认", "Confirm"),
                self._t("恢复出厂设置将清空配置并清除 LTK，确定？", "Factory reset clears config and LTK. Continue?"),
            ) != QMessageBox.StandardButton.Yes:
                return
        if cmd == "startota":
            if QMessageBox.question(
                self, self._t("确认", "Confirm"),
                self._t("启动 OTA，确定？", "Start OTA?"),
            ) != QMessageBox.StandardButton.Yes:
                return
        self._submit(self._quick(cmd, title))

    async def _quick(self, cmd: str, title: str) -> None:
        assert self._transport
        payload: dict[str, Any] = {"cmd": cmd}
        if cmd in ("enablehttp", "enablemodbustcp"):
            payload["enable"] = True
        if cmd == "model":
            payload["type"] = 1
        timeout = 25.0 if cmd in ("checkota", "startota", "otaprogress", "restart", "reset") else 15.0
        resp = await self._transport.send_secure_command(payload, cmd, timeout=timeout)
        self._log(f"{title}: {json.dumps(resp, ensure_ascii=False)}")
        data = resp.get("d") if isinstance(resp.get("d"), dict) else {}
        if cmd == "getFunctionMap":
            raw = data.get("functionMap", resp.get("functionMap"))
            try:
                self._status_comm = decode_function_map(int(raw), self._lang)
                self._fmap_raw = raw
            except (TypeError, ValueError):
                pass
            self._paint_comm()
            self._refresh_dev_status()
        if cmd == "model" and data:
            self._model_d = data
            self._log(format_model_snapshot(data, self._lang))
            self._paint_comm()
        if cmd == "mqttdata":
            self._mqtt_d = data
            self._paint_comm()
        if cmd == "udpdata":
            self._udp_d = data if data else resp.get("d")
            self._paint_comm()
        if cmd in ("restart", "reset") and resp.get("ok"):
            self._log(self._t("设备将重启；若勾选自动重连将恢复会话", "Device will reboot; auto-reconnect will resume session"))

    def _on_set_modbus(self) -> None:
        if not self._require_transport(need_session=True):
            return
        try:
            baud = int(self.mb_baud.text().strip())
        except ValueError:
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("波特率必须是数字", "Baud must be a number"))
            return
        parity_stop = int(self.mb_parity.currentData())
        payload = {"cmd": "modbus", "baud": baud, "parityStop": parity_stop, "address": int(self.mb_addr.value())}
        self._submit(self._custom_cmd(payload))

    def _on_read_data(self) -> None:
        if not self._require_transport(need_session=True):
            return
        self._submit(self._read_data())

    async def _read_data(self) -> None:
        assert self._transport
        try:
            await self._transport.send_secure_command({"cmd": "read"}, "read")
            doc = await self._transport.read_secure_snapshot()
            self._log(f"[READ C314] {json.dumps(doc, ensure_ascii=False)}")
            self._fill_meter(doc)
            ip = str(doc.get("IP", ""))
            rssi = doc.get("RSSI", "")
            sep = "; " if self._lang == "en" else "；"
            self._status_wifi = f"{wifi_ip_status(ip, self._lang)}{sep}RSSI={rssi} dBm"
            self._refresh_dev_status()
        except Exception as exc:
            self._log(f"read failed: {exc}")

    def _on_custom_cmd(self) -> None:
        if not self._require_transport(need_session=True):
            return
        raw = self.custom_cmd_edit.toPlainText().strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "JSON", str(exc))
            return
        if not isinstance(payload, dict):
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("必须是 JSON 对象", "Must be a JSON object"))
            return
        self._submit(self._custom_cmd(payload))

    async def _custom_cmd(self, payload: dict[str, Any]) -> None:
        assert self._transport
        event = str(payload.get("cmd") or "")
        resp = await self._transport.send_secure_command(payload, event or None)
        self._log(f"[应答] {json.dumps(resp, ensure_ascii=False)}")
        if payload.get("cmd") == "getwifilist" and resp.get("ok"):
            self._update_wifi_table(parse_wifi_list(resp))
        if payload.get("cmd") == "model":
            md = resp.get("d") if isinstance(resp.get("d"), dict) else {}
            if md:
                self._model_d = md
                self._paint_comm()

    async def _refresh_link_snapshot(self) -> None:
        if not self._transport or self._transport.session is None:
            return
        await self._refresh_comm()
        await self._read_data()

    def closeEvent(self, event: Any) -> None:
        self._want_link = False
        try:
            self._submit(self._stop_adv_scanner()).result(timeout=3)
        except Exception:
            pass
        fut = self._submit(self._silent_close())
        try:
            fut.result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    win = BleSecuredWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
