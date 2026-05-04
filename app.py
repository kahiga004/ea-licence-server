from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
import hashlib
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "default_secret_key")
SECRET_KEY = os.environ.get("EA_SECRET_KEY", "anom") # Your EA hash key
MASTER_USERNAME = os.environ.get("MASTER_USER", "admin")
MASTER_PASSWORD = os.environ.get("MASTER_PASS", "changeme")

def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # Create Partners Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS partners (
                    id SERIAL PRIMARY KEY,
                    business_name TEXT UNIQUE NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    max_clients INTEGER DEFAULT 50,
                    is_active BOOLEAN DEFAULT TRUE
                )''')
    # Create Licenses Table (Now includes partner_id for linking)
    cursor.execute('''CREATE TABLE IF NOT EXISTS licenses (
                    id SERIAL PRIMARY KEY,
                    hwid TEXT UNIQUE NOT NULL,
                    partner_id INTEGER REFERENCES partners(id) ON DELETE CASCADE,
                    is_active BOOLEAN DEFAULT TRUE,
                    months_purchased INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    cursor.close()
    conn.close()

# ==========================================
# HTML TEMPLATES
# ==========================================
LOGIN_HTML = """
<!DOCTYPE html><html><head><title>System Login</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;}
.box{background:#fff;padding:40px;border-radius:10px;box-shadow:0 4px 15px rgba(0,0,0,0.1);width:350px;text-align:center;}
h2{color:#2c3e50;margin-top:0;}input{width:100%;padding:10px;margin:10px 0;border:1px solid #ccc;border-radius:5px;box-sizing:border-box;}
button{width:100%;padding:10px;background:#3498db;color:white;border:none;border-radius:5px;cursor:pointer;font-size:16px;}
button:hover{background:#2980b9;}</style></head><body>
<div class="box"><h2>🔐 System Login</h2>
{% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
<form method="POST"><input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button></form></div></body></html>
"""

MASTER_DASHBOARD_HTML = """
<!DOCTYPE html><html><head><title>Master Admin</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:40px;}
.header{text-align:center;margin-bottom:40px;} h1{color:#2c3e50;}
.container{display:flex;justify-content:center;gap:40px;}
.card{background:#fff;padding:40px;border-radius:10px;box-shadow:0 4px 15px rgba(0,0,0,0.1);width:400px;text-align:center;cursor:pointer;transition:transform 0.2s;}
.card:hover{transform:translateY(-5px);} h2{color:#3498db;} p{color:#7f8c8d;}
.btn{display:inline-block;margin-top:20px;padding:12px 30px;background:#3498db;color:white;text-decoration:none;border-radius:5px;font-weight:bold;}</style></head><body>
<div class="header"><h1>🛡️ SaaS Master Control</h1><p>Welcome back, God Mode.</p></div>
<div class="container">
<a href="/retail" style="text-decoration:none;"><div class="card"><h2>👤 Retail Clients</h2><p>Manage direct-to-consumer licenses.</p></div></a>
<a href="/partners" style="text-decoration:none;"><div class="card"><h2>🏢 B2B Partners</h2><p>Manage brokers, prop firms, and influencers.</p></div></a>
</div></body></html>
"""

PARTNER_DASHBOARD_HTML = """
<!DOCTYPE html><html><head><title>{{ name }} Dashboard</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:20px;color:#333;}
.container{max-width:900px;margin:20px auto;background:#fff;padding:30px;border-radius:12px;box-shadow:0 8px 20px rgba(0,0,0,0.05);}
h2{text-align:center;color:#2c3e50;} .card{background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:25px;border:1px solid #e9ecef;}
.form-group{margin-bottom:15px;} label{display:block;font-weight:600;margin-bottom:5px;color:#495057;font-size:14px;}
input[type="text"],input[type="number"]{width:100%;padding:10px;border:1px solid #ced4da;border-radius:6px;box-sizing:border-box;}
.btn-group{display:flex;gap:10px;} button{padding:10px 20px;border:none;border-radius:6px;cursor:pointer;font-weight:600;color:white;}
.btn-add{background:#28a745;flex:1;} .btn-remove{background:#dc3545;flex:1;}
table{width:100%;border-collapse:collapse;margin-top:20px;} th,td{padding:12px 15px;text-align:left;border-bottom:1px solid #dee2e6;}
th{background-color:#3498db;color:white;} .badge{padding:4px 8px;border-radius:4px;font-size:12px;font-weight:bold;color:white;}
.badge-active{background:#28a745;} .badge-inactive{background:#dc3545;} .badge-expiring{background:#ffc107;color:#333;}
.hwid-col{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;}</style></head><body>
<div class="container"><h2>🏢 {{ name }} - License Manager</h2>
<p style="text-align:center;color:#7f8c8d;">Active Clients: <b>{{ client_count }}</b> / {{ max_clients }} Limit</p>
<div class="card"><div class="form-group"><label>Hardware ID (HWID)</label><input type="text" id="hwidInput" placeholder="Paste client HWID here..."></div>
<div class="form-group"><label>Months to Activate</label><input type="number" id="monthsInput" value="1" min="1" max="24"></div>
<div class="btn-group"><button class="btn-add" onclick="manageLicense('add')">✅ Activate</button><button class="btn-remove" onclick="manageLicense('remove')">❌ Deactivate</button></div></div>
<table><thead><tr><th>HWID</th><th>Status</th><th>Expires On</th><th>Days Left</th></tr></thead><tbody>
{% for row in licenses %}
<tr><td class="hwid-col" title="{{ row['hwid'] }}">{{ row['hwid'][:20] }}...</td>
<td>{% if row['is_active'] and row['days_left'] > 7 %}<span class="badge badge-active">Active</span>
{% elif row['is_active'] and row['days_left'] <= 7 %}<span class="badge badge-expiring">Expiring</span>
{% else %}<span class="badge badge-inactive">Inactive</span>{% endif %}</td>
<td>{{ row['expiry_date'] }}</td>
<td style="color:{% if row['days_left'] <= 7 %}red{% endif %};font-weight:bold;">{% if row['is_active'] %}{{ row['days_left'] }} Days{% else %}N/A{% endif %}</td></tr>
{% endfor %}</tbody></table></div>
<script>
function manageLicense(action){
    var hwid = document.getElementById('hwidInput').value.trim();
    var months = document.getElementById("monthsInput").value;
    if(!hwid){alert("Enter HWID!");return;}
    
    // Added '?v=' to bust browser cache & Added r.ok to catch silent network/session errors
    fetch('/partner/api/'+action + '?v=' + new Date().getTime(), {
        method:'POST',
        headers:{'Content-Type':'application/json'}, 
        body: JSON.stringify({hwid:hwid, months:parseInt(months)})
    })
    .then(r => {
        if(!r.ok) { alert("Network error! Your session may have expired. Please log out and log back in."); return; }
        return r.json();
    })
    .then(d => {
        alert(d.message); 
        if(d.success) location.reload();
    })
    .catch(error => {
        alert("JavaScript Error: " + error.message);
    });
}

function deleteClient(hwid){
    if(confirm('Delete this client permanently?')){
        fetch('/partner/api/delete/'+hwid + '?v=' + new Date().getTime(), {method:'DELETE'})
        .then(r => {
            if(!r.ok) { alert("Network error!"); return r.text(); }
            return r.json();
        })
        .then(d => {
            alert(d.message); 
            if(d.success) location.reload();
        })
        .catch(error => alert("JavaScript Error: " + error.message);
    }
</script>
</body></html>
"""

# (Retail HTML is same as before, shortened for space)
RETAIL_DASHBOARD_HTML = """
<!DOCTYPE html><html><head><title>Retail Manager</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:20px;color:#333;}
.container{max-width:900px;margin:20px auto;background:#fff;padding:30px;border-radius:12px;box-shadow:0 8px 20px rgba(0,0,0,0.05);}
h2{text-align:center;color:#2c3e50;} .card{background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:25px;border:1px solid #e9ecef;}
.form-group{margin-bottom:15px;} label{display:block;font-weight:600;margin-bottom:5px;color:#495057;font-size:14px;}
input[type="text"],input[type="number"]{width:100%;padding:10px;border:1px solid #ced4da;border-radius:6px;box-sizing:border-box;}
.btn-group{display:flex;gap:10px;} button{padding:10px 20px;border:none;border-radius:6px;cursor:pointer;font-weight:600;color:white;}
.btn-add{background:#28a745;flex:1;} .btn-remove{background:#dc3545;flex:1;}
table{width:100%;border-collapse:collapse;margin-top:20px;} th,td{padding:12px 15px;text-align:left;border-bottom:1px solid #dee2e6;}
th{background-color:#2ecc71;color:white;} .badge{padding:4px 8px;border-radius:4px;font-size:12px;font-weight:bold;color:white;}
.badge-active{background:#28a745;} .badge-inactive{background:#dc3545;} .badge-expiring{background:#ffc107;color:#333;}
.hwid-col{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;}</style></head><body>
<div class="container"><h2>👤 Direct Retail Clients</h2>
<div class="card"><div class="form-group"><label>Hardware ID (HWID)</label><input type="text" id="hwidInput" placeholder="Paste client HWID here..."></div>
<div class="form-group"><label>Months to Activate</label><input type="number" id="monthsInput" value="1" min="1" max="24"></div>
<div class="btn-group"><button class="btn-add" onclick="manageLicense('add')">✅ Activate</button><button class="btn-remove" onclick="manageLicense('remove')">❌ Deactivate</button></div></div>
<table><thead><tr><th>HWID</th><th>Status</th><th>Expires On</th><th>Days Left</th><th>Action</th></tr></thead><tbody>
{% for row in licenses %}
<tr><td class="hwid-col" title="{{ row['hwid'] }}">{{ row['hwid'][:20] }}...</td>
<td>{% if row['is_active'] and row['days_left'] > 7 %}<span class="badge badge-active">Active</span>{% elif row['is_active'] and row['days_left'] <= 7 %}<span class="badge badge-expiring">Expiring</span>{% else %}<span class="badge badge-inactive">Inactive</span>{% endif %}</td>
<td>{{ row['expiry_date'] }}</td><td style="color:{% if row['days_left'] <= 7 %}red{% endif %};font-weight:bold;">{% if row['is_active'] %}{{ row['days_left'] }} Days{% else %}N/A{% endif %}</td>
<td><a href="/retail/delete/{{ row['hwid'] }}" class="badge badge-inactive" style="text-decoration:none;" onclick="return confirm('Delete?')">Delete</a></td></tr>
{% endfor %}</tbody></table></div>
<script>
function manageLicense(action){var hwid=document.getElementById('hwidInput').value.trim();var months=document.getElementById('monthsInput').value;
if(!hwid){alert("Enter HWID!");return;}
fetch('/retail/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hwid:hwid,months:parseInt(months)})})
.then(r=>r.json()).then(d=>{alert(d.message);if(d.success)location.reload();});}
</script></body></html>
"""

# ==========================================
# ROUTES: AUTH & MASTER DASHBOARD
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == MASTER_USERNAME and password == MASTER_PASSWORD:
            session['role'] = 'master'
            return redirect(url_for('master_dashboard'))
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM partners WHERE username = %s", (username,))
        partner = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if partner and check_password_hash(partner['password_hash'], password):
            session['role'] = 'partner'
            session['partner_id'] = partner['id']
            return redirect(url_for('partner_dashboard'))
            
        return render_template_string(LOGIN_HTML, error="Invalid username or password")
    return render_template_string(LOGIN_HTML, error="")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

def login_required(role):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

@app.route('/master')
@login_required('master')
def master_dashboard():
    return render_template_string(MASTER_DASHBOARD_HTML)

# ==========================================
# ROUTES: RETAIL CLIENTS (Master Only)
# ==========================================
@app.route('/retail')
@login_required('master')
def retail_dashboard():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM licenses WHERE partner_id IS NULL ORDER BY created_at DESC")
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
                cursor.execute("UPDATE licenses SET is_active = FALSE WHERE id = %s", (row_dict['id'],))
                row_dict['is_active'] = False
        else:
            row_dict['expiry_date'] = "N/A"
            row_dict['days_left'] = 0
        licenses_list.append(row_dict)
    conn.commit()
    cursor.close()
    conn.close()
    return render_template_string(RETAIL_DASHBOARD_HTML, licenses=licenses_list)

@app.route('/retail/api/<action>', methods=['POST'])
@login_required('master')
def retail_api(action):
    data = request.json
    hwid = data.get('hwid', '').strip()
    months = data.get('months', 1)
    if not hwid: return jsonify({"success": False, "message": "Invalid HWID"})
    conn = get_db()
    cursor = conn.cursor()
    if action == 'add':
        cursor.execute("INSERT INTO licenses (hwid, partner_id, is_active, months_purchased, created_at) VALUES (%s, NULL, TRUE, %s, CURRENT_TIMESTAMP) ON CONFLICT (hwid) DO UPDATE SET is_active = TRUE, months_purchased = %s, created_at = CURRENT_TIMESTAMP, partner_id = NULL", (hwid, months, months))
    elif action == 'remove':
        cursor.execute("UPDATE licenses SET is_active = false WHERE hwid = %s AND partner_id IS NULL", (hwid,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Retail client updated!"})

@app.route('/retail/delete/<hwid>')
@login_required('master')
def retail_delete(hwid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM licenses WHERE hwid = %s AND partner_id IS NULL", (hwid,))
    conn.commit()
    cursor.close()
    conn.close()
    return "Deleted"

# ==========================================
# ROUTES: B2B PARTNERS (Master Only)
# ==========================================
@app.route('/partners')
@login_required('master')
def partners_dashboard():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get partners and their live client count
    cursor.execute("""
        SELECT p.*, 
               (SELECT COUNT(id) FROM licenses WHERE partner_id = p.id) as client_count 
        FROM partners p 
        ORDER BY p.business_name
    """)
    partners = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template_string("""
    <html><head><title>Manage Partners</title>
    <style>body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;padding:20px;} .container{max-width:850px;margin:auto;background:#fff;padding:30px;border-radius:12px;box-shadow:0 8px 20px rgba(0,0,0,0.05);}
    h2{text-align:center;color:#2c3e50;} .card{background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:20px;border:1px solid #e9ecef;}
    .form-group{margin-bottom:10px;} label{display:block;font-weight:600;margin-bottom:5px;font-size:14px;}
    input{width:100%;padding:8px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box;}
    button{padding:10px 20px;border:none;border-radius:4px;cursor:pointer;color:white;font-weight:bold;}
    .btn-add{background:#3498db;} .btn-nuke{background:#e74c3c;}
    table{width:100%;border-collapse:collapse;margin-top:20px;} th,td{padding:10px;text-align:left;border-bottom:1px solid #dee2e6;}
    th{background-color:#3498db;color:white;} .badge{padding:4px 8px;border-radius:4px;font-size:12px;font-weight:bold;color:white;}
    .badge-active{background:#28a745;} .badge-inactive{background:#dc3545;}</style></head><body>
    <div class="container"><h2>🏢 B2B Partners</h2>
    <div class="card"><div class="form-group"><label>Business Name</label><input type="text" id="bname" placeholder="e.g. QuantFX Capital"></div>
    <div class="form-group"><label>Max Clients Allowed</label><input type="number" id="mclients" value="50"></div>
    <button class="btn-add" onclick="addPartner()">Create Partner</button></div>
    
    <table><thead><tr><th>Business Name</th><th>Login Username</th><th>Clients Used</th><th>Status</th><th>Actions</th></tr></thead><tbody>
    {% for p in partners %}<tr>
    <td><b>{{ p['business_name'] }}</b></td>
    <td>{{ p['username'] }}</td>
    <td>{{ p['client_count'] }} / {{ p['max_clients'] }}</td>
    <td>{% if p['is_active'] %}<span class="badge badge-active">Active</span>{% else %}<span class="badge badge-inactive">NUKED</span>{% endif %}</td>
    <!-- THIS IS WHERE THE NEW BUTTON IS -->
    <td>
        {% if p['is_active'] %}<a href="/master/view_partner/{{ p['username'] }}" style="text-decoration:none;padding:6px 12px;background:#3498db;color:white;border-radius:4px;font-size:12px;margin-right:5px;">View Clients</a>{% endif %}
        {% if p['is_active'] %}<button class="btn-nuke" onclick="nukePartner('{{ p['username'] }}')">NUKE</button>{% endif %}
    </td>
    </tr>{% endfor %}
    </tbody></table></div>
    
    <script>
    function addPartner(){var n=document.getElementById('bname').value;var m=document.getElementById('mclients').value;if(!n){alert('Enter name');return;}
    fetch('/partners/api/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,max:m})}).then(r=>r.json()).then(d=>{alert(d.message);if(d.success)location.reload();});}
    function nukePartner(u){if(confirm('NUKE this partner? ALL their clients will instantly shut down!')){fetch('/partners/api/nuke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u})}).then(r=>r.json()).then(d=>{alert(d.message);location.reload();});}}
    </script></body></html>
    """, partners=partners)
    
@app.route('/partners/api/add', methods=['POST'])
@login_required('master')
def add_partner():
    data = request.json
    name = data.get('name', '').strip()
    max_c = data.get('max', 50)
    if not name: return jsonify({"success": False, "message": "Enter name"})
    
    # Create username from business name
    username = name.lower().replace(" ", "_").replace(".", "")
    plain_pass = os.urandom(8).hex() # Auto-generate secure password
    pass_hash = generate_password_hash(plain_pass)
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO partners (business_name, username, password_hash, max_clients) VALUES (%s, %s, %s, %s) RETURNING password_hash", (name, username, pass_hash, max_c))
        # We have to return the plain text password exactly once when created!
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Name already exists"})
    
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Partner Created!\nUsername: {username}\nPassword: {plain_pass}\n(Save this, you won't see it again!)"})

@app.route('/partners/api/nuke', methods=['POST'])
@login_required('master')
def nuke_partner():
    data = request.json
    username = data.get('username')
    conn = get_db()
    cursor = conn.cursor()
    # THE NUCLEAR OPTION: Turn off partner, AND instantly deactivate all their clients
    cursor.execute("UPDATE licenses SET is_active = FALSE WHERE partner_id = (SELECT id FROM partners WHERE username = %s)", (username,))
    cursor.execute("UPDATE partners SET is_active = FALSE WHERE username = %s", (username,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Partner and ALL their clients have been shut down."})

# ==========================================
# ROUTES: PARTNER DASHBOARD (B2B Access)
# ==========================================
@app.route('/partner/dashboard')
@login_required('partner')
def partner_dashboard():
    pid = session['partner_id']
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get Partner Info
    cursor.execute("SELECT business_name, max_clients FROM partners WHERE id = %s", (pid,))
    partner = cursor.fetchone()
    if not partner: return redirect(url_for('login'))
    
    # Get Their Clients
    cursor.execute("SELECT * FROM licenses WHERE partner_id = %s ORDER BY created_at DESC", (pid,))
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
                cursor.execute("UPDATE licenses SET is_active = FALSE WHERE id = %s", (row_dict['id'],))
                row_dict['is_active'] = False
        else:
            row_dict['expiry_date'] = "N/A"
            row_dict['days_left'] = 0
        licenses_list.append(row_dict)
        
    # Count clients
    cursor.execute("SELECT COUNT(id) FROM licenses WHERE partner_id = %s", (pid,))
    client_count = cursor.fetchone()['count']
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return render_template_string(PARTNER_DASHBOARD_HTML, name=partner['business_name'], licenses=licenses_list, max_clients=partner['max_clients'], client_count=client_count)

@app.route('/partner/api/<action>', methods=['POST'])
@login_required('partner')
def partner_api(action):
    pid = int(session['partner_id'])
    data = request.json
    hwid = data.get('hwid', '').strip()
    months = data.get('months', 1)
    
    if not hwid: 
        return jsonify({"success": False, "message": "Invalid HWID"})
        
    conn = get_db()
    cursor = conn.cursor()
    
    # STEP 1: Check if HWID exists ANYWHERE in the database (Prevents stealing retail clients)
    cursor.execute("SELECT partner_id, is_active FROM licenses WHERE hwid = %s", (hwid,))
    existing = cursor.fetchone()
    
    if existing:
        cursor.close()
        conn.close()
        # If it belongs to THIS partner already, tell them to use Renew
        if existing['partner_id'] == pid:
            return jsonify({"success": False, "message": "HWID already exists under your account! Use Renew to add more time."})
        # If it belongs to someone else (Retail or another Partner), block it completely
        else:
            return jsonify({"success": False, "message": "HWID is already registered under another account."})

    # STEP 2: Clean Insert (No complex SQL conflicts)
    try:
        cursor.execute("INSERT INTO licenses (hwid, partner_id, is_active, months_purchased, created_at) VALUES (%s, %s, TRUE, %s, CURRENT_TIMESTAMP)", (hwid, pid, months))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Client activated successfully!"})
    except Exception as e:
        # If it still fails, print the EXACT database error so we aren't guessing anymore
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": f"Database Error: {str(e)}"})

@app.route('/partner/api/delete/<hwid>', methods=['DELETE'])
@login_required('partner')
def partner_delete_client(hwid):
    pid = session['partner_id']
    conn = get_db()
    cursor = conn.cursor()
    # Security: Ensures the partner can ONLY delete their own clients, not someone else's
    cursor.execute("DELETE FROM licenses WHERE hwid = %s AND partner_id = %s", (hwid, pid))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Client deleted and freed up a slot!"})

# ==========================================
# ROUTES: EA VALIDATION API (The Core Logic)
# ==========================================
@app.route('/api/validate', methods=['POST'])
def validate():
    try:
        data = request.json
        hwid = str(data.get('hwid', '')).strip()
        timestamp = str(data.get('timestamp', '')).strip()
        token = data.get('token', '')

        # 1. Cryptographic Check
        raw_string = f"{timestamp}{hwid}{SECRET_KEY}"
        expected_token = hashlib.sha256(raw_string.encode()).hexdigest()
        if expected_token != token:
            return jsonify({"status": "failed", "is_active": False})

        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT l.is_active, l.created_at, l.months_purchased, p.is_active as partner_active FROM licenses l LEFT JOIN partners p ON l.partner_id = p.id WHERE l.hwid = %s", (hwid,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close(); conn.close()
            return jsonify({"status": "failed", "is_active": False})

        # 2. THE NUCLEAR CHECK: If they belong to a B2B client, is that B2B client active?
        if user['partner_active'] == False:
            cursor.close(); conn.close()
            return jsonify({"status": "failed", "is_active": False})

        # 3. Time Check
        if user['is_active'] and user['created_at']:
            created_dt = user['created_at'].strftime("%Y-%m-%d %H:%M:%S")
            created_dt = datetime.strptime(created_dt, "%Y-%m-%d %H:%M:%S")
            expiry_dt = created_dt + timedelta(days=30 * user['months_purchased'])
            
            if datetime.now() < expiry_dt:
                cursor.close(); conn.close()
                return jsonify({"status": "success", "is_active": True})
            else:
                cursor.execute("UPDATE licenses SET is_active = FALSE WHERE hwid = %s", (hwid,))
                conn.commit()
                
        cursor.close()
        conn.close()
        return jsonify({"status": "failed", "is_active": False})
        
    except Exception as e:
        # If the database is broken, print the exact error to the EA so we know what's wrong!
        return jsonify({"status": "error", "message": str(e)})

@app.route('/master/view_partner/<username>')
@login_required('master')
def master_view_partner(username):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT id, business_name FROM partners WHERE LOWER(username) = LOWER(%s)", (username,))
    partner = cursor.fetchone()
    if not partner: 
        cursor.close()
        conn.close()
        return redirect(url_for('partners_dashboard'))
    
    pid = partner['id']
    
    # THIS IS THE LINE THAT WAS MISSING:
    cursor.execute("SELECT * FROM licenses WHERE partner_id = %s ORDER BY created_at DESC", (pid,))
    rows = cursor.fetchall()
    
    # Process the rows
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
                cursor.execute("UPDATE licenses SET is_active = FALSE WHERE id = %s", (row_dict['id'],))
                row_dict['is_active'] = False
        else:
            row_dict['expiry_date'] = "N/A"
            row_dict['days_left'] = 0
        licenses_list.append(row_dict)
        
    conn.commit()
    cursor.close()
    conn.close()
    
    return render_template_string("""
    <html><head><title>Partner Clients</title>
    <style>body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:20px;} .container{max-width:900px;margin:20px auto;background:#fff;padding:30px;border-radius:12px;box-shadow:0 8px 20px rgba(0,0,0,0.05);}
    h2{text-align:center;color:#2c3e50;} .badge{padding:4px 8px;border-radius:4px;font-size:12px;font-weight:bold;color:white;}
    .badge-active{background:#28a745;} .badge-inactive{background:#dc3545;} .badge-expiring{background:#ffc107;color:#333;}
    .back-link{display:inline-block;margin-bottom:20px;text-decoration:none;color:#3498db;font-weight:bold;}
    table{width:100%;border-collapse:collapse;margin-top:20px;} th,td{padding:12px 15px;text-align:left;border-bottom:1px solid #dee2e6;}
    th{background-color:#3498db;color:white;} .hwid-col{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;}</style></head><body>
    <div class="container">
    <a href="/partners" class="back-link">← Back to Partners</a>
    <h2>{{ partner['business_name'] }} - Client List</h2>
    
    {% if licenses_list|length == 0 %}
       <p style="text-align:center; color:#999;">This partner currently has 0 active clients in the database.</p>
    {% endif %}
    
    <table><thead><tr><th>HWID</th><th>Status</th><th>Expires On</th><th>Days Left</th></tr></thead><tbody>
    {% for row in licenses_list %}
    <tr><td class="hwid-col" title="{{ row['hwid'] }}">{{ row['hwid'][:20] }}...</td>
    <td>{% if row['is_active'] and row['days_left'] > 7 %}<span class="badge badge-active">Active</span>{% elif row['is_active'] and row['days_left'] <= 7 %}<span class="badge badge-expiring">Expiring</span>{% else %}<span class="badge badge-inactive">Inactive</span>{% endif %}</td>
    <td>{{ row['expiry_date'] }}</td>
    <td style="color:{% if row['days_left'] <= 7 %}red{% endif %};font-weight:bold;">{% if row['is_active'] %}{{ row['days_left'] }} Days{% else %}N/A{% endif %}</td></tr>
    {% endfor %}</tbody></table></div></body></html>
    """, partner=partner, licenses=licenses_list)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    init_db()
    app.run(host='0.0.0.0', port=port, debug=False)
