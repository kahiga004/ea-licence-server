from flask import Flask, request, jsonify, render_template_string
import sqlite3
import hashlib
import time

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
# WARNING: This MUST match the exact secret key in your C++ DLL!
SECRET_KEY = "123" 
DB_NAME = "licenses.db"

# ==========================================
# DATABASE SETUP
# ==========================================
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

# ==========================================
# HTML DASHBOARD (Single Page)
# ==========================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>EA License Manager</title>
    <style>
        body { font-family: Arial; background: #f4f4f9; padding: 20px; }
        .container { max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0px 0px 10px rgba(0,0,0,0.1); }
        h2 { text-align: center; color: #333; }
        textarea { width: 100%; height: 100px; margin-bottom: 10px; padding: 10px; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 10px 15px; margin-right: 10px; border: none; border-radius: 4px; cursor: pointer; color: white; }
        .btn-add { background: #28a745; } .btn-remove { background: #dc3545; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
        th { background-color: #007bff; color: white; }
        .status-active { color: green; font-weight: bold; } .status-inactive { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <h2>EA License Manager</h2>
        <p>Paste Hardware IDs (one per line) to manage licenses:</p>
        <textarea id="hwidBox" placeholder="Example: BFEBFBFF000906EA_AWV8F32..."></textarea><br>
        <button class="btn-add" onclick="manageLicense('add')">Activate License</button>
        <button class="btn-remove" onclick="manageLicense('remove')">Deactivate License</button>
        
        <table>
            <tr><th>HWID (First 20 chars...)</th><th>Status</th></tr>
            {% for row in licenses %}
            <tr>
                <td title="{{ row['hwid'] }}">{{ row['hwid'][:20] }}...</td>
                <td class="{{ 'status-active' if row['is_active'] else 'status-inactive' }}">
                    {{ 'Active' if row['is_active'] else 'Inactive' }}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    <script>
        function manageLicense(action) {
            var hwids = document.getElementById('hwidBox').value.trim().split('\\n');
            fetch('/admin/' + action, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hwids: hwids })
            }).then(response => response.json()).then(data => {
                alert(data.message);
                location.reload();
            });
        }
    </script>
</body>
</html>
"""

# ==========================================
# API ROUTES
# ==========================================
@app.route('/')
def dashboard():
    conn = get_db()
    licenses = conn.execute("SELECT * FROM licenses").fetchall()
    conn.close()
    return render_template_string(DASHBOARD_HTML, licenses=licenses)

@app.route('/admin/add', methods=['POST'])
def add_license():
    data = request.json
    conn = get_db()
    for hwid in data.get('hwids', []):
        hwid = hwid.strip()
        if hwid:
            conn.execute("INSERT OR REPLACE INTO licenses (hwid, is_active) VALUES (?, 1)", (hwid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Licenses Activated!"})

@app.route('/admin/remove', methods=['POST'])
def remove_license():
    data = request.json
    conn = get_db()
    for hwid in data.get('hwids', []):
        hwid = hwid.strip()
        if hwid:
            conn.execute("UPDATE licenses SET is_active = 0 WHERE hwid = ?", (hwid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Licenses Deactivated!"})

# THE ENDPOINT YOUR DLL CALLS
@app.route('/api/validate', methods=['POST'])
def validate():
    data = request.json
    hwid = data.get('hwid', '')
    timestamp = data.get('timestamp', '')
    token = data.get('token', '')
    print(f"Received HWID: {hwid}")
    print(f"Received Timestamp: {timestamp}")
    print(f"Received Token: {token}")
    raw_string = f"{timestamp}{hwid}{SECRET_KEY}"
    print(f"Python is hashing: {raw_string}")

    # 1. Check Timestamp (Reject if older than 60 seconds to prevent replay attacks)
    try:
        req_time = int(timestamp)
        if abs(time.time() - req_time) > 60:
            return jsonify({"status": "error", "is_active": False})
    except:
        return jsonify({"status": "error", "is_active": False})

    # 2. Cryptographic Handshake Verification
    raw_string = f"{timestamp}{hwid}{SECRET_KEY}"
    expected_token = hashlib.sha256(raw_string.encode()).hexdigest()
    
    if expected_token != token:
        return jsonify({"status": "error", "is_active": False})

    # 3. Check Database
    conn = get_db()
    user = conn.execute("SELECT is_active FROM licenses WHERE hwid = ?", (hwid,)).fetchone()
    conn.close()

    if user and user['is_active']:
        return jsonify({"status": "success", "is_active": True})
    else:
        return jsonify({"status": "failed", "is_active": False})

if __name__ == '__main__':
    init_db()
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
