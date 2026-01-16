from flask import Flask, request, jsonify
import sqlite3
import time
import os
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix


# Загружаем настройки из файла .env
load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1
)

DB_NAME = "vpn_server.db"

# ==========================================
# 🛡️ БЕЗОПАСНАЯ КОНФИГУРАЦИЯ (Загрузка из .env)
# ==========================================

# 1. Получаем ссылку по умолчанию
DEFAULT_CONFIG = os.getenv("DEFAULT_CONFIG", "vless://placeholder")

# 2. Получаем список IP и очищаем от пробелов
raw_ips = os.getenv("ADMIN_IPS", "127.0.0.1,::1")
ALLOWED_ADMIN_IPS = [ip.strip() for ip in raw_ips.split(",") if ip.strip()]

# 3. Получаем список Админов
raw_users = os.getenv("ADMIN_USERS", "admin")
ALLOWED_ADMIN_USERS = [u.strip() for u in raw_users.split(",") if u.strip()]

print(f"Server started. Admin IPs loaded: {len(ALLOWED_ADMIN_IPS)}")
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        config_link TEXT,  
        config_name TEXT DEFAULT 'Server Default',
        is_admin INTEGER DEFAULT 0,
        last_seen REAL DEFAULT 0,
        expire_date REAL DEFAULT 0
    )''')
    
    # Миграции для поддержки старых версий базы
    try: cur.execute("ALTER TABLE users ADD COLUMN last_seen REAL DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE users ADD COLUMN config_name TEXT DEFAULT 'Server Default'")
    except: pass
    try: cur.execute("ALTER TABLE users ADD COLUMN expire_date REAL DEFAULT 0")
    except: pass
    
    # Создание/Обновление супер-админов
    for admin_name in ALLOWED_ADMIN_USERS:
        cur.execute("SELECT * FROM users WHERE username=?", (admin_name,))
        if not cur.fetchone():
            print(f" Creating super-admin account: {admin_name}")
            cur.execute("INSERT INTO users (username, password, config_link, is_admin) VALUES (?, ?, ?, ?)", 
                        (admin_name, "admin", DEFAULT_CONFIG, 1))
        else:
            # Если юзер уже есть, убеждаемся что он админ
            cur.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (admin_name,))
            
    conn.commit()
    conn.close()

def check_admin_access(req):
    if req.remote_addr not in ALLOWED_ADMIN_IPS:
        print(f"SECURITY ALERT: Blocked admin request from {req.remote_addr}")
        return False
    return True

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, username, config_link, is_admin, config_name, expire_date FROM users WHERE username=? AND password=?", 
                (data.get('username'), data.get('password')))
    user = cur.fetchone()
    
    real_ip = request.remote_addr
    print(f"--- Login attempt: {data.get('username')} from {real_ip} ---")
    
    if user:
        username = user[1]
        current_config = user[2]
        is_admin_db = user[3]
        conf_name = user[4]
        expire_ts = user[5]
        
        expired_alert = False
        
        # Проверка срока действия
        if expire_ts > 0 and time.time() > expire_ts:
            print(f"User {username} subscription EXPIRED.")
            cur.execute("UPDATE users SET config_link = ?, config_name = ?, expire_date = 0 WHERE id = ?", 
                        ("", "Expired", 0, user[0]))
            conn.commit()
            current_config = ""
            conf_name = "Expired"
            expired_alert = True

        # Проверка прав админа по IP
        final_is_admin = 0
        if is_admin_db == 1:
            if (real_ip in ALLOWED_ADMIN_IPS) and (username in ALLOWED_ADMIN_USERS):
                final_is_admin = 1
                print(" -> Admin access GRANTED")
            else:
                print(f" -> Admin access DENIED (IP {real_ip} not allowed or user not in safe list)")

        conn.close()
        return jsonify({
            "status": "success", 
            "username": username, 
            "config": current_config, 
            "config_name": conf_name,
            "is_admin": final_is_admin,
            "expired_alert": expired_alert
        })
        
    conn.close()
    return jsonify({"status": "error"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password, config_link, config_name, is_admin) VALUES (?, ?, ?, ?, ?)", 
                    (data.get('username'), data.get('password'), DEFAULT_CONFIG, 'Starter Pack', 0))
        conn.commit()
        return jsonify({"status": "success"})
    except: return jsonify({"status": "error"}), 400
    finally: conn.close()

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_seen = ? WHERE username = ?", (time.time(), data.get('username')))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# === ADMIN ROUTES ===

@app.route('/admin/users', methods=['POST'])
def get_all_users():
    if not check_admin_access(request): return jsonify({"status": "forbidden"}), 403
    data = request.json
    if not data.get('is_admin'): return jsonify({"status": "forbidden"}), 403

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, username, is_admin, last_seen, config_link, config_name, expire_date FROM users")
    users = cur.fetchall()
    conn.close()
    user_list = []
    curr = time.time()
    for u in users:
        has_conf = bool(u[4])
        conf_n = u[5] if u[5] else "Unknown"
        
        days_left = "∞"
        if u[6] > 0:
            diff = u[6] - curr
            if diff > 0:
                days_left = f"{int(diff / 86400)}d"
            else:
                days_left = "Exp"

        user_list.append({
            "id": u[0], "username": u[1], "is_admin": u[2],
            "status": "ONLINE" if (curr - u[3]) < 30 else "OFFLINE",
            "has_config": has_conf, "config_name": conf_n,
            "days_left": days_left
        })
    return jsonify({"users": user_list})

@app.route('/admin/update_config', methods=['POST'])
def update_user_config():
    if not check_admin_access(request): return jsonify({"status": "forbidden"}), 403
    data = request.json
    if not data.get('is_admin'): return jsonify({"status": "forbidden"}), 403
    
    days = data.get('days', 0)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Если 0, значит безлимит (сбрасываем таймер)
    # Если > 0, добавляем время к текущему
    expire_ts = 0 
    if days > 0:
        expire_ts = time.time() + (days * 86400)

    cur.execute("UPDATE users SET config_link = ?, config_name = ?, expire_date = ? WHERE username = ?", 
                (data.get('config'), data.get('config_name'), expire_ts, data.get('target_user')))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/admin/get_config', methods=['POST'])
def get_user_specific_config():
    if not check_admin_access(request): return jsonify({"status": "forbidden"}), 403
    data = request.json
    if not data.get('is_admin'): return jsonify({"status": "forbidden"}), 403
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT config_link, config_name, expire_date FROM users WHERE username = ?", (data.get('target_user'),))
    row = cur.fetchone()
    conn.close()
    
    config = row[0] if row and row[0] else ""
    name = row[1] if row and row[1] else ""
    expire = row[2] if row and row[2] else 0
    return jsonify({"status": "success", "config": config, "name": name, "expire": expire})

@app.route('/admin/delete_user', methods=['POST'])
def delete_user():
    if not check_admin_access(request): return jsonify({"status": "forbidden"}), 403
    data = request.json
    if not data.get('is_admin'): return jsonify({"status": "forbidden"}), 403
    
    target = data.get('target_user')
    if target in ALLOWED_ADMIN_USERS:
        return jsonify({"status": "error", "message": "Cannot delete protected admin"}), 400

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE username = ?", (target,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/admin/reset_password', methods=['POST'])
def reset_password():
    if not check_admin_access(request): return jsonify({"status": "forbidden"}), 403
    data = request.json
    if not data.get('is_admin'): return jsonify({"status": "forbidden"}), 403
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET password = ? WHERE username = ?", (data.get('new_password'), data.get('target_user')))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    init_db()
    # 0.0.0.0 обязательно, чтобы сервер был виден в сети
    app.run(host='0.0.0.0', port=5000)