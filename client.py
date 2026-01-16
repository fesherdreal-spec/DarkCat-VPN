import sys
import requests
import json
import subprocess
import os
import atexit
import winreg
import webbrowser
from urllib.parse import parse_qs, unquote
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
# ⚙️ НАСТРОЙКИ
# ==========================================================
SERVER_URL = "https://catvpn.fesherd.ru"  
XRAY_PATH = "core/xray.exe"
LOCAL_CONFIGS_FILE = "local_configs.json"
SETTINGS_FILE = "darkvpn.settings"
CONTACT_EMAIL = "contact@fesherd.ru"
BUY_LINK = "https://t.me/fesherd"

COLORS = {
    "bg": "#121212", 
    "surface": "#1E1E1E", 
    "primary": "#3A3A3A", 
    "accent": "#5E5CE6", 
    "success": "#32D74B", 
    "text": "#FFFFFF", 
    "danger": "#FF453A",
    "buy": "#F59E0B", 
    "combo_bg": "#252525", 
    "subtext": "#888888", 
    "table_header": "#2A2A2A",
    "table_alt": "#181818"
}

# Отключаем системный прокси для запросов самого приложения
api = requests.Session()
api.trust_env = False 

def kill_existing_xray():
    try: 
        subprocess.run("taskkill /f /im xray.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: 
        pass

def set_windows_proxy(enable=True):
    try:
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, "127.0.0.1:10808")
        else:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
    except Exception as e: 
        print(f"Proxy Error: {e}")

def set_hidden(file_path):
    if os.name == 'nt' and os.path.exists(file_path):
        try:
            subprocess.check_call(["attrib", "+h", file_path])
        except Exception as e:
            print(f"Could not hide file {file_path}: {e}")

# ==========================================================
# 💾 МЕНЕДЖЕРЫ (ИСПРАВЛЕНО ЧТЕНИЕ ФАЙЛОВ)
# ==========================================================
class SettingsManager:
    @staticmethod
    def save_auth(username, password):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"username": username, "password": password}, f)
            set_hidden(SETTINGS_FILE)
        except Exception as e:
            print(f"Error saving settings: {e}")

    @staticmethod
    def load_auth():
        if not os.path.exists(SETTINGS_FILE): return None
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f: 
                return json.load(f)
        except:
            return None

    @staticmethod
    def clear_auth():
        if os.path.exists(SETTINGS_FILE): 
            os.remove(SETTINGS_FILE)

class ConfigManager:
    @staticmethod
    def load_user_configs(username):
        if not os.path.exists(LOCAL_CONFIGS_FILE):
            return []
        try:
            with open(LOCAL_CONFIGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return []
                return data.get(username, [])
        except: 
            return []
    
    @staticmethod
    def save_user_config(username, name, link):
        data = {}
        if os.path.exists(LOCAL_CONFIGS_FILE):
            try: 
                with open(LOCAL_CONFIGS_FILE, "r", encoding="utf-8") as f: 
                    data = json.load(f)
            except: 
                pass
        
        if username not in data: 
            data[username] = []
        
        data[username].append({"name": name, "link": link})
        
        with open(LOCAL_CONFIGS_FILE, "w", encoding="utf-8") as f: 
            json.dump(data, f, indent=4, ensure_ascii=False)
            
    @staticmethod
    def delete_user_config(username, config_index):
        if not os.path.exists(LOCAL_CONFIGS_FILE):
            return
        try:
            with open(LOCAL_CONFIGS_FILE, "r", encoding="utf-8") as f: 
                data = json.load(f)
            
            if username in data and 0 <= config_index < len(data[username]):
                del data[username][config_index]
                
                with open(LOCAL_CONFIGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        except: 
            pass

class ApiClient:
    @staticmethod
    def login(u, p):
        try:
            r = api.post(f"{SERVER_URL}/login", json={"username":u, "password":p}, timeout=3)
            if r.status_code == 200:
                return True, r.json()
            else:
                return False, "Ошибка входа"
        except: 
            return False, "Сервер недоступен"

    @staticmethod
    def register(u, p):
        try:
            r = api.post(f"{SERVER_URL}/register", json={"username":u, "password":p}, timeout=3)
            if r.status_code == 200:
                return True, "OK"
            else:
                return False, "Ошибка"
        except: 
            return False, "Сервер недоступен"

    @staticmethod
    def send_heartbeat(username):
        try: 
            api.post(f"{SERVER_URL}/heartbeat", json={"username": username}, timeout=1)
        except: 
            pass

    @staticmethod
    def get_users(is_admin):
        try:
            r = api.post(f"{SERVER_URL}/admin/users", json={"is_admin": is_admin}, timeout=3)
            if r.status_code == 200: 
                return r.json().get('users', [])
            elif r.status_code == 403: 
                return "FORBIDDEN"
            return []
        except: 
            return []

    @staticmethod
    def update_user_config(is_admin, target_user, new_config, config_name, days):
        try:
            r = api.post(f"{SERVER_URL}/admin/update_config", json={
                "is_admin": is_admin, "target_user": target_user, 
                "config": new_config, "config_name": config_name, "days": days
            }, timeout=3)
            return r.status_code == 200
        except: 
            return False

    @staticmethod
    def get_user_config(is_admin, target_user):
        try:
            r = api.post(f"{SERVER_URL}/admin/get_config", json={"is_admin": is_admin, "target_user": target_user}, timeout=3)
            if r.status_code == 200: 
                return r.json()
            return {"config": "", "name": ""}
        except: 
            return {"config": "", "name": ""}

    @staticmethod
    def delete_user(is_admin, target_user):
        try:
            r = api.post(f"{SERVER_URL}/admin/delete_user", json={"is_admin": is_admin, "target_user": target_user}, timeout=3)
            return r.status_code == 200
        except: 
            return False

    @staticmethod
    def reset_password(is_admin, target_user, new_pass):
        try:
            r = api.post(f"{SERVER_URL}/admin/reset_password", json={"is_admin": is_admin, "target_user": target_user, "new_password": new_pass}, timeout=3)
            return r.status_code == 200
        except: 
            return False

# ==========================================================
# ANIMATED COMPONENTS
# ==========================================================
class AnimButton(QPushButton):
    def __init__(self, text, bg_color=COLORS['surface'], txt_color="white", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
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
        self.setCursor(Qt.PointingHandCursor)
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
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
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
        btn = AnimButton("Сохранить", "accent"); btn.clicked.connect(self.accept)
        l.addWidget(self.name_inp); l.addWidget(self.link_inp); l.addWidget(btn)
    def get_data(self): return self.name_inp.text(), self.link_inp.text()

class EditConfigDialog(QDialog):
    def __init__(self, target_user, parent=None):
        super().__init__(parent)
        self.target_user = target_user; self.setWindowTitle(f"Manage: {target_user}"); self.setFixedSize(400, 600)
        self.setStyleSheet(f"background:{COLORS['bg']}; color:white")
        l = QVBoxLayout(self)
        
        l.addWidget(QLabel("🔒 Безопасность:"))
        pass_group = QFrame(); pass_group.setStyleSheet(f"background:{COLORS['surface']}; border-radius:10px; padding: 5px;")
        pg = QVBoxLayout(pass_group); pg.setContentsMargins(10,10,10,10)
        self.new_pass_inp = ModernInput("Новый пароль"); self.new_pass_inp.setStyleSheet("border:1px solid #444;")
        pass_btn = AnimButton("Обновить пароль", "primary"); pass_btn.clicked.connect(self.save_password)
        pg.addWidget(self.new_pass_inp); pg.addWidget(pass_btn); l.addWidget(pass_group); l.addSpacing(10)

        l.addWidget(QLabel("🌍 VPN Конфигурация:"))
        conf_group = QFrame(); conf_group.setStyleSheet(f"background:{COLORS['surface']}; border-radius:10px; padding: 5px;")
        cg = QVBoxLayout(conf_group); cg.setContentsMargins(10,10,10,10)
        self.conf_name_inp = ModernInput("Название подписки"); self.conf_name_inp.setStyleSheet("border:1px solid #444;")
        self.text_area = QTextEdit(); self.text_area.setPlaceholderText("vless://..."); self.text_area.setStyleSheet(f"background:#121212; border:1px solid #444; border-radius:8px; padding:5px; color:white;")
        
        self.days_spin = QSpinBox(); self.days_spin.setRange(0, 3650); self.days_spin.setSuffix(" дн."); self.days_spin.setSpecialValueText("Безлимит")
        self.days_spin.setStyleSheet("background:#333; color:white; padding:5px; border-radius:5px;")

        cg.addWidget(self.conf_name_inp); cg.addWidget(QLabel("Срок действия:")); cg.addWidget(self.days_spin); cg.addWidget(self.text_area); l.addWidget(conf_group)
        
        data = ApiClient.get_user_config(1, target_user); self.text_area.setPlainText(data.get('config', '')); self.conf_name_inp.setText(data.get('name', ''))
        
        btns = QHBoxLayout()
        del_btn = AnimButton("Удалить", "danger"); del_btn.clicked.connect(self.delete_config)
        save_btn = AnimButton("Сохранить", "success"); save_btn.clicked.connect(self.accept)
        btns.addWidget(del_btn); btns.addWidget(save_btn); l.addLayout(btns)
        
        self.result_config = None; self.result_name = None; self.result_days = 0

    def save_password(self):
        if not self.new_pass_inp.text(): return
        if ApiClient.reset_password(1, self.target_user, self.new_pass_inp.text()): QMessageBox.information(self, "OK", "Пароль изменен!"); self.new_pass_inp.clear()
        else: QMessageBox.warning(self, "Error", "Ошибка")
    def delete_config(self): self.result_config = ""; self.result_name = ""; self.accept()
    def accept(self):
        if self.result_config is None: 
            self.result_config = self.text_area.toPlainText().strip()
            self.result_name = self.conf_name_inp.text().strip()
            self.result_days = self.days_spin.value()
        super().accept()

# ==========================================================
# 👮 АДМИН ПАНЕЛЬ
# ==========================================================
class AdminPanel(QWidget):
    def __init__(self, app_manager):
        super().__init__()
        self.app = app_manager; layout = QVBoxLayout(self); layout.setContentsMargins(30, 30, 30, 30)
        
        h = QHBoxLayout(); title = QLabel("Admin Panel"); title.setFont(QFont("Segoe UI", 24, QFont.Bold)); title.setStyleSheet("color: white")
        back_btn = AnimButton("Back", "surface"); back_btn.setFixedSize(80, 40); back_btn.clicked.connect(self.app.switch_back_to_dash)
        h.addWidget(title); h.addStretch(); h.addWidget(back_btn); layout.addLayout(h); layout.addSpacing(20)
        
        self.table = QTableWidget(); self.table.setColumnCount(5); self.table.setHorizontalHeaderLabels(["ID", "User", "Status", "Days", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents); header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed); self.table.setColumnWidth(2, 90)
        header.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 60)
        header.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 110)
        
        self.table.verticalHeader().setVisible(False); self.table.verticalHeader().setDefaultSectionSize(55)
        self.table.setFocusPolicy(Qt.NoFocus); self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False); self.table.setAlternatingRowColors(True)
        self.table.hideColumn(0)
        
        self.table.setStyleSheet(f"QTableWidget {{ background-color: {COLORS['surface']}; color: white; border-radius: 12px; border: none; outline: 0; alternate-background-color: {COLORS['table_alt']}; }} QHeaderView::section {{ background-color: {COLORS['table_header']}; color: #888; padding: 12px; border: none; font-weight: bold; font-size: 13px; text-transform: uppercase; }} QTableWidget::item {{ border-bottom: 1px solid {COLORS['table_header']}; padding-left: 15px; }}")
        layout.addWidget(self.table)
        self.timer = QTimer(self); self.timer.timeout.connect(self.load_data); self.timer.start(3000); self.load_data()

    def load_data(self):
        users = ApiClient.get_users(is_admin=1)
        if users == "FORBIDDEN": self.app.switch_back_to_dash(); return
        if not isinstance(users, list): return
        self.table.setRowCount(len(users))
        for i, u in enumerate(users):
            self.table.setItem(i, 0, QTableWidgetItem(str(u['id'])))
            username_txt = u['username'] if u['username'] else "Unknown"
            user_item = QTableWidgetItem(username_txt); user_item.setFont(QFont("Segoe UI", 12, QFont.Bold)); user_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(i, 1, user_item)
            status_widget = QWidget(); status_layout = QHBoxLayout(status_widget); status_layout.setContentsMargins(0,0,0,0); status_layout.setAlignment(Qt.AlignCenter)
            lbl = QLabel("●"); lbl.setFont(QFont("Segoe UI", 16))
            col = COLORS['success'] if u['status'] == 'ONLINE' else "#444"
            lbl.setStyleSheet(f"color: {col};"); status_layout.addWidget(lbl)
            self.table.setCellWidget(i, 2, status_widget)
            days_item = QTableWidgetItem(str(u.get('days_left', '∞'))); days_item.setTextAlignment(Qt.AlignCenter); self.table.setItem(i, 3, days_item)
            btn_frame = QFrame(); hbox = QHBoxLayout(btn_frame); hbox.setContentsMargins(5,0,5,0); hbox.setAlignment(Qt.AlignCenter); hbox.setSpacing(10)
            edit_btn = QPushButton("⚙"); edit_btn.setFixedSize(36, 36); edit_btn.setCursor(Qt.PointingHandCursor)
            edit_bg = COLORS['accent'] if u.get('has_config') else '#444'
            edit_btn.setStyleSheet(f"background: {edit_bg}; color: white; border-radius: 8px; font-weight: bold; font-size: 18px;")
            edit_btn.clicked.connect(lambda _, user=u['username']: self.open_editor(user))
            del_btn = QPushButton("🗑"); del_btn.setFixedSize(36, 36); del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(f"background: {COLORS['danger']}; color: white; border-radius: 8px; font-weight: bold; font-size: 16px;")
            del_btn.clicked.connect(lambda _, user=u['username']: self.delete_user_confirm(user))
            hbox.addWidget(edit_btn); hbox.addWidget(del_btn); self.table.setCellWidget(i, 4, btn_frame)

    def open_editor(self, username):
        dlg = EditConfigDialog(username, self)
        if dlg.exec():
            new_conf = dlg.result_config; new_name = dlg.result_name; days = dlg.result_days
            if new_conf is not None:
                if ApiClient.update_user_config(1, username, new_conf, new_name, days): self.load_data()
    def delete_user_confirm(self, username):
        if username == "admin": QMessageBox.warning(self, "Stop", "Root admin protected!"); return
        if QMessageBox.question(self, 'Удаление', f"Удалить {username}?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            if ApiClient.delete_user(1, username): self.load_data()

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
        ok, d = ApiClient.login(self.u.text(), self.p.text())
        if ok: 
            if d.get('expired_alert'):
                msg = QMessageBox(self); msg.setWindowTitle("Expired"); msg.setText("Срок подписки истек.\nХотите продлить?"); msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No); msg.setStyleSheet(f"background:{COLORS['bg']}; color:white;")
                if msg.exec() == QMessageBox.Yes: webbrowser.open(BUY_LINK)
            SettingsManager.save_auth(self.u.text(), self.p.text()); self.app.open_dashboard(d)
        else: QMessageBox.warning(self, "Error", str(d))

class RegisterScreen(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app; l = QVBoxLayout(self); l.setAlignment(Qt.AlignCenter); l.setSpacing(20); l.setContentsMargins(40,0,40,0)
        t = QLabel("Join Network"); t.setFont(QFont("Segoe UI", 28, QFont.Bold)); t.setStyleSheet("color:white")
        self.u = ModernInput("Username"); self.p = PasswordInput("Password")
        b = AnimButton("Sign Up", "accent"); b.clicked.connect(self.do_reg)
        bk = QPushButton("Back to Login"); bk.setCursor(Qt.PointingHandCursor); bk.setStyleSheet("color:#888; border:none"); bk.clicked.connect(lambda: self.app.switch("login"))
        self.opacity = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity); self.anim = QPropertyAnimation(self.opacity, b"opacity"); self.anim.setDuration(500); self.anim.setStartValue(0); self.anim.setEndValue(1); self.anim.start()
        l.addWidget(t,0,Qt.AlignCenter); l.addWidget(self.u); l.addWidget(self.p); l.addWidget(b); l.addWidget(bk)
    def do_reg(self):
        ok, m = ApiClient.register(self.u.text(), self.p.text())
        if ok: 
            ok_log, d = ApiClient.login(self.u.text(), self.p.text())
            if ok_log: SettingsManager.save_auth(self.u.text(), self.p.text()); self.app.open_dashboard(d)
            else: self.app.switch("login")
        else: QMessageBox.warning(self, "Error", m)

class Dashboard(QWidget):
    def __init__(self, user_data, app):
        super().__init__()
        self.user_data = user_data; self.app = app; self.vpn_process = None; self.configs = []; atexit.register(self.force_stop)
        l = QVBoxLayout(self); l.setContentsMargins(0,20,0,30)
        self.opacity = QGraphicsOpacityEffect(self); self.setGraphicsEffect(self.opacity); self.anim = QPropertyAnimation(self.opacity, b"opacity"); self.anim.setDuration(600); self.anim.setStartValue(0); self.anim.setEndValue(1); self.anim.setEasingCurve(QEasingCurve.OutQuad); self.anim.start()
        h = QHBoxLayout(); h.setContentsMargins(20,0,20,0)
        ul = QLabel(f"👤 {user_data.get('username')}"); ul.setStyleSheet("color:#888; font-weight:bold")
        ex = QPushButton("Exit"); ex.setCursor(Qt.PointingHandCursor); ex.setStyleSheet(f"color:{COLORS['danger']}; border:none; font-weight:bold"); ex.clicked.connect(self.logout)
        h.addWidget(ul); h.addStretch()
        if user_data.get('is_admin') == 1:
            admin_btn = QPushButton("Admin Panel"); admin_btn.setStyleSheet(f"color: {COLORS['accent']}; font-weight: bold; border: 1px solid {COLORS['accent']}; border-radius: 8px; padding: 6px 12px;"); admin_btn.setCursor(Qt.PointingHandCursor); admin_btn.clicked.connect(self.app.open_admin_panel); h.addWidget(admin_btn); h.addSpacing(15)
        h.addWidget(ex); l.addLayout(h); l.addStretch()
        cfg_frame = QFrame(); cfg_frame.setStyleSheet(f"background:{COLORS['surface']}; border-radius:15px;")
        cfg_frame.setFixedSize(340, 60)
        cfl = QHBoxLayout(cfg_frame); cfl.setContentsMargins(10,5,10,5)
        self.combo = QComboBox(); self.combo.setFixedHeight(40); self.combo.setStyleSheet(f"QComboBox {{ background: transparent; color: white; border: none; font-size:14px; font-weight:bold; }} QComboBox::drop-down {{ border: none; }}")
        self.combo.currentIndexChanged.connect(self.on_combo_changed)
        add_btn = QPushButton("+"); add_btn.setFixedSize(35, 35); add_btn.setCursor(Qt.PointingHandCursor); add_btn.setStyleSheet(f"background:{COLORS['bg']}; color:{COLORS['accent']}; border-radius:8px; font-weight:bold; font-size:18px"); add_btn.clicked.connect(self.add_config_dialog)
        del_btn = QPushButton("🗑"); del_btn.setFixedSize(35, 35); del_btn.setCursor(Qt.PointingHandCursor); del_btn.setStyleSheet(f"background:{COLORS['bg']}; color:{COLORS['danger']}; border-radius:8px; font-weight:bold; font-size:16px"); del_btn.clicked.connect(self.delete_current_local_config)
        cfl.addWidget(self.combo); cfl.addWidget(add_btn); cfl.addWidget(del_btn)
        l.addWidget(cfg_frame, 0, Qt.AlignCenter); l.addSpacing(30)
        self.btn = PowerButton(); self.btn.clicked.connect(self.toggle); l.addWidget(self.btn, 0, Qt.AlignCenter)
        self.st = QLabel("DISCONNECTED"); self.st.setFont(QFont("Segoe UI", 16, QFont.Bold)); self.st.setStyleSheet("color:#666; margin-top:25px"); l.addWidget(self.st, 0, Qt.AlignCenter)
        self.ip_lbl = QLabel("Server IP: ---"); self.ip_lbl.setStyleSheet(f"color:{COLORS['subtext']}; font-size:12px; margin-top:5px"); l.addWidget(self.ip_lbl, 0, Qt.AlignCenter); l.addStretch()
        buy_btn = AnimButton("💎 Купить VPN / Продлить", "buy"); buy_btn.clicked.connect(lambda: webbrowser.open(BUY_LINK)); l.addWidget(buy_btn, 0, Qt.AlignCenter)
        fb_btn = QPushButton("💬 Feedback / Support"); fb_btn.setCursor(Qt.PointingHandCursor); fb_btn.setStyleSheet(f"background: transparent; color: {COLORS['subtext']}; border: none;"); fb_btn.clicked.connect(self.show_feedback); l.addWidget(fb_btn, 0, Qt.AlignCenter)
        self.heartbeat_timer = QTimer(self); self.heartbeat_timer.timeout.connect(self.send_heartbeat); self.refresh_configs()
    def refresh_configs(self):
        self.combo.blockSignals(True); self.combo.clear(); self.configs = []
        server_raw_text = self.user_data.get('config', ''); srv_name = self.user_data.get('config_name', "Server Default")
        if server_raw_text:
            for line in server_raw_text.split('\n'):
                line = line.strip()
                if line.startswith("vless://"):
                    name = srv_name
                    if "#" in line:
                        try: name = unquote(line.split("#")[-1])
                        except: pass
                    self.configs.append({"name": name, "link": line, "is_server": True})
        locals = ConfigManager.load_user_configs(self.user_data.get('username'))
        for lc in locals: lc['is_server'] = False; self.configs.append(lc)
        if not self.configs:
            self.combo.addItem("Нет конфигов")
        else:
            for cfg in self.configs: self.combo.addItem(cfg['name'])
        self.combo.blockSignals(False); self.update_ip_display()
        
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
            n, l = dlg.get_data()
            if l.startswith("vless://"):
                if not n.strip():
                    if "#" in l:
                        try: n = unquote(l.split("#")[-1])
                        except: n = "Local Config"
                    else: n = "Local Config"
                ConfigManager.save_user_config(self.user_data.get('username'), n, l); self.refresh_configs(); self.combo.setCurrentIndex(self.combo.count() - 1)
            else: QMessageBox.warning(self, "Ошибка", "Некорректная ссылка")
    
    def delete_current_local_config(self):
        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self.configs): return
        if self.configs[idx].get('is_server'): QMessageBox.warning(self, "Ошибка", "Нельзя удалить конфиг сервера."); return
        if QMessageBox.question(self, 'Удаление', f"Удалить '{self.configs[idx]['name']}'?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            server_configs_count = len([c for c in self.configs if c.get('is_server')])
            ConfigManager.delete_user_config(self.user_data.get('username'), idx - server_configs_count); self.refresh_configs()

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
        except: return None

    def start_vpn(self):
        if not self.configs: 
            QMessageBox.warning(self, "Ошибка", "Нет доступных конфигураций!"); return
        self.btn.set_state("CONNECTING"); self.st.setText("CONNECTING..."); self.st.setStyleSheet(f"color:{COLORS['accent']}; margin-top:25px"); QTimer.singleShot(600, self.finish_start)
    
    def finish_start(self):
        idx = self.combo.currentIndex()
        if idx < 0: return
        cfg = self.generate_config(self.configs[idx]['link'])
        if not cfg: QMessageBox.critical(self, "Ошибка", "Ошибка генерации конфига"); self.stop_vpn(); return
        if not os.path.exists("core"): os.makedirs("core")
        with open("core/config.json", "w") as f: json.dump(cfg, f, indent=4)
        if os.path.exists(XRAY_PATH):
            try:
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.vpn_process = subprocess.Popen([XRAY_PATH, '-c', 'config.json'], cwd="core", startupinfo=si)
                set_windows_proxy(True); self.btn.set_state("ON"); self.st.setText("PROTECTED"); self.st.setStyleSheet(f"color:{COLORS['success']}; margin-top:25px"); self.heartbeat_timer.start(10000)
            except Exception as e: QMessageBox.critical(self, "Ошибка", str(e)); self.stop_vpn()
        else: QMessageBox.critical(self, "Ошибка", f"Нет {XRAY_PATH}"); self.stop_vpn()
    def send_heartbeat(self): ApiClient.send_heartbeat(self.user_data.get('username'))
    def stop_vpn(self): self.force_stop(); self.btn.set_state("OFF"); self.st.setText("DISCONNECTED"); self.st.setStyleSheet("color:#666; margin-top:25px"); self.heartbeat_timer.stop()
    def force_stop(self):
        set_windows_proxy(False)
        if self.vpn_process: self.vpn_process.terminate(); self.vpn_process = None
    def logout(self): SettingsManager.clear_auth(); self.force_stop(); self.app.switch_login()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DarkCat VPN"); self.setFixedSize(430, 700)
        self.setWindowIcon(QIcon("icon.ico"))
        self.setStyleSheet(f"background:{COLORS['bg']}"); self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.login = LoginScreen(self); self.reg = RegisterScreen(self); self.stack.addWidget(self.login); self.stack.addWidget(self.reg)
        saved = SettingsManager.load_auth()
        if saved:
            ok, d = ApiClient.login(saved['username'], saved['password'])
            if ok: self.open_dashboard(d)
    def switch(self, n): self.stack.setCurrentWidget(self.login if n == "login" else self.reg)
    def open_dashboard(self, d): self.dash = Dashboard(d, self); self.stack.addWidget(self.dash); self.stack.setCurrentWidget(self.dash)
    def open_admin_panel(self): self.admin = AdminPanel(self); self.stack.addWidget(self.admin); self.stack.setCurrentWidget(self.admin)
    def switch_back_to_dash(self): self.stack.removeWidget(self.admin); self.stack.setCurrentWidget(self.dash)
    def switch_login(self): 
        if hasattr(self, 'dash'): self.dash.force_stop(); self.stack.removeWidget(self.dash)
        self.stack.setCurrentWidget(self.login)
    def closeEvent(self, e): 
        if hasattr(self, 'dash'): self.dash.force_stop()
        e.accept()

if __name__ == "__main__":
    kill_existing_xray()
    app = QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec())