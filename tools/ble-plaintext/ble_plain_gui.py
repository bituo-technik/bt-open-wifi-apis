#!/usr/bin/env python3
"""电表明文 BLE 体验工具（客户版）

明文通道: A002 / 写 C303 / 读 C304 / 通知 C305。
出厂 BLE 密码 1234。Wi-Fi 仅 2.4 GHz。不含未发布通断器。

  py -3 -m pip install -r requirements.txt
  py -3 ble_plain_gui.py
"""

from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from command_help import (
    decode_function_map,
    format_comm_config,
    format_meter_snapshot,
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

SERVICE_UUID = "0000a002-0000-1000-8000-00805f9b34fb"
READ_UUID = "0000c304-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000c303-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000c305-0000-1000-8000-00805f9b34fb"
DEVICE_NAME_FILTERS = ("SDM", "SPM")
GATT_DROP = "__GATT_DROP__"

class PlainBleClient:
    def __init__(self, client: BleakClient, log: Callable[[str], None]) -> None:
        self.client = client
        self._log = log
        self._unlocked = False
        self.notifications: asyncio.Queue[str] = asyncio.Queue()

    def _notification_callback(self, _: Any, data: bytearray) -> None:
        text = bytes(data).decode("utf-8", errors="replace")
        self._log(f"[RX] {text}")
        self.notifications.put_nowait(text)

    async def start(self) -> None:
        await self.client.start_notify(NOTIFY_UUID, self._notification_callback)

    async def stop(self) -> None:
        if not self.client.is_connected:
            return
        try:
            await self.client.stop_notify(NOTIFY_UUID)
        except Exception:
            pass

    def _drain_notifications(self) -> None:
        while not self.notifications.empty():
            self.notifications.get_nowait()

    async def wait_for_event(
        self,
        event_name: Optional[str] = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError("waiting for device response timeout")
            raw = await asyncio.wait_for(self.notifications.get(), remaining)
            try:
                doc = json.loads(raw.strip())
            except json.JSONDecodeError:
                return {"ok": True, "msg": raw, "event": event_name or "raw", "raw": raw}
            if event_name is None or doc.get("event") in (event_name, "pas"):
                return doc

    async def write_raw(self, text: str) -> None:
        self._log(f"[TX] {text}")
        await self.client.write_gatt_char(WRITE_UUID, text.encode("utf-8"), response=True)

    async def send_command(
        self,
        payload: dict[str, Any],
        expected_event: Optional[str] = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        self._drain_notifications()
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        await self.write_raw(text)
        event = expected_event or str(payload.get("cmd") or "cmd")
        try:
            return await self.wait_for_event(event, timeout=timeout)
        except asyncio.TimeoutError:
            self._log("等待设备响应超时")
            return {"ok": False, "msg": "timeout", "event": event}

    async def unlock(self, password: str) -> dict[str, Any]:
        response = await self.send_command(
            {"cmd": "pass", "pas": password, "continue": True},
            expected_event="pass",
        )
        if response.get("ok", False):
            self._unlocked = True
        return response

    async def read_characteristic(self) -> str:
        data = await self.client.read_gatt_char(READ_UUID)
        return data.decode("utf-8", errors="replace")


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


class BleWifiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("电表明文 BLE 体验工具")
        self.resize(1180, 820)
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        self._client: Optional[BleakClient] = None
        self._transport: Optional[PlainBleClient] = None
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
        self._build_ui()
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(120)

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

        self.conn_box = QGroupBox("设备连接（明文服务 0xA002）")
        conn_box = self.conn_box
        conn_layout = QVBoxLayout(conn_box)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("BLE 密码"))
        self.ble_pass_edit = QLineEdit("1234")
        self.ble_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        row1.addWidget(self.ble_pass_edit)
        row1.addWidget(QLabel("扫描(秒)"))
        self.scan_timeout_spin = QSpinBox()
        self.scan_timeout_spin.setRange(3, 60)
        self.scan_timeout_spin.setValue(8)
        row1.addWidget(self.scan_timeout_spin)
        conn_layout.addLayout(row1)
        self.auto_reconnect_chk = QCheckBox("设备重启后自动重连 GATT（推荐：配 MQTT / Modbus TCP 后不必手点连接）")
        self._lbl_ble_pass = None  # set below
        self.auto_reconnect_chk.setChecked(True)
        conn_layout.addWidget(self.auto_reconnect_chk)
        row2 = QHBoxLayout()
        self.scan_btn = QPushButton("扫描")
        self.scan_btn.clicked.connect(self._on_scan)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._on_connect)
        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.clicked.connect(self._on_user_disconnect)
        self.unlock_btn = QPushButton("解锁")
        self.unlock_btn.clicked.connect(self._on_unlock)
        for b in (self.scan_btn, self.connect_btn, self.disconnect_btn, self.unlock_btn):
            row2.addWidget(b)
        self.conn_label = QLabel("未连接")
        self.conn_label.setStyleSheet("color:#888;")
        row2.addWidget(self.conn_label)
        row2.addStretch()
        conn_layout.addLayout(row2)
        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(90)
        conn_layout.addWidget(self.device_list)
        left.addWidget(conn_box)

        self.wifi_box = QGroupBox("Wi-Fi 配网（2.4 GHz）")
        wifi_box = self.wifi_box
        wifi_form = QFormLayout(wifi_box)
        self.wifi_ssid_edit = QLineEdit()
        self.wifi_ssid_edit.setPlaceholderText("路由器 SSID")
        self.wifi_pass_edit = QLineEdit()
        self.wifi_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        wifi_form.addRow("SSID", self.wifi_ssid_edit)
        wifi_form.addRow("Wi-Fi 密码（不是 BLE 密码）", self.wifi_pass_edit)
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
            "发送 Wi-Fi / 扫描热点 / 获取列表：都是写特征 0xC303（JSON 命令），结果从通知 0xC305 回来。\n"
            "读 IP / 电参：先写 0xC303 发 cmd=read，再 GATT 读特征 0xC304。配网成功时 IP 应为 IPv4。"
        ))
        left.addWidget(wifi_box)

        self.quick_box = QGroupBox("常用一键命令（均写 0xC303，应答走通知 0xC305）")
        quick_box = self.quick_box
        quick_layout = QVBoxLayout(quick_box)
        self._quick_grid = QGridLayout()
        qgrid = self._quick_grid
        self._quick_btns = []
        for i, (label, cmd) in enumerate(one_click_buttons(self._lang)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, c=cmd: self._on_quick(c))
            qgrid.addWidget(btn, i // 3, i % 3)
            self._quick_btns.append((btn, cmd))
        quick_layout.addLayout(qgrid)
        mb_row = QHBoxLayout()
        mb_row.addWidget(QLabel("写 Modbus 485"))
        self.mb_addr = QSpinBox()
        self.mb_addr.setRange(1, 247)
        self.mb_addr.setValue(1)
        self.mb_baud = QLineEdit("9600")
        self.mb_baud.setMaximumWidth(80)
        mb_go = QPushButton("下发 modbus")
        mb_go.clicked.connect(self._on_set_modbus)
        mb_row.addWidget(QLabel("地址"))
        mb_row.addWidget(self.mb_addr)
        mb_row.addWidget(QLabel("波特率"))
        mb_row.addWidget(self.mb_baud)
        mb_row.addWidget(mb_go)
        mb_row.addStretch()
        quick_layout.addLayout(mb_row)
        quick_layout.addWidget(self._hint("恢复出厂 / OTA 启动会改变设备；重启与出厂后将自动重连（若勾选）。"))
        left.addWidget(quick_box)

        self.custom_box = QGroupBox("自定义 JSON")
        custom_box = self.custom_box
        custom_layout = QVBoxLayout(custom_box)
        custom_layout.addWidget(self._hint("只发送你输入的对象。命令、缩写、错误码请切到右侧「命令/缩写速查」。"))
        self.custom_cmd_edit = QPlainTextEdit()
        self.custom_cmd_edit.setMaximumHeight(88)
        self.custom_cmd_edit.setPlaceholderText('{"cmd":"..."}')
        custom_layout.addWidget(self.custom_cmd_edit)
        self.custom_send_btn = QPushButton("发送自定义 JSON")
        self.custom_send_btn.clicked.connect(self._on_custom_cmd)
        custom_layout.addWidget(self.custom_send_btn)
        left.addWidget(custom_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_host)
        splitter.addWidget(scroll)

        self.right_tabs = QTabWidget()
        right = self.right_tabs
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
        wifi_list_box = self.wifi_list_box
        wifi_list_layout = QVBoxLayout(wifi_list_box)
        self.wifi_table = QTableWidget(0, 2)
        self.wifi_table.setHorizontalHeaderLabels(["SSID", "RSSI (dBm)"])
        self.wifi_table.horizontalHeader().setStretchLastSection(True)
        self.wifi_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.wifi_table.itemDoubleClicked.connect(self._on_wifi_row_double_click)
        wifi_list_layout.addWidget(self.wifi_table)
        status_l.addWidget(wifi_list_box)
        right.addTab(status, "运行状态")

        meter_tab = QWidget()
        meter_l = QVBoxLayout(meter_tab)
        self.meter_hint = QLabel("GATT Read 0xC304 电参。点左侧「读 IP / 电参」或下方刷新。")
        meter_l.addWidget(self.meter_hint)
        self.meter_table = QTableWidget(0, 3)
        self.meter_table.setHorizontalHeaderLabels(["键", "含义", "值"])
        self.meter_table.horizontalHeader().setStretchLastSection(True)
        self.meter_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        meter_l.addWidget(self.meter_table)
        self.meter_refresh_btn = QPushButton("刷新电参")
        self.meter_refresh_btn.clicked.connect(self._on_read_data)
        meter_l.addWidget(self.meter_refresh_btn)
        right.addTab(meter_tab, "电参")

        comm_tab = QWidget()
        comm_l = QVBoxLayout(comm_tab)
        self.comm_hint = QLabel("Modbus RTU、MQTT、UDP 当前配置（不必翻日志）")
        comm_l.addWidget(self.comm_hint)
        self.comm_view = QPlainTextEdit()
        self.comm_view.setReadOnly(True)
        self.comm_view.setFont(QFont("Consolas", 10))
        self.comm_view.setPlainText("尚未查询。连接后会自动拉取，也可点下方刷新。")
        comm_l.addWidget(self.comm_view)
        self.comm_refresh_btn = QPushButton("刷新通讯配置")
        self.comm_refresh_btn.clicked.connect(self._on_refresh_comm)
        comm_l.addWidget(self.comm_refresh_btn)
        right.addTab(comm_tab, "通讯配置")

        help_tab = QWidget()
        help_l = QVBoxLayout(help_tab)
        self.help_hint = QLabel("命令、返回、缩写、错误码（用下方过滤）")
        help_l.addWidget(self.help_hint)
        self.help_filter = QLineEdit()
        self.help_filter.setPlaceholderText("过滤：wifi、MI、1002、MAD…")
        self.help_filter.textChanged.connect(self._filter_help)
        help_l.addWidget(self.help_filter)
        self.help_view = QPlainTextEdit()
        self.help_view.setReadOnly(True)
        self.help_view.setPlainText(help_text(self._lang))
        self.help_view.setFont(QFont("Consolas", 10))
        help_l.addWidget(self.help_view)
        right.addTab(help_tab, "命令/缩写速查")

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
        right.addTab(log_tab, "日志")

        splitter.addWidget(right)
        splitter.setSizes([560, 620])
        self._refresh_dev_status()

    def _refresh_dev_status(self) -> None:
        name = self._last_name or "—"
        mac = self._last_address or "—"
        if self._lang == "en":
            self.dev_status.setText(
                f"Name: {name}\nMAC / address: {mac}\nBLE: {self._status_ble}\n"
                f"Wi-Fi: {self._status_wifi}\nComm: {self._status_comm}"
            )
        else:
            self.dev_status.setText(
                f"名称：{name}\nMAC/地址：{mac}\nBLE：{self._status_ble}\n"
                f"Wi-Fi：{self._status_wifi}\n通讯：{self._status_comm}"
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

    def _on_refresh_comm(self) -> None:
        if not self._require_transport():
            return
        self._submit(self._refresh_comm())

    async def _refresh_comm(self) -> None:
        assert self._transport
        try:
            fmap = await self._transport.send_command({"cmd": "getFunctionMap"}, expected_event="getFunctionMap")
            data = fmap.get("d") if isinstance(fmap.get("d"), dict) else {}
            self._fmap_raw = data.get("functionMap", fmap.get("functionMap"))
            try:
                self._status_comm = decode_function_map(int(self._fmap_raw), self._lang)
            except (TypeError, ValueError):
                pass
        except Exception as exc:
            self._log(f"getFunctionMap 失败: {exc}")
        try:
            model = await self._transport.send_command({"cmd": "model", "type": 1}, expected_event="model")
            md = model.get("d") if isinstance(model.get("d"), dict) else {}
            if md:
                self._model_d = md
        except Exception as exc:
            self._log(f"model 失败: {exc}")
        try:
            mqtt = await self._transport.send_command({"cmd": "mqttdata"}, expected_event="mqttdata")
            self._mqtt_d = mqtt.get("d") if isinstance(mqtt.get("d"), dict) else {}
        except Exception as exc:
            self._log(f"mqttdata 失败: {exc}")
        try:
            udp = await self._transport.send_command({"cmd": "udpdata"}, expected_event="udpdata")
            d = udp.get("d") if isinstance(udp.get("d"), dict) else udp
            self._udp_d = d
        except Exception as exc:
            self._log(f"udpdata 失败: {exc}")
        self._paint_comm()
        self._refresh_dev_status()


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
        self.setWindowTitle(self._t("电表明文 BLE 体验工具", "Energy Meter Plaintext BLE Console"))
        self.conn_box.setTitle(self._t("设备连接（明文服务 0xA002）", "Device connection (service 0xA002)"))
        self.auto_reconnect_chk.setText(self._t(
            "设备重启后自动重连 GATT（推荐：配 MQTT / Modbus TCP 后不必手点连接）",
            "Auto-reconnect GATT after device restart (recommended after MQTT / Modbus TCP)",
        ))
        self.scan_btn.setText(self._t("扫描", "Scan"))
        self.connect_btn.setText(self._t("连接", "Connect"))
        self.disconnect_btn.setText(self._t("断开", "Disconnect"))
        self.unlock_btn.setText(self._t("解锁", "Unlock"))
        if not (self._client and self._client.is_connected):
            self.conn_label.setText(self._t("未连接", "Disconnected"))
        self.wifi_box.setTitle(self._t("Wi-Fi 配网（2.4 GHz）", "Wi-Fi provisioning (2.4 GHz)"))
        self.wifi_ssid_edit.setPlaceholderText(self._t("路由器 SSID", "Router SSID"))
        self.send_wifi_btn.setText(self._t("发送 Wi-Fi", "Send Wi-Fi"))
        self.wifi_scan_btn.setText(self._t("扫描热点", "Scan APs"))
        self.wifi_list_btn.setText(self._t("获取列表", "Get list"))
        self.read_btn.setText(self._t("读 IP / 电参", "Read IP / meter"))
        self.quick_box.setTitle(self._t(
            "常用一键命令（均写 0xC303，应答走通知 0xC305）",
            "Quick commands (write 0xC303, reply on notify 0xC305)",
        ))
        for btn, cmd in self._quick_btns:
            for label, c in one_click_buttons(self._lang):
                if c == cmd:
                    btn.setText(label)
                    break
        self.custom_box.setTitle(self._t("自定义 JSON", "Custom JSON"))
        self.custom_send_btn.setText(self._t("发送自定义 JSON", "Send custom JSON"))
        self.right_tabs.setTabText(0, self._t("运行状态", "Status"))
        self.right_tabs.setTabText(1, self._t("电参", "Meter"))
        self.right_tabs.setTabText(2, self._t("通讯配置", "Comm"))
        self.right_tabs.setTabText(3, self._t("命令/缩写速查", "Commands"))
        self.right_tabs.setTabText(4, self._t("日志", "Log"))
        self.refresh_status_btn.setText(self._t("刷新名称 / BLE / Wi-Fi / 通讯", "Refresh name / BLE / Wi-Fi / comm"))
        self.wifi_list_box.setTitle(self._t("Wi-Fi 扫描结果（双击填入 SSID）", "Wi-Fi scan results (double-click to fill SSID)"))
        self.meter_hint.setText(self._t(
            "GATT Read 0xC304 电参。点左侧「读 IP / 电参」或下方刷新。",
            "GATT Read 0xC304. Use Read IP / meter on the left or refresh below.",
        ))
        self.meter_table.setHorizontalHeaderLabels([
            self._t("键", "Key"), self._t("含义", "Meaning"), self._t("值", "Value"),
        ])
        self.meter_refresh_btn.setText(self._t("刷新电参", "Refresh meter"))
        self.comm_hint.setText(self._t(
            "Modbus RTU、MQTT、UDP 当前配置（不必翻日志）",
            "Modbus RTU, MQTT, UDP settings (no need to dig in the log)",
        ))
        if not (self._client and self._client.is_connected):
            self.comm_view.setPlainText(self._t(
                "尚未查询。连接后会自动拉取，也可点下方刷新。",
                "Not queried yet. Auto-fetched after connect, or refresh below.",
            ))
        self.comm_refresh_btn.setText(self._t("刷新通讯配置", "Refresh communication"))
        self.help_hint.setText(self._t("命令、返回、缩写、错误码（用下方过滤）", "Commands, responses, abbreviations, errors (filter below)"))
        self.help_filter.setPlaceholderText(self._t("过滤：wifi、MI、1002、MAD…", "Filter: wifi, MI, 1002, MAD…"))
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
                self.log_edit.appendPlainText("[GATT] 连接已断开")
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
            self._log("将自动重连（设备重启后需数秒重新广播）...")
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

    def _require_transport(self) -> bool:
        if self._transport and self._client and self._client.is_connected:
            return True
        QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请先连接 BLE 设备", "Connect a BLE device first"))
        return False

    def _on_scan(self) -> None:
        self._submit(self._scan_devices(disconnect_first=True))

    async def _scan_devices(self, disconnect_first: bool = True) -> list[Any]:
        if disconnect_first and self._client and self._client.is_connected:
            await self._disconnect(keep_want=False)
        self.device_list.clear()
        self._devices.clear()
        timeout = float(self.scan_timeout_spin.value())
        self._log(f"开始扫描 ({timeout:.0f}s)...")
        found: list[Any] = []
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            for device in devices:
                name = device.name or ""
                if any(tag in name for tag in DEVICE_NAME_FILTERS):
                    self.device_list.addItem(f"{name} - {device.address}")
                    self._devices.append(device)
                    found.append(device)
            self._log(f"扫描完成，找到 {len(self._devices)} 台")
        except Exception as exc:
            self._log(f"扫描失败: {exc}")
        return found

    def _on_connect(self) -> None:
        row = self.device_list.currentRow()
        if row < 0 or row >= len(self._devices):
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请先选择一台设备", "Select a device first"))
            return
        device = self._devices[row]
        self._want_link = True
        self._submit(self._connect_device(device.address, device.name or device.address))

    async def _connect_device(self, address: str, name: str) -> bool:
        self._log(f"正在连接 {name} ({address})...")
        try:
            if self._client:
                await self._silent_close()
            client = BleakClient(address, disconnected_callback=self._on_ble_disconnected)
            await client.connect()
            self._client = client
            self._transport = PlainBleClient(client, self._log)
            await self._transport.start()
            self._last_address = address
            self._last_name = name
            self._want_link = True
            self._set_connected_ui(True)
            self._log("连接成功，已订阅通知 0xC305")
            pwd = self.ble_pass_edit.text().strip() or "1234"
            resp = await self._transport.unlock(pwd)
            if resp.get("ok"):
                self._log("已解锁 (pass + continue)")
                self._status_ble = self._t("已连接，已解锁", "Connected, unlocked")
                self._refresh_dev_status()
            else:
                self._log(f"自动解锁未成功: {resp.get('msg', resp)}")
                self._status_ble = self._t("已连接，未解锁", "Connected, locked")
                self._refresh_dev_status()
            await self._refresh_link_snapshot()
            return True
        except Exception as exc:
            self._log(f"连接失败: {exc}")
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
        await self._silent_close()
        self._set_connected_ui(False)
        self._log("已断开连接")

    async def _auto_reconnect(self) -> None:
        if self._reconnect_busy:
            return
        self._reconnect_busy = True
        try:
            for attempt in range(1, 13):
                if not self._want_link or not self.auto_reconnect_chk.isChecked():
                    return
                wait = 4.0 if attempt == 1 else 2.5
                self._log(f"自动重连 {attempt}/12，等待 {wait:.0f}s 后扫描...")
                await asyncio.sleep(wait)
                target = None
                if self._last_address:
                    if await self._connect_device(self._last_address, self._last_name or self._last_address):
                        self._log("自动重连成功")
                        return
                devices = await BleakScanner.discover(timeout=6.0)
                last = (self._last_name or "").strip()
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
                    self._log("自动重连成功")
                    return
            self._log("自动重连失败，请手动扫描连接")
        finally:
            self._reconnect_busy = False

    def _on_unlock(self) -> None:
        if not self._require_transport():
            return
        pwd = self.ble_pass_edit.text().strip()
        if not pwd:
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请输入 BLE 密码", "Enter the BLE password"))
            return
        self._submit(self._unlock(pwd))

    def _on_refresh_status(self) -> None:
        if not self._require_transport():
            return
        self._submit(self._refresh_link_snapshot())

    async def _unlock(self, password: str) -> None:
        assert self._transport
        try:
            resp = await self._transport.unlock(password)
            if resp.get("ok"):
                self._log("解锁成功")
                self._status_ble = self._t("已连接，已解锁", "Connected, unlocked")
                self._refresh_dev_status()
                await self._refresh_link_snapshot()
            else:
                self._log(f"解锁失败: {resp.get('msg', resp)}")
                self._status_ble = self._t("已连接，未解锁", "Connected, locked")
                self._refresh_dev_status()
        except Exception as exc:
            self._log(f"解锁异常: {exc}")

    def _on_send_wifi(self) -> None:
        if not self._require_transport():
            return
        ssid = self.wifi_ssid_edit.text().strip()
        if not ssid:
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("请输入 Wi-Fi SSID", "Enter the Wi-Fi SSID"))
            return
        self._submit(self._send_wifi(ssid, self.wifi_pass_edit.text()))

    async def _send_wifi(self, ssid: str, wifi_pass: str) -> None:
        assert self._transport
        resp = await self._transport.send_command(
            {"cmd": "wifi", "ssid": ssid, "pass": wifi_pass},
            expected_event="wifi",
            timeout=20.0,
        )
        if resp.get("ok"):
            self._log("电表已接受 Wi-Fi，请点「读 IP / 电参」（读 0xC304）确认 IPv4")
        else:
            self._log(f"Wi-Fi 配网失败: {resp.get('msg', resp)}")

    def _on_wifi_scan(self) -> None:
        if not self._require_transport():
            return
        self._submit(self._wifi_scan())

    async def _wifi_scan(self) -> None:
        assert self._transport
        resp = await self._transport.send_command({"cmd": "wifiscan"}, expected_event="wifiscan")
        self._log(f"wifiscan: {resp.get('msg', resp)}")

    def _on_get_wifi_list(self) -> None:
        if not self._require_transport():
            return
        self._submit(self._get_wifi_list())

    async def _get_wifi_list(self) -> None:
        assert self._transport
        resp = await self._transport.send_command({"cmd": "getwifilist"}, expected_event="getwifilist")
        if not resp.get("ok"):
            self._log(f"获取列表失败: {resp.get('msg', resp)} (code={resp.get('code', '')})")
            return
        items = parse_wifi_list(resp)
        self._update_wifi_table(items)
        self._log(f"获取到 {len(items)} 个热点")

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

    def _on_quick(self, cmd: str, title: str | None = None) -> None:
        if not self._require_transport():
            return
        if title is None:
            title = next((lab for lab, c in one_click_buttons(self._lang) if c == cmd), cmd)
        if cmd == "reset":
            if QMessageBox.question(
                self,
                self._t("确认", "Confirm"),
                self._t("恢复出厂将清空配置并重启，确定？", "Factory reset clears config and reboots. Continue?"),
            ) != QMessageBox.StandardButton.Yes:
                return
        if cmd == "startota":
            if QMessageBox.question(
                self,
                self._t("确认", "Confirm"),
                self._t("启动 OTA 将下载并升级固件，确定？", "Starting OTA will download and upgrade firmware. Continue?"),
            ) != QMessageBox.StandardButton.Yes:
                return
        self._submit(self._quick(cmd, title))

    async def _quick(self, cmd: str, title: str) -> None:
        assert self._transport
        payload: dict[str, Any] = {"cmd": cmd}
        if cmd == "enablehttp" or cmd == "enablemodbustcp":
            payload["enable"] = True
        if cmd == "model":
            payload["type"] = 1
        timeout = 25.0 if cmd in ("checkota", "startota", "otaprogress", "restart", "reset") else 15.0
        resp = await self._transport.send_command(payload, expected_event=cmd, timeout=timeout)
        self._log(f"{title}: {json.dumps(resp, ensure_ascii=False)}")
        data = resp.get("d") if isinstance(resp.get("d"), dict) else {}
        if cmd == "getFunctionMap":
            raw = data.get("functionMap", resp.get("functionMap"))
            try:
                text = decode_function_map(int(raw), self._lang)
            except (TypeError, ValueError):
                text = (f"Cannot parse functionMap: {raw}" if self._lang == "en" else f"无法解析 functionMap: {raw}")
            self._status_comm = text
            self._fmap_raw = raw
            self._refresh_dev_status()
            self._log(text)
            self._paint_comm()
        if cmd == "model" and data:
            self._model_d = data
            snap = format_model_snapshot(data, self._lang)
            self._log(snap)
            mad = data.get("MAD")
            if mad:
                self._log(f"当前 485 / Modbus 参数 MAD = {mad}")
            wn = data.get("WN")
            if wn:
                self._status_wifi = f"已配置 SSID={wn}"
                self._refresh_dev_status()
            self._paint_comm()
        if cmd == "mqttdata":
            self._mqtt_d = data
            self._paint_comm()
        if cmd == "udpdata":
            self._udp_d = data if data else resp.get("d")
            self._paint_comm()
        if cmd in ("restart", "reset") and resp.get("ok"):
            self._log("设备即将重启，GATT 会断开；若已勾选自动重连将自行连回并解锁。")

    def _on_set_modbus(self) -> None:
        if not self._require_transport():
            return
        try:
            baud = int(self.mb_baud.text().strip())
        except ValueError:
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("波特率必须是数字", "Baud rate must be a number"))
            return
        payload = {"cmd": "modbus", "baud": baud, "parityStop": 0, "address": int(self.mb_addr.value())}
        self._submit(self._custom_cmd(payload))

    def _on_read_data(self) -> None:
        if not self._require_transport():
            return
        self._submit(self._read_data())

    async def _read_data(self) -> None:
        assert self._transport
        try:
            await self._transport.send_command({"cmd": "read", "continue": True}, expected_event="read")
            text = await self._transport.read_characteristic()
            self._log(f"[READ C304] {text}")
            try:
                doc = json.loads(text)
                self._fill_meter(doc)
                ip = str(doc.get("IP", ""))
                rssi = doc.get("RSSI", "")
                sep = "; " if self._lang == "en" else "；"
                self._status_wifi = f"{wifi_ip_status(ip, self._lang)}{sep}RSSI={rssi} dBm"
                self._refresh_dev_status()
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
        except Exception as exc:
            self._log(f"读取失败: {exc}")

    def _on_custom_cmd(self) -> None:
        if not self._require_transport():
            return
        raw = self.custom_cmd_edit.toPlainText().strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, self._t("JSON 错误", "JSON error"), str(exc))
            return
        if not isinstance(payload, dict):
            QMessageBox.warning(self, self._t("提示", "Notice"), self._t("命令必须是 JSON 对象", "Command must be a JSON object"))
            return
        self._submit(self._custom_cmd(payload))

    async def _custom_cmd(self, payload: dict[str, Any]) -> None:
        assert self._transport
        event = str(payload.get("cmd") or "")
        resp = await self._transport.send_command(payload, expected_event=event or None)
        self._log(f"[应答] {json.dumps(resp, ensure_ascii=False)}")
        if payload.get("cmd") == "getwifilist" and resp.get("ok"):
            self._update_wifi_table(parse_wifi_list(resp))
        if payload.get("cmd") == "getFunctionMap":
            data = resp.get("d") or {}
            try:
                self._fmap_raw = data.get("functionMap")
                self._status_comm = decode_function_map(int(self._fmap_raw), self._lang)
                self._refresh_dev_status()
                self._paint_comm()
            except (TypeError, ValueError):
                pass
        if payload.get("cmd") == "mqttdata":
            self._mqtt_d = resp.get("d") if isinstance(resp.get("d"), dict) else {}
            self._paint_comm()
        if payload.get("cmd") == "udpdata":
            self._udp_d = resp.get("d")
            self._paint_comm()
        if payload.get("cmd") == "model":
            md = resp.get("d") if isinstance(resp.get("d"), dict) else {}
            if md:
                self._model_d = md
                self._paint_comm()

    async def _refresh_link_snapshot(self) -> None:
        await self._refresh_comm()
        await self._read_data()
        wn = self._model_d.get("WN") or ""
        if wn and "SSID=" not in (self._status_wifi or ""):
            self._status_wifi = f"{self._status_wifi}；SSID={wn}"
            self._refresh_dev_status()

    def closeEvent(self, event: Any) -> None:
        self._want_link = False
        fut = self._submit(self._silent_close())
        try:
            fut.result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    win = BleWifiWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
