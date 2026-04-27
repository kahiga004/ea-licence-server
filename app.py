from flask import Flask, request, jsonify, render_template_string
import sqlite3
import hashlib
import time

app = Flask(__name__)

SECRET_KEY = "123"  # MATCH THIS IN C++
DB_NAME = "licenses.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS licenses (hwid TEXT PRIMARY KEY, is_active BOOLEAN DEFAULT 1)''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head><title>EA License Manager</title></head>
<body>
    <h2>EA License Manager</h2>
    <form action="/admin/add" method="POST">
        <input type="text" name="hwid" placeholder="Paste HWID here" style="width:300px">
        <button type="submit">Activate</button>
    </form>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/admin/add', methods=['POST'])
def add_license():
    hwid = request.form.get('hwid', '').strip()
    if hwid:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO licenses (hwid, is_active) VALUES (?, 1)", (hwid,))
        conn.commit()
        conn.close()
    return "Activated!"

@app.route('/api/validate', methods=['POST'])
def validate():
    data = request.json
    hwid = data.get('hwid', '')
    timestamp = data.get('timestamp', '')
    token = data.get('token', '')

    print("=== NEW REQUEST RECEIVED ===")
    print("HWID: " + hwid)
    
    raw_string = f"{timestamp}{hwid}{SECRET_KEY}"
    print("Hashing: " + raw_string)
    expected_token = hashlib.sha256(raw_string.encode()).hexdigest()
    
    print("Expected Token: " + expected_token)
    print("Received Token: " + token)

    if expected_token != token:
        print("RESULT: TOKEN MISMATCH!")
        return jsonify({"status": "failed", "is_active": False})

    conn = get_db()
    user = conn.execute("SELECT is_active FROM licenses WHERE hwid = ?", (hwid,)).fetchone()
    conn.close()

    if user and user['is_active']:
        print("RESULT: SUCCESS!")
        return jsonify({"status": "success", "is_active": True})
    else:
        print("RESULT: NOT IN DATABASE!")
        return jsonify({"status": "failed", "is_active": False})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    init_db()
    app.run(host='0.0.0.0', port=port, debug=False)
