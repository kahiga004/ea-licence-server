from flask import Flask, request, jsonify, render_template_string
import sqlite3, hashlib, os

app = Flask(__name__)
SECRET_KEY = "123" # MUST MATCH MQL5
DB_NAME = "licenses.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS licenses (hwid TEXT PRIMARY KEY, is_active BOOLEAN DEFAULT 1)''')
    conn.commit(); conn.close()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

DASHBOARD_HTML = """<!DOCTYPE html><html><head><title>Manager</title></head><body><h2>License Manager</h2><form action="/admin/add" method="POST"><input type="text" name="hwid" style="width:300px" placeholder="Paste HWID"><button>Activate</button></form></body></html>"""

@app.route('/')
def dashboard(): return render_template_string(DASHBOARD_HTML)

@app.route('/admin/add', methods=['POST'])
def add_license():
    hwid = request.form.get('hwid', '').strip()
    if hwid:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO licenses (hwid, is_active) VALUES (?, 1)", (hwid,))
        conn.commit(); conn.close()
    return "Activated!"

@app.route('/api/validate', methods=['POST'])
def validate():
    data = request.json
    hwid = str(data.get('hwid', '')).strip()
    timestamp = str(data.get('timestamp', '')).strip()
    token = data.get('token', '')

    raw_string = f"{timestamp}{hwid}{SECRET_KEY}"
    expected_token = hashlib.sha256(raw_string.encode()).hexdigest()
    
    if expected_token != token:
        return jsonify({"status": "failed", "is_active": False})

    conn = get_db()
    user = conn.execute("SELECT is_active FROM licenses WHERE hwid = ?", (hwid,)).fetchone()
    conn.close()

    if user and user['is_active']:
        return jsonify({"status": "success", "is_active": True})
        
    return jsonify({"status": "failed", "is_active": False})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    init_db()
    app.run(host='0.0.0.0', port=port, debug=False)
