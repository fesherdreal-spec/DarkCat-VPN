# --- START OF FULL client.py ---

import sys
import requests
import json
import subprocess
import os
import atexit
import winreg
import webbrowser
import logging
from urllib.parse import parse_qs, unquote

# [FIXED] Secret Leakage: Using keyring to securely store credentials in the OS vault.
import keyring

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QLineEdit,
                               QStackedWidget, QMessageBox, QComboBox, QDialog, QFrame,
                               QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
                               QGraphicsOpacityEffect, QAbstractItemView, QSpinBox)
from PySide6.QtCore import (Qt, QTimer, QPoint, QRect, QSize, QPropertyAnimation,
                            QEasingCurve)
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QRadialGradient,
                           QBrush, QCursor, QIcon)

# ==========================================================
# ⚙️ CONFIGURATION & CONSTANTS
# ==========================================================

# ##############################################################################
# !!! CRITICAL SECURITY WARNING !!!
#
# Hardcoding URLs is a TERRIBLE practice. This is for LOCAL DEVELOPMENT ONLY.
# In a real production environment, this MUST be configured via an environment
# variable, and it MUST use HTTPS.
#
# Correct Production Example:
# SERVER_URL = os.getenv("DARKVPN_SERVER_URL", "https://your-api.example.com")
#
# Leaving it hardcoded like this is begging for a security incident.
#
SERVER_URL = "https://catvpn.fesherd.ru"
# ##############################################################################


XRAY_EXECUTABLE = "core/xray.exe"
LOCAL_CONFIGS_FILE = "local_configs.json"
KEYRING_SERVICE_NAME = "DarkCatVPN"
LAST_USER_FILE = "darkcatvpn.settings"
CONTACT_EMAIL = "contact@fesherd.ru"
BUY_LINK = "https://t.me/fesherd"

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    stream=sys.stdout
)

# --- UI Colors ---
COLORS = {
    "bg": "#121212", "surface": "#1E1E1E", "primary": "#3A3A3A", "accent": "#5E5CE6",
    "success": "#32D74B", "text": "#FFFFFF", "danger": "#FF453A", "buy": "#F59E0B",
    "combo_bg": "#252525", "subtext": "#888888", "table_header": "#2A2A2A", "table_alt": "#181818"
}

# --- Global Session ---
# Disable system proxy for the application's own requests.
api = requests.Session()
api.trust_env = False

# ==========================================================
# 🚀 SYSTEM UTILITIES
# ==========================================================

def kill_existing_xray():
    """Forcefully terminate any running xray.exe processes."""
    try:
        # Use CREATE_NO_WINDOW flag to prevent console window from flashing.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(
            ["taskkill", "/f", "/im", "xray.exe"],
            shell=False, # shell=True is a security risk.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo
        )
        logging.info("Terminated existing xray.exe processes.")
    except FileNotFoundError:
        logging.warning("taskkill command not found. Skipping process cleanup.")
    except Exception as e:
        logging.error(f"Failed to kill existing xray processes: {e}")

def set_windows_proxy(enable=True, proxy_addr="127.0.0.1:10808"):
    """Enable or disable the system-wide proxy for the current user."""
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        # Ensure the key is opened with write access.
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_addr)
                logging.info(f"System proxy enabled: {proxy_addr}")
            else:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, "")
                logging.info("System proxy disabled.")
    except Exception as e:
        logging.error(f"Failed to configure Windows proxy: {e}")
        # Inform the user, as this is a critical function.
        QMessageBox.warning(None, "Proxy Error", f"Could not change system proxy settings.\nPlease check your permissions.\nError: {e}")


# ==========================================================
# 💾 DATA MANAGERS
# ==========================================================

class SettingsManager:
    """
    [MODIFIED] Manages credentials via keyring AND the last logged-in username.
    """
    @staticmethod
    def save_last_user(username: str):
        try:
            with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
                f.write(username)
        except IOError as e:
            logging.error(f"Failed to save last user: {e}")

    @staticmethod
    def load_last_user() -> str | None:
        if not os.path.exists(LAST_USER_FILE):
            return None
        try:
            with open(LAST_USER_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except IOError as e:
            logging.error(f"Failed to load last user: {e}")
            return None

    @staticmethod
    def clear_last_user():
        if os.path.exists(LAST_USER_FILE):
            try:
                os.remove(LAST_USER_FILE)
            except OSError as e:
                logging.error(f"Failed to clear last user file: {e}")

    @staticmethod
    def save_auth(username, password):
        try:
            keyring.set_password(KEYRING_SERVICE_NAME, username, password)
            SettingsManager.save_last_user(username)
            logging.info(f"Credentials and last user '{username}' saved.")
        except Exception as e:
            logging.error(f"Failed to save credentials to keyring: {e}")

    @staticmethod
    def clear_auth(username):
        if not username:
            return
        try:
            keyring.delete_password(KEYRING_SERVICE_NAME, username)
            SettingsManager.clear_last_user()
            logging.info(f"Cleared credentials and last user for '{username}'.")
        except keyring.errors.PasswordNotFoundError:
            logging.info(f"No credentials found for '{username}' to clear.")
        except Exception as e:
            logging.error(f"Failed to clear credentials from keyring: {e}")

class ConfigManager:
    """Manages local (user-added) VPN configurations."""
    @staticmethod
    def load_user_configs(username):
        if not os.path.exists(LOCAL_CONFIGS_FILE):
            return []
        try:
            with open(LOCAL_CONFIGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(username, [])
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading local configs: {e}")
            return []

    @staticmethod
    def save_user_configs(username, configs):
        data = {}
        if os.path.exists(LOCAL_CONFIGS_FILE):
            try:
                with open(LOCAL_CONFIGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass # Overwrite if corrupted

        data[username] = configs

        try:
            with open(LOCAL_CONFIGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            logging.error(f"Error saving local configs: {e}")

# ==========================================================
# 📡 API CLIENT
# ==========================================================

class ApiClient:
    """
    The client MUST NOT send authorization state (e.g., "is_admin").
    The server is the single source of truth for a user's role, based on their session.
    """
    @staticmethod
    def _request(method, endpoint, **kwargs):
        """A robust wrapper for making API requests."""
        url = f"{SERVER_URL}{endpoint}"
        try:
            # Set a reasonable timeout for all requests.
            # verify=True is the default and crucial for HTTPS security.
            response = api.request(method, url, timeout=5, **kwargs)
            response.raise_for_status() # Raises HTTPError for 4xx/5xx responses
            return response.json(), None
        except requests.exceptions.HTTPError as e:
            # Try to get a meaningful error message from the server response.
            try:
                err_msg = e.response.json().get("message", "Unknown server error")
            except json.JSONDecodeError:
                err_msg = e.response.text
            logging.warning(f"API Error {e.response.status_code} on {endpoint}: {err_msg}")
            return None, err_msg
        except requests.exceptions.RequestException as e:
            # Covers connection errors, timeouts, etc.
            logging.error(f"Network error on {endpoint}: {e}")
            return None, "Server is unavailable"
        except json.JSONDecodeError:
            logging.error(f"Failed to decode JSON response from {endpoint}")
            return None, "Invalid response from server"

    @staticmethod
    def login(username, password):
        return ApiClient._request("post", "/login", json={"username": username, "password": password})

    @staticmethod
    def register(username, password):
        return ApiClient._request("post", "/register", json={"username": username, "password": password})

    @staticmethod
    def send_heartbeat():
        # Heartbeat is not critical, so we can be more lenient with errors.
        try:
            api.post(f"{SERVER_URL}/heartbeat", timeout=2)
        except requests.exceptions.RequestException:
            pass # Don't log spam for heartbeat failures

    @staticmethod
    def get_users():
        return ApiClient._request("get", "/admin/users")

    @staticmethod
    def update_user_config(target_user, new_config, config_name, days):
        payload = {
            "target_user": target_user,
            "config": new_config,
            "config_name": config_name,
            "days": days
        }
        return ApiClient._request("post", "/admin/update_config", json=payload)

    @staticmethod
    def delete_user(target_user):
        return ApiClient._request("post", "/admin/delete_user", json={"target_user": target_user})

    @staticmethod
    def reset_password(target_user, new_pass):
        payload = {"target_user": target_user, "new_password": new_pass}
        return ApiClient._request("post", "/admin/reset_password", json=payload)


# ==========================================================
# ANIMATED COMPONENTS
# ==========================================================
class AnimButton(QPushButton):
    def __init__(self, text, bg_color=COLORS['surface'], txt_color="white", parent=None):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(45)
        self.bg_color = bg_color
        self.hover_color = COLORS['accent'] if bg_color == COLORS['surface'] else "#444"
        if bg_color == COLORS['accent']: self.hover_color = "#7B79FF"
        if bg_color == COLORS['danger']: self.hover_color = "#FF6B6B"
        if bg_color == COLORS['buy']: self.hover_color = "#FFC107"
        self.setStyleSheet(f"QPushButton {{ background-color: {self.bg_color}; color: {txt_color}; border-radius: 10px; font-weight: bold; border: 1px solid #333; padding: 0 15px; }}")
        self.graphics_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.graphics_effect)
        self.graphics_effect.setOpacity(1.0)

    def enterEvent(self, event):
        self.setStyleSheet(f"QPushButton {{ background-color: {self.hover_color}; color: white; border-radius: 10px; font-weight: bold; border: 1px solid {self.hover_color}; }}")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(f"QPushButton {{ background-color: {self.bg_color}; color: white; border-radius: 10px; font-weight: bold; border: 1px solid #333; }}")
        super().leaveEvent(event)

class PowerButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.state = "OFF"
        self.angle = 0
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.rotate)
        self.anim_timer.start(16)

    def set_state(self, s):
        self.state = s
        self.update()

    def rotate(self):
        if self.state == "CONNECTING":
            self.angle += 5
            if self.angle >= 360: self.angle = 0
            self.update()
        else:
            self.angle = 0

    def paintEvent(self, e):
        painter = QPainter()
        if not painter.begin(self):
            return
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            c = QPoint(90, 90)
            grad_off = QRadialGradient(c, 90); grad_off.setColorAt(0, "#2C2C2C"); grad_off.setColorAt(1, "#151515")
            grad_on = QRadialGradient(c, 90); grad_on.setColorAt(0, "#32D74B"); grad_on.setColorAt(1, "#28A745")
            bg_brush = QBrush(grad_on if self.state == "ON" else grad_off)

            painter.setPen(Qt.NoPen); painter.setBrush(bg_brush); painter.drawEllipse(c, 80, 80)
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor("#111"), 4)); painter.drawEllipse(c, 82, 82)

            if self.state == "CONNECTING":
                painter.setPen(QPen(QColor(COLORS['accent']), 6, Qt.SolidLine, Qt.RoundCap))
                painter.drawArc(QRect(15, 15, 150, 150), -self.angle * 16, 100 * 16)

            icon_col = QColor("white") if self.state == "ON" else QColor("#666")
            if self.state == "CONNECTING": icon_col = QColor(COLORS['accent'])

            painter.setPen(QPen(icon_col, 6, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(QRect(50, 50, 80, 80), 35 * 16, 290 * 16)
            painter.drawLine(90, 40, 90, 90)
        finally:
            painter.end()

class ModernInput(QLineEdit):
    def __init__(self, ph):
        super().__init__()
        self.setPlaceholderText(ph)
        self.setFixedHeight(45)
        self.setStyleSheet(f"QLineEdit {{ background-color: {COLORS['surface']}; border: 1px solid #333; border-radius: 10px; padding: 0 15px; color: white; font-size: 14px; }} QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; background-color: #252525; }}")

class PasswordInput(QFrame):
    def __init__(self, ph):
        super().__init__()
        self.setFixedHeight(45)
        self.setStyleSheet(f"QFrame {{ background:{COLORS['surface']}; border:1px solid #333; border-radius:10px; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 5, 0)
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(ph)
        self.line_edit.setEchoMode(QLineEdit.Password)
        self.line_edit.setStyleSheet("border: none; background: transparent; color: white; padding-left: 15px; font-size:14px;")
        self.toggle_btn = QPushButton("👁")
        self.toggle_btn.setFixedSize(30, 30)
        self.toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.toggle_btn.setStyleSheet("border: none; color: #666; font-size: 16px;")
        self.toggle_btn.clicked.connect(self.toggle_visibility)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.toggle_btn)

    def toggle_visibility(self):
        if self.line_edit.echoMode() == QLineEdit.Password:
            self.line_edit.setEchoMode(QLineEdit.Normal)
            self.toggle_btn.setStyleSheet(f"border: none; color: {COLORS['accent']}; font-size: 16px;")
        else:
            self.line_edit.setEchoMode(QLineEdit.Password)
            self.toggle_btn.setStyleSheet("border: none; color: #666; font-size: 16px;")

    def text(self): return self.line_edit.text()

class AddConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Config"); self.setFixedSize(320, 250)
        self.setStyleSheet(f"background:{COLORS['bg']}; color:white")
        l = QVBoxLayout(self)
        l.addWidget(QLabel("Название (необязательно):"))
        self.name_inp = ModernInput("Например: Германия")
        l.addWidget(QLabel("VLESS Ссылка:"))
        self.link_inp = ModernInput("vless://...")
        btn = AnimButton("Сохранить", bg_color=COLORS['accent']); btn.clicked.connect(self.accept)
        l.addWidget(self.name_inp); l.addWidget(self.link_inp); l.addWidget(btn)
    def get_data(self): return self.name_inp.text(), self.link_inp.text()


class EditConfigDialog(QDialog):
    def __init__(self, target_user, parent=None):
        super().__init__(parent)
        self.target_user = target_user
        self.setWindowTitle(f"Manage: {target_user}")
        self.setFixedSize(400, 600)
        self.setStyleSheet(f"background:{COLORS['bg']}; color:white")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("🔒 Безопасность:"))
        pass_group = QFrame(); pass_group.setStyleSheet(f"background:{COLORS['surface']}; border-radius:10px; padding: 5px;")
        pg = QVBoxLayout(pass_group); pg.setContentsMargins(10,10,10,10)
        self.new_pass_inp = ModernInput("Новый пароль"); self.new_pass_inp.setStyleSheet("border:1px solid #444;")
        pass_btn = AnimButton("Обновить пароль", bg_color=COLORS['primary']); pass_btn.clicked.connect(self.save_password)
        pg.addWidget(self.new_pass_inp); pg.addWidget(pass_btn); layout.addWidget(pass_group); layout.addSpacing(10)

        layout.addWidget(QLabel("🌍 VPN Конфигурация:"))
        conf_group = QFrame(); conf_group.setStyleSheet(f"background:{COLORS['surface']}; border-radius:10px; padding: 5px;")
        cg = QVBoxLayout(conf_group); cg.setContentsMargins(10,10,10,10)
        self.conf_name_inp = ModernInput("Название подписки"); self.conf_name_inp.setStyleSheet("border:1px solid #444;")
        self.text_area = QTextEdit(); self.text_area.setPlaceholderText("vless://..."); self.text_area.setStyleSheet(f"background:#121212; border:1px solid #444; border-radius:8px; padding:5px; color:white;")

        self.days_spin = QSpinBox(); self.days_spin.setRange(0, 3650); self.days_spin.setSuffix(" дн."); self.days_spin.setSpecialValueText("Безлимит")
        self.days_spin.setStyleSheet("background:#333; color:white; padding:5px; border-radius:5px;")

        cg.addWidget(self.conf_name_inp); cg.addWidget(QLabel("Срок действия:")); cg.addWidget(self.days_spin); cg.addWidget(self.text_area); layout.addWidget(conf_group)

        btns = QHBoxLayout()
        del_btn = AnimButton("Удалить", bg_color=COLORS['danger']); del_btn.clicked.connect(self.delete_config)
        save_btn = AnimButton("Сохранить", bg_color=COLORS['success']); save_btn.clicked.connect(self.accept)
        btns.addWidget(del_btn); btns.addWidget(save_btn); layout.addLayout(btns)

        self.result_config = None; self.result_name = None; self.result_days = 0

    def save_password(self):
        new_pass = self.new_pass_inp.text()
        if not new_pass:
            return
        if len(new_pass) < 12:
            QMessageBox.warning(self, "Ошибка", "Пароль должен быть не менее 12 символов.")
            return

        _, error = ApiClient.reset_password(self.target_user, new_pass)
        if error:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сбросить пароль: {error}")
        else:
            QMessageBox.information(self, "Успех", "Пароль успешно изменен!")
            self.new_pass_inp.clear()

    def delete_config(self):
        self.result_config = ""
        self.result_name = "Disabled"
        self.result_days = 0
        self.accept()

    def accept(self):
        if self.result_config is None:
            self.result_config = self.text_area.toPlainText().strip()
            self.result_name = self.conf_name_inp.text().strip()
            self.result_days = self.days_spin.value()
        super().accept()


class AdminPanel(QWidget):
    def __init__(self, app_manager):
        super().__init__()
        self.app = app_manager
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        h_layout = QHBoxLayout()
        title = QLabel("Admin Panel")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet("color: white")

        refresh_btn = AnimButton("Refresh", bg_color=COLORS['primary'])
        refresh_btn.setFixedSize(100, 40)
        refresh_btn.clicked.connect(self.load_data)

        back_btn = AnimButton("Back", bg_color=COLORS['surface'])
        back_btn.setFixedSize(80, 40)
        back_btn.clicked.connect(self.app.switch_back_to_dash)

        h_layout.addWidget(title)
        h_layout.addStretch()
        h_layout.addWidget(refresh_btn)
        h_layout.addWidget(back_btn)
        layout.addLayout(h_layout)
        layout.addSpacing(20)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "User", "Status", "Days", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 90)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 60)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 110)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(55)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.hideColumn(0)

        self.table.setStyleSheet(f"QTableWidget {{ background-color: {COLORS['surface']}; color: white; border-radius: 12px; border: none; outline: 0; alternate-background-color: {COLORS['table_alt']}; }} QHeaderView::section {{ background-color: {COLORS['table_header']}; color: #888; padding: 12px; border: none; font-weight: bold; font-size: 13px; text-transform: uppercase; }} QTableWidget::item {{ border-bottom: 1px solid {COLORS['table_header']}; padding-left: 15px; }}")
        layout.addWidget(self.table)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_data)
        self.timer.start(30000)
        self.load_data()

    def load_data(self):
        data, error = ApiClient.get_users()
        if error:
            if "Forbidden" in str(error) or "Unauthorized" in str(error):
                QMessageBox.warning(self, "Доступ запрещен", "У вас нет прав для просмотра этой страницы. Возможно, ваша сессия истекла.")
                self.app.switch_back_to_dash()
            logging.warning(f"Failed to load user data: {error}")
            return

        users = data.get('users', [])
        self.table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.table.setItem(i, 0, QTableWidgetItem(str(u['id'])))
            username_txt = u['username'] if u['username'] else "Unknown"
            user_item = QTableWidgetItem(username_txt)
            user_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            user_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(i, 1, user_item)

            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0,0,0,0)
            status_layout.setAlignment(Qt.AlignCenter)
            lbl = QLabel("●")
            lbl.setFont(QFont("Segoe UI", 16))
            col = COLORS['success'] if u['status'] == 'ONLINE' else "#444"
            lbl.setStyleSheet(f"color: {col};")
            status_layout.addWidget(lbl)
            self.table.setCellWidget(i, 2, status_widget)

            days_item = QTableWidgetItem(str(u.get('days_left', '∞')))
            days_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, days_item)

            btn_frame = QFrame()
            hbox = QHBoxLayout(btn_frame)
            hbox.setContentsMargins(5,0,5,0)
            hbox.setAlignment(Qt.AlignCenter)
            hbox.setSpacing(10)
            
            edit_btn = QPushButton("⚙")
            edit_btn.setFixedSize(36, 36)
            edit_btn.setCursor(QCursor(Qt.PointingHandCursor))
            edit_bg = COLORS['accent'] if u.get('has_config') else '#444'
            edit_btn.setStyleSheet(f"background: {edit_bg}; color: white; border-radius: 8px; font-weight: bold; font-size: 18px;")
            edit_btn.clicked.connect(lambda checked=False, user=u['username']: self.open_editor(user))

            del_btn = QPushButton("🗑")
            del_btn.setFixedSize(36, 36)
            del_btn.setCursor(QCursor(Qt.PointingHandCursor))
            del_btn.setStyleSheet(f"background: {COLORS['danger']}; color: white; border-radius: 8px; font-weight: bold; font-size: 16px;")
            del_btn.clicked.connect(lambda checked=False, user=u['username']: self.delete_user_confirm(user))

            hbox.addWidget(edit_btn)
            hbox.addWidget(del_btn)
            self.table.setCellWidget(i, 4, btn_frame)

    def open_editor(self, username):
        dlg = EditConfigDialog(username, self)
        if dlg.exec():
            new_conf, new_name, days = dlg.result_config, dlg.result_name, dlg.result_days
            if new_conf is not None:
                _, error = ApiClient.update_user_config(username, new_conf, new_name, days)
                if error:
                    QMessageBox.warning(self, "Ошибка", f"Не удалось обновить конфиг: {error}")
                else:
                    self.load_data()

    def delete_user_confirm(self, username):
        reply = QMessageBox.question(self, 'Подтверждение', f"Вы уверены, что хотите удалить пользователя {username}?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            _, error = ApiClient.delete_user(username)
            if error:
                QMessageBox.warning(self, "Ошибка", f"Не удалось удалить пользователя: {error}")
            else:
                self.load_data()

class LoginScreen(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app; l = QVBoxLayout(self); l.setAlignment(Qt.AlignCenter); l.setSpacing(20); l.setContentsMargins(40,0,40,0)
        t = QLabel("DarkCat VPN"); t.setFont(QFont("Segoe UI", 28, QFont.Bold)); t.setStyleSheet("color:white")
        self.u = ModernInput("Username"); self.p = PasswordInput("Password") 
        b = AnimButton("Log In", "accent"); b.clicked.connect(self.do_login)
        r = QPushButton("Create Account"); r.setCursor(Qt.PointingHandCursor); r.setStyleSheet("color:#888; border:none; font-weight:bold;"); r.clicked.connect(lambda: self.app.switch("reg"))
        self.opacity = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity); self.anim = QPropertyAnimation(self.opacity, b"opacity"); self.anim.setDuration(500); self.anim.setStartValue(0); self.anim.setEndValue(1); self.anim.start()
        l.addWidget(t,0,Qt.AlignCenter); l.addWidget(self.u); l.addWidget(self.p); l.addWidget(b); l.addWidget(r)

    def do_login(self):
        username = self.u.text()
        password = self.p.text()
        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Имя пользователя и пароль не могут быть пустыми.")
            return

        data, error = ApiClient.login(username, password)
        if error:
            QMessageBox.warning(self, "Ошибка входа", str(error))
        else:
            if data.get('expired_alert'):
                msg = QMessageBox(self); msg.setWindowTitle("Expired"); msg.setText("Срок подписки истек.\nХотите продлить?"); msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No); msg.setStyleSheet(f"background:{COLORS['bg']}; color:white;")
                if msg.exec() == QMessageBox.Yes: webbrowser.open(BUY_LINK)
            
            # [MODIFIED] Save both credentials to keyring and username to file.
            SettingsManager.save_auth(username, password)
            self.app.open_dashboard(data)

class RegisterScreen(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app; l = QVBoxLayout(self); l.setAlignment(Qt.AlignCenter); l.setSpacing(20); l.setContentsMargins(40,0,40,0)
        t = QLabel("Join Network"); t.setFont(QFont("Segoe UI", 28, QFont.Bold)); t.setStyleSheet("color:white")
        self.u = ModernInput("Username"); self.p = PasswordInput("Password")
        b = AnimButton("Sign Up", bg_color=COLORS['accent']); b.clicked.connect(self.do_reg)
        bk = QPushButton("Back to Login"); bk.setCursor(QCursor(Qt.PointingHandCursor)); bk.setStyleSheet("color:#888; border:none"); bk.clicked.connect(lambda: self.app.switch("login"))
        self.opacity = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity); self.anim = QPropertyAnimation(self.opacity, b"opacity"); self.anim.setDuration(500); self.anim.setStartValue(0); self.anim.setEndValue(1); self.anim.start()
        l.addWidget(t,0,Qt.AlignCenter); l.addWidget(self.u); l.addWidget(self.p); l.addWidget(b); l.addWidget(bk)

    def do_reg(self):
        username = self.u.text()
        password = self.p.text()
        if not (username and password and len(password) >= 12):
            QMessageBox.warning(self, "Ошибка", "Требуется имя пользователя и пароль не менее 12 символов.")
            return

        _, error = ApiClient.register(username, password)
        if error:
            QMessageBox.warning(self, "Ошибка регистрации", error)
        else:
            QMessageBox.information(self, "Успех", "Регистрация прошла успешно. Теперь вы можете войти.")
            self.app.switch("login")

class Dashboard(QWidget):
    def __init__(self, user_data, app):
        super().__init__()
        self.user_data = user_data
        self.username = user_data.get('username')
        self.app = app
        self.vpn_process = None
        self.configs = []
        atexit.register(self.force_stop)
        l = QVBoxLayout(self); l.setContentsMargins(0,20,0,30)
        self.opacity = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity); self.anim = QPropertyAnimation(self.opacity, b"opacity"); self.anim.setDuration(600); self.anim.setStartValue(0); self.anim.setEndValue(1); self.anim.setEasingCurve(QEasingCurve.OutQuad); self.anim.start()
        h = QHBoxLayout(); h.setContentsMargins(20,0,20,0)
        ul = QLabel(f"👤 {self.username}"); ul.setStyleSheet("color:#888; font-weight:bold")
        ex = QPushButton("Exit"); ex.setCursor(QCursor(Qt.PointingHandCursor)); ex.setStyleSheet(f"color:{COLORS['danger']}; border:none; font-weight:bold"); ex.clicked.connect(self.logout)
        h.addWidget(ul); h.addStretch()
        if user_data.get('role') == 'admin':
            admin_btn = QPushButton("Admin Panel"); admin_btn.setStyleSheet(f"color: {COLORS['accent']}; font-weight: bold; border: 1px solid {COLORS['accent']}; border-radius: 8px; padding: 6px 12px;"); admin_btn.setCursor(QCursor(Qt.PointingHandCursor)); admin_btn.clicked.connect(self.app.open_admin_panel); h.addWidget(admin_btn); h.addSpacing(15)
        h.addWidget(ex); l.addLayout(h); l.addStretch()
        cfg_frame = QFrame(); cfg_frame.setStyleSheet(f"background:{COLORS['surface']}; border-radius:15px;")
        cfg_frame.setFixedSize(340, 60)
        cfl = QHBoxLayout(cfg_frame); cfl.setContentsMargins(10,5,10,5)
        self.combo = QComboBox(); self.combo.setFixedHeight(40); self.combo.setStyleSheet(f"QComboBox {{ background: transparent; color: white; border: none; font-size:14px; font-weight:bold; }} QComboBox::drop-down {{ border: none; }}")
        self.combo.currentIndexChanged.connect(self.on_combo_changed)
        add_btn = QPushButton("+"); add_btn.setFixedSize(35, 35); add_btn.setCursor(QCursor(Qt.PointingHandCursor)); add_btn.setStyleSheet(f"background:{COLORS['bg']}; color:{COLORS['accent']}; border-radius:8px; font-weight:bold; font-size:18px"); add_btn.clicked.connect(self.add_config_dialog)
        del_btn = QPushButton("🗑"); del_btn.setFixedSize(35, 35); del_btn.setCursor(QCursor(Qt.PointingHandCursor)); del_btn.setStyleSheet(f"background:{COLORS['bg']}; color:{COLORS['danger']}; border-radius:8px; font-weight:bold; font-size:16px"); del_btn.clicked.connect(self.delete_current_local_config)
        cfl.addWidget(self.combo); cfl.addWidget(add_btn); cfl.addWidget(del_btn)
        l.addWidget(cfg_frame, 0, Qt.AlignCenter); l.addSpacing(30)
        self.btn = PowerButton(); self.btn.clicked.connect(self.toggle); l.addWidget(self.btn, 0, Qt.AlignCenter)
        self.st = QLabel("DISCONNECTED"); self.st.setFont(QFont("Segoe UI", 16, QFont.Bold)); self.st.setStyleSheet("color:#666; margin-top:25px"); l.addWidget(self.st, 0, Qt.AlignCenter)
        self.ip_lbl = QLabel("Server IP: ---"); self.ip_lbl.setStyleSheet(f"color:{COLORS['subtext']}; font-size:12px; margin-top:5px"); l.addWidget(self.ip_lbl, 0, Qt.AlignCenter); l.addStretch()
        buy_btn = AnimButton("💎 Купить VPN / Продлить", "buy"); buy_btn.clicked.connect(lambda: webbrowser.open(BUY_LINK)); l.addWidget(buy_btn, 0, Qt.AlignCenter)
        fb_btn = QPushButton("💬 Feedback / Support"); fb_btn.setCursor(QCursor(Qt.PointingHandCursor)); fb_btn.setStyleSheet(f"background: transparent; color: {COLORS['subtext']}; border: none;"); fb_btn.clicked.connect(self.show_feedback); l.addWidget(fb_btn, 0, Qt.AlignCenter)
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(ApiClient.send_heartbeat)
        self.refresh_configs()

    def refresh_configs(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        self.configs = []
        server_config_link = self.user_data.get('config', '')
        if server_config_link:
            config_name = self.user_data.get('config_name', 'Server Default')
            self.configs.append({"name": config_name, "link": server_config_link, "is_server": True})
        local_configs = ConfigManager.load_user_configs(self.username)
        for lc in local_configs:
            lc['is_server'] = False
        self.configs.extend(local_configs)
        if not self.configs:
            self.combo.addItem("No configurations available")
        else:
            for cfg in self.configs:
                self.combo.addItem(cfg['name'])
        self.combo.blockSignals(False)
        self.update_ip_display()

    def on_combo_changed(self):
        if self.combo.count() == 0 or not self.configs: return
        self.update_ip_display()
        if self.btn.state == "ON": self.force_stop(); self.start_vpn()

    def update_ip_display(self):
        idx = self.combo.currentIndex()
        if idx >= 0 and idx < len(self.configs):
            self.ip_lbl.setText(f"Server IP: {self.extract_ip(self.configs[idx]['link'])}")
        else: self.ip_lbl.setText("Server IP: ---")

    def extract_ip(self, link):
        try: return link.split("@")[1].split(":")[0]
        except: return "Unknown"

    def add_config_dialog(self):
        dlg = AddConfigDialog(self)
        if dlg.exec():
            name, link = dlg.get_data()
            if link.startswith("vless://"):
                if not name.strip():
                    try:
                        name = unquote(link.split("#")[-1]) if "#" in link else "Local Config"
                    except Exception:
                        name = "Local Config"
                local_configs = ConfigManager.load_user_configs(self.username)
                local_configs.append({"name": name, "link": link})
                ConfigManager.save_user_configs(self.username, local_configs)
                self.refresh_configs()
                self.combo.setCurrentIndex(self.combo.count() - 1)
            else:
                QMessageBox.warning(self, "Ошибка", "Ссылка должна начинаться с vless://")

    def delete_current_local_config(self):
        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self.configs): return
        if self.configs[idx].get('is_server'):
            QMessageBox.warning(self, "Ошибка", "Нельзя удалить конфигурацию, полученную от сервера.")
            return
        reply = QMessageBox.question(self, 'Удаление', f"Удалить '{self.configs[idx]['name']}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            server_configs_count = sum(1 for c in self.configs if c.get('is_server'))
            local_config_index_to_delete = idx - server_configs_count
            local_configs = ConfigManager.load_user_configs(self.username)
            if 0 <= local_config_index_to_delete < len(local_configs):
                del local_configs[local_config_index_to_delete]
                ConfigManager.save_user_configs(self.username, local_configs)
                self.refresh_configs()

    def show_feedback(self):
        msg = QMessageBox(self); msg.setWindowTitle("Feedback"); msg.setText(f"Found a bug? Have an idea?\n\nContact us:\n{CONTACT_EMAIL}"); msg.setStyleSheet(f"background:{COLORS['bg']}; color:white;"); msg.exec()

    def toggle(self): self.start_vpn() if self.btn.state == "OFF" else self.stop_vpn()

    def generate_config(self, link):
        try:
            if not link.startswith("vless://"): return None
            body = link.split("#")[0].replace("vless://", ""); info, params_str = body.split("?"); uuid, addr_port = info.split("@"); addr, port = addr_port.split(":"); p = parse_qs(params_str)
            network_type = p.get("type", ["tcp"])[0]; flow = p.get("flow", [""])[0]
            config = {"log": {"loglevel": "warning"}, "inbounds": [{"port": 10808, "listen": "127.0.0.1", "protocol": "http", "settings": {"udp": True}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True}}, {"port": 10809, "listen": "127.0.0.1", "protocol": "socks", "settings": {"udp": True}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True}}], "outbounds": [{"protocol": "vless", "settings": {"vnext": [{"address": addr, "port": int(port), "users": [{"id": uuid, "encryption": "none", "flow": flow}]}]}, "streamSettings": {"network": network_type, "security": p.get("security", ["none"])[0]}}], "policy": {"levels": {"0": {"handshake": 10, "connIdle": 100, "uplinkOnly": 2, "downlinkOnly": 5, "statsUserUplink": True, "statsUserDownlink": True, "bufferSize": 10240}}, "system": {"statsInboundUplink": True, "statsInboundDownlink": True, "statsOutboundUplink": True, "statsOutboundDownlink": True}}}
            stream = config["outbounds"][0]["streamSettings"]
            if network_type == "tcp": stream["tcpSettings"] = { "header": { "type": "none" } }
            if "vision" in flow: config["outbounds"][0]["mux"] = { "enabled": False }
            else: config["outbounds"][0]["mux"] = { "enabled": True, "concurrency": 8 }
            sec = p.get("security", ["none"])[0]
            if sec == "reality": stream["realitySettings"] = {"publicKey": p.get("pbk", [""])[0], "fingerprint": p.get("fp", ["chrome"])[0], "serverName": p.get("sni", [""])[0], "shortId": p.get("sid", [""])[0], "spiderX": p.get("spx", [""])[0]}
            elif sec == "tls": stream["tlsSettings"] = {"serverName": p.get("sni", [""])[0], "fingerprint": p.get("fp", ["chrome"])[0]}
            return config
        except Exception as e:
            logging.error(f"Failed to parse vless link: {e}")
            return None

    def start_vpn(self):
        if not self.configs:
            QMessageBox.warning(self, "Ошибка", "Нет доступных конфигураций!"); return
        self.btn.set_state("CONNECTING"); self.st.setText("CONNECTING..."); self.st.setStyleSheet(f"color:{COLORS['accent']}; margin-top:25px"); QTimer.singleShot(600, self.finish_start)

    def finish_start(self):
        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self.configs):
            self.stop_vpn()
            return
        link = self.configs[idx]['link']
        config_json = self.generate_config(link)
        if not config_json:
            QMessageBox.critical(self, "Ошибка", "Не удалось сгенерировать конфигурацию из ссылки.")
            self.stop_vpn()
            return
        if not os.path.exists(XRAY_EXECUTABLE):
            QMessageBox.critical(self, "Ошибка", f"Исполняемый файл не найден: {XRAY_EXECUTABLE}")
            self.stop_vpn()
            return
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.vpn_process = subprocess.Popen(
                [XRAY_EXECUTABLE, 'run'],
                cwd="core",
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=si,
                encoding='utf-8'
            )
            self.vpn_process.stdin.write(json.dumps(config_json))
            self.vpn_process.stdin.close()
            set_windows_proxy(True)
            self.btn.set_state("ON")
            self.st.setText("PROTECTED")
            self.st.setStyleSheet(f"color:{COLORS['success']}; margin-top:25px")
            self.heartbeat_timer.start(30000)
            logging.info("VPN connection established.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка запуска", f"Не удалось запустить процесс VPN: {e}")
            self.stop_vpn()

    def stop_vpn(self):
        self.force_stop()
        self.btn.set_state("OFF")
        self.st.setText("DISCONNECTED")
        self.st.setStyleSheet("color:#666; margin-top:25px")
        self.heartbeat_timer.stop()

    def force_stop(self):
        set_windows_proxy(False)
        if self.vpn_process and self.vpn_process.poll() is None:
            logging.info("Terminating VPN process...")
            self.vpn_process.terminate()
            try:
                self.vpn_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logging.warning("VPN process did not terminate gracefully, killing.")
                self.vpn_process.kill()
            self.vpn_process = None

    def logout(self):
        # [MODIFIED] Clear credentials using the stored username.
        SettingsManager.clear_auth(self.username)
        self.force_stop()
        self.app.switch_login()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DarkCat VPN")
        self.setFixedSize(430, 700)
        try:
            self.setWindowIcon(QIcon("icon.ico"))
        except Exception as e:
            logging.warning(f"Could not load icon.ico: {e}")

        self.setStyleSheet(f"background:{COLORS['bg']}")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Always create login/register screens
        self.login = LoginScreen(self)
        self.reg = RegisterScreen(self)
        self.stack.addWidget(self.login)
        self.stack.addWidget(self.reg)
        
        # [MODIFIED] Centralized startup logic
        QTimer.singleShot(100, self.attempt_auto_login)

    def attempt_auto_login(self):
        """
        The core auto-login logic. Securely attempts to create a new session.
        """
        last_user = SettingsManager.load_last_user()
        if not last_user:
            self.show_login_screen()
            return

        logging.info(f"Attempting auto-login for user: {last_user}")
        password = keyring.get_password(KEYRING_SERVICE_NAME, last_user)

        if not password:
            logging.warning("Username found but no password in keyring. Forcing login.")
            self.show_login_screen()
            return
        
        data, error = ApiClient.login(last_user, password)
        
        if data:
            logging.info("Auto-login successful.")
            self.open_dashboard(data)
        else:
            logging.warning(f"Auto-login failed for '{last_user}'. Credentials may be outdated. Error: {error}")
            # [CRITICAL] If stored credentials fail, they are invalid. Clean them up.
            SettingsManager.clear_auth(last_user)
            QMessageBox.warning(self, "Сессия истекла", "Не удалось войти автоматически. Пожалуйста, введите ваши данные заново.")
            self.show_login_screen()

    def show_login_screen(self):
        """Switches to the login screen view."""
        self.stack.setCurrentWidget(self.login)

    def switch(self, n):
        self.stack.setCurrentWidget(self.login if n == "login" else self.reg)

    def open_dashboard(self, d):
        self.dash = Dashboard(d, self)
        self.stack.addWidget(self.dash)
        self.stack.setCurrentWidget(self.dash)

    def open_admin_panel(self):
        self.admin = AdminPanel(self)
        self.stack.addWidget(self.admin)
        self.stack.setCurrentWidget(self.admin)

    def switch_back_to_dash(self):
        self.stack.setCurrentWidget(self.dash)

    def switch_login(self):
        if hasattr(self, 'dash'):
            self.stack.removeWidget(self.dash); del self.dash
        if hasattr(self, 'admin'):
            self.stack.removeWidget(self.admin); del self.admin
        self.show_login_screen()

    def closeEvent(self, e):
        if hasattr(self, 'dash'):
            self.dash.force_stop()
        e.accept()

if __name__ == "__main__":
    kill_existing_xray()
    set_windows_proxy(False)
    app = QApplication(sys.argv)
    win = MainWindow()
    try:
        win.show()
        sys.exit(app.exec())
    finally:
        logging.info("Application shutting down, ensuring proxy is disabled.")
        set_windows_proxy(False)
        kill_existing_xray()
