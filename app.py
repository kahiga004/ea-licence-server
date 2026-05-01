from flask import Flask, request, jsonify, render_template_string
import hashlib
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor # THIS FIXES THE DICTIONARY ERROR

app = Flask(__name__)
SECRET_KEY = "123" # CHANGE THIS TO YOUR REAL SECRET KEY!

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EA License Manager</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 900px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 8px 20px rgba(0,0,0,0.05); }
        h2 { text-align: center; color: #2c3e50; margin-top: 0; }
        .card { background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 25px; border: 1px solid #e9ecef; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: 600; margin-bottom: 5px; color: #495057; font-size: 14px; }
        input[type="text"], input[type="number"] { width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        .btn-group { display: flex; gap: 10px; }
        button { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; color: white; font-size: 14px; transition: opacity 0.2s; }
        button:hover { opacity: 0.9; }
        .btn-add { background: #28a745; flex: 1; } .btn-remove { background: #dc3545; flex: 1; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #dee2e6; font-size: 14px; }
        th { background-color: #3498db; color: white; font-weight: 600; }
        tr:hover { background-color: #f1f3f5; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; color: white; }
        .badge-active { background: #28a745; } .badge-inactive { background: #dc3545; } .badge-expiring { background: #ffc107; color: #333; }
        .hwid-col { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
        .action-btn { background: #6c757d; padding: 6px 12px; font-size: 12px; text-decoration: none; color: white; border-radius: 4px; }
        .action-btn:hover { background: #5a6268; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🛡️ EA License Manager</h2>
        <div class="card">
            <div class="form-group">
                <label>Hardware ID (HWID)</label>
                <input type="text" id="hwidInput" placeholder="Paste client HWID here...">
            </div>
            <div class="form-group">
                <label>Months to Activate</label>
                <input type="number" id="monthsInput" value="1" min="1" max="24">
            </div>
            <div class="btn-group">
                <button class="btn-add" onclick="manageLicense('add')">✅ Activate / Renew</button>
                <button class="btn-remove" onclick="manageLicense('remove')">❌ Deactivate</button>
            </div>
        </div>
        <table>
            <thead><tr><th>HWID</th><th>Status</th><th>Months</th><th>Expires On</th><th>Time Remaining</th><th>Action</th></tr></thead>
            <tbody>
                {% for row in licenses %}
                <tr>
                    <td class="hwid-col" title="{{ row['hwid'] }}">{{ row['hwid'][:20] }}...</td>
                    <td>
                        {% if row['is_active'] and row['days_left'] > 7 %}<span class="badge badge-active">Active</span>
                        {% elif row['is_active'] and row['days_left'] <= 7 %}<span class="badge badge-expiring">Expiring Soon</span>
                        {% else %}<span class="badge badge-inactive">Inactive</span>{% endif %}
                    </td>
                    <td>{{ row['months_purchased'] }}</td>
                    <td>{{ row['expiry_date'] }}</td>
                    <td style="color: {% if row['days_left'] <= 7 %}red{% endif %}; font-weight: bold;">
                        {% if row['is_active'] %}{{ row['days_left'] }} Days{% else %}N/A{% endif %}
                    </td>
                    <td><a href="/admin/delete/{{ row['hwid'] }}" class="action-btn" onclick="return confirm('Permanently delete?')">Delete</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <script>
        function manageLicense(action) {
            var hwid = document.getElementById('hwidInput').value.trim();
            var months = document.getElementById('monthsInput').value;
            if(!hwid) { alert("Please enter a HWID!"); return; }
            fetch('/admin/' + action, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hwid: hwid, months: parseInt(months) })
            }).then(r => r.json()).then(d => { alert(d.message); if(d.success) location.reload(); });
        }
    </script>
</body>
</html>
"""

# ==========================================
# POSTGRESQL DATABASE CONNECTION
# ==========================================
def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS licenses (
                    hwid TEXT PRIMARY KEY,
                    is_active BOOLEAN DEFAULT TRUE,
                    months_purchased INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    cursor.close()
    conn.close()

# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def dashboard():
    conn = get_db()
    # RealDictCursor makes rows act like dictionaries (Fixes the crash)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM licenses ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    licenses_list = []
    for row in rows:
        row_dict = dict(row) 
        if row_dict['created_at']:
            created_dt = row_dict['created_at'].strftime("%Y-%m-%d %H:%M:%S")
            created_dt = datetime.strptime(created_dt, "%Y-%m-%d %H:%M:%S")
            expiry_dt = created_dt + timedelta(days=30 * row_dict['months_purchased'])
            days_left = (expiry_dt - datetime.now()).days
            row_dict['expiry_date'] = expiry_dt.strftime("%Y-%m-%d")
            row_dict['days_left'] = days_left
            
            if days_left <= 0 and row_dict['is_active']:
                cursor.execute("UPDATE licenses SET is_active = FALSE WHERE hwid = %s", (row_dict['hwid'],))
                row_dict['is_active'] = False
        else:
            row_dict['expiry_date'] = "N/A"
            row_dict['days_left'] = 0
        licenses_list.append(row_dict)
    
    conn.commit()
    cursor.close()
    conn.close()
    return render_template_string(DASHBOARD_HTML, licenses=licenses_list)

@app.route('/admin/add', methods=['POST'])
def add_license():
    data = request.json
    hwid = data.get('hwid', '').strip()
    months = data.get('months', 1)
    if not hwid: return jsonify({"success": False, "message": "Invalid HWID"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO licenses (hwid, is_active, months_purchased, created_at) VALUES (%s, TRUE, %s, CURRENT_TIMESTAMP) ON CONFLICT (hwid) DO UPDATE SET is_active = TRUE, months_purchased = %s, created_at = CURRENT_TIMESTAMP", (hwid, months, months))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"License activated for {months} month(s)!"})

@app.route('/admin/remove', methods=['POST'])
def remove_license():
    data = request.json
    hwid = data.get('hwid', '').strip()
    if not hwid: return jsonify({"success": False, "message": "Invalid HWID"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE licenses SET is_active = FALSE WHERE hwid = %s", (hwid,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "License deactivated!"})

@app.route('/admin/delete/<hwid>')
def delete_license(hwid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM licenses WHERE hwid = %s", (hwid,))
    conn.commit()
    cursor.close()
    conn.close()
    return "Deleted"

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
    # Use RealDictCursor here too so we can use column names
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT is_active, created_at, months_purchased FROM licenses WHERE hwid = %s", (hwid,))
    user = cursor.fetchone()
    
    if user and user['is_active']:
        created_dt = user['created_at'].strftime("%Y-%m-%d %H:%M:%S")
        created_dt = datetime.strptime(created_dt, "%Y-%m-%d %H:%M:%S")
        expiry_dt = created_dt + timedelta(days=30 * user['months_purchased'])
        
        if datetime.now() < expiry_dt:
            cursor.close()
            conn.close()
            return jsonify({"status": "success", "is_active": True})
        else:
            cursor.execute("UPDATE licenses SET is_active = FALSE WHERE hwid = %s", (hwid,))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({"status": "expired", "is_active": False})
            
    cursor.close()
    conn.close()
    return jsonify({"status": "failed", "is_active": False})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    init_db()
    app.run(host='0.0.0.0', port=port, debug=False)
