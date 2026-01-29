#!/usr/bin/env python3
"""
Pricing Management Web Interface

Simple web app to manage Nutanix licensing pricing for Dark Site Metering.
"""

import os
import json
import csv
import io
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, Response
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

PRICING_FILE = os.getenv('PRICING_FILE', '/data/pricing/pricing.json')

# Prometheus metrics for pricing
nci_hourly_rate = Gauge('nutanix_pricing_nci_hourly_rate', 'NCI hourly rate per core', ['product_code', 'name'])
nus_hourly_rate = Gauge('nutanix_pricing_nus_hourly_rate', 'NUS hourly rate per TiB', ['product_code', 'name'])
active_nci_rate = Gauge('nutanix_pricing_active_nci_rate', 'Active NCI hourly rate per core')
active_nus_rate = Gauge('nutanix_pricing_active_nus_rate', 'Active NUS hourly rate per TiB')

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Dark Site Metering - Pricing Management</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #00d4ff; margin-bottom: 5px; }
        h2 { color: #ff6b6b; margin-top: 30px; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .subtitle { color: #888; margin-bottom: 30px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; background: #16213e; border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #0f3460; color: #00d4ff; }
        tr:hover { background: #1a3a5c; }
        .active { background: #1a4a3a !important; }
        .rate { font-family: monospace; color: #4ade80; }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin: 2px;
        }
        .btn-primary { background: #00d4ff; color: #000; }
        .btn-primary:hover { background: #00b8e6; }
        .btn-danger { background: #ff6b6b; color: #fff; }
        .btn-danger:hover { background: #ff5252; }
        .btn-success { background: #4ade80; color: #000; }
        .btn-success:hover { background: #3cc970; }
        input, select {
            padding: 8px 12px;
            border: 1px solid #333;
            border-radius: 4px;
            background: #0f3460;
            color: #eee;
            margin: 2px;
        }
        input:focus, select:focus { outline: none; border-color: #00d4ff; }
        .form-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 15px 0; }
        .card { background: #16213e; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .message { padding: 15px; border-radius: 4px; margin: 15px 0; }
        .message.success { background: #1a4a3a; border: 1px solid #4ade80; }
        .message.error { background: #4a1a1a; border: 1px solid #ff6b6b; }
        .import-section { margin-top: 30px; padding-top: 20px; border-top: 1px solid #333; }
        .active-badge {
            background: #4ade80;
            color: #000;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
        }
        .metrics-link { color: #00d4ff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Dark Site Metering</h1>
        <p class="subtitle">Pricing Management Interface</p>

        {% if message %}
        <div class="message {{ message_type }}">{{ message }}</div>
        {% endif %}

        <h2>NCI Pricing (Cores)</h2>
        <p>Active rate: <span class="rate">${{ "%.8f"|format(active_nci.hourly_rate) }}/core/hour</span> ({{ active_nci.name }})</p>
        <table>
            <thead>
                <tr>
                    <th>Product Code</th>
                    <th>Name</th>
                    <th>Hourly Rate</th>
                    <th>Annual Rate</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for code, item in pricing.nci.items() %}
                <tr class="{{ 'active' if code == pricing.active.nci else '' }}">
                    <td>{{ code }} {% if code == pricing.active.nci %}<span class="active-badge">ACTIVE</span>{% endif %}</td>
                    <td>{{ item.name }}</td>
                    <td class="rate">${{ "%.8f"|format(item.hourly_rate) }}/{{ item.unit }}/hr</td>
                    <td class="rate">${{ "%.2f"|format(item.annual_rate) }}/{{ item.unit }}/yr</td>
                    <td>
                        {% if code != pricing.active.nci %}
                        <form method="post" action="/set-active" style="display:inline">
                            <input type="hidden" name="type" value="nci">
                            <input type="hidden" name="code" value="{{ code }}">
                            <button type="submit" class="btn btn-primary">Set Active</button>
                        </form>
                        {% endif %}
                        <form method="post" action="/delete" style="display:inline">
                            <input type="hidden" name="type" value="nci">
                            <input type="hidden" name="code" value="{{ code }}">
                            <button type="submit" class="btn btn-danger" onclick="return confirm('Delete this pricing?')">Delete</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="card">
            <h3>Add NCI Pricing</h3>
            <form method="post" action="/add">
                <input type="hidden" name="type" value="nci">
                <div class="form-row">
                    <input type="text" name="code" placeholder="Product Code (e.g., SP-SW-NCI-XXX-PR)" required style="width: 250px">
                    <input type="text" name="name" placeholder="Name (e.g., NCI Pro)" required>
                    <input type="number" name="hourly_rate" placeholder="Hourly Rate" step="0.00000001" required>
                    <input type="number" name="annual_rate" placeholder="Annual Rate" step="0.01" required>
                    <input type="hidden" name="unit" value="core">
                    <button type="submit" class="btn btn-success">Add</button>
                </div>
            </form>
        </div>

        <h2>NUS Pricing (Files - TiB)</h2>
        <p>Active rate: <span class="rate">${{ "%.8f"|format(active_nus.hourly_rate) }}/TiB/hour</span> ({{ active_nus.name }})</p>
        <table>
            <thead>
                <tr>
                    <th>Product Code</th>
                    <th>Name</th>
                    <th>Hourly Rate</th>
                    <th>Annual Rate</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for code, item in pricing.nus.items() %}
                <tr class="{{ 'active' if code == pricing.active.nus else '' }}">
                    <td>{{ code }} {% if code == pricing.active.nus %}<span class="active-badge">ACTIVE</span>{% endif %}</td>
                    <td>{{ item.name }}</td>
                    <td class="rate">${{ "%.8f"|format(item.hourly_rate) }}/{{ item.unit }}/hr</td>
                    <td class="rate">${{ "%.2f"|format(item.annual_rate) }}/{{ item.unit }}/yr</td>
                    <td>
                        {% if code != pricing.active.nus %}
                        <form method="post" action="/set-active" style="display:inline">
                            <input type="hidden" name="type" value="nus">
                            <input type="hidden" name="code" value="{{ code }}">
                            <button type="submit" class="btn btn-primary">Set Active</button>
                        </form>
                        {% endif %}
                        <form method="post" action="/delete" style="display:inline">
                            <input type="hidden" name="type" value="nus">
                            <input type="hidden" name="code" value="{{ code }}">
                            <button type="submit" class="btn btn-danger" onclick="return confirm('Delete this pricing?')">Delete</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="card">
            <h3>Add NUS Pricing</h3>
            <form method="post" action="/add">
                <input type="hidden" name="type" value="nus">
                <div class="form-row">
                    <input type="text" name="code" placeholder="Product Code (e.g., SP-SW-NUS-XXX-PR)" required style="width: 250px">
                    <input type="text" name="name" placeholder="Name (e.g., NUS Pro)" required>
                    <input type="number" name="hourly_rate" placeholder="Hourly Rate" step="0.00000001" required>
                    <input type="number" name="annual_rate" placeholder="Annual Rate" step="0.01" required>
                    <input type="hidden" name="unit" value="TiB">
                    <button type="submit" class="btn btn-success">Add</button>
                </div>
            </form>
        </div>

        <div class="import-section">
            <h2>Import/Export</h2>
            <div class="card">
                <h3>Import from CSV</h3>
                <p>CSV format: type,product_code,name,hourly_rate,annual_rate,unit</p>
                <form method="post" action="/import-csv" enctype="multipart/form-data">
                    <div class="form-row">
                        <input type="file" name="file" accept=".csv" required>
                        <button type="submit" class="btn btn-primary">Import CSV</button>
                    </div>
                </form>

                <h3 style="margin-top: 20px;">Export</h3>
                <div class="form-row">
                    <a href="/export-csv" class="btn btn-success">Export CSV</a>
                    <a href="/export-json" class="btn btn-success">Export JSON</a>
                    <a href="/metrics" class="btn btn-primary">View Prometheus Metrics</a>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
'''

def load_pricing():
    """Load pricing from JSON file."""
    try:
        with open(PRICING_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "nci": {},
            "nus": {},
            "active": {"nci": "", "nus": ""}
        }

def save_pricing(pricing):
    """Save pricing to JSON file."""
    os.makedirs(os.path.dirname(PRICING_FILE), exist_ok=True)
    with open(PRICING_FILE, 'w') as f:
        json.dump(pricing, f, indent=2)
    update_prometheus_metrics(pricing)

def update_prometheus_metrics(pricing):
    """Update Prometheus metrics with current pricing."""
    # Clear existing metrics
    nci_hourly_rate._metrics.clear()
    nus_hourly_rate._metrics.clear()

    # Set NCI rates
    for code, item in pricing.get('nci', {}).items():
        nci_hourly_rate.labels(product_code=code, name=item['name']).set(item['hourly_rate'])

    # Set NUS rates
    for code, item in pricing.get('nus', {}).items():
        nus_hourly_rate.labels(product_code=code, name=item['name']).set(item['hourly_rate'])

    # Set active rates
    active_nci_code = pricing.get('active', {}).get('nci', '')
    active_nus_code = pricing.get('active', {}).get('nus', '')

    if active_nci_code and active_nci_code in pricing.get('nci', {}):
        active_nci_rate.set(pricing['nci'][active_nci_code]['hourly_rate'])

    if active_nus_code and active_nus_code in pricing.get('nus', {}):
        active_nus_rate.set(pricing['nus'][active_nus_code]['hourly_rate'])

def get_active_pricing(pricing, ptype):
    """Get the active pricing for a type."""
    active_code = pricing.get('active', {}).get(ptype, '')
    items = pricing.get(ptype, {})
    if active_code and active_code in items:
        return items[active_code]
    return {'name': 'Not Set', 'hourly_rate': 0, 'annual_rate': 0, 'unit': 'N/A'}

@app.route('/')
def index():
    pricing = load_pricing()
    message = request.args.get('message', '')
    message_type = request.args.get('type', 'success')

    return render_template_string(
        HTML_TEMPLATE,
        pricing=pricing,
        active_nci=get_active_pricing(pricing, 'nci'),
        active_nus=get_active_pricing(pricing, 'nus'),
        message=message,
        message_type=message_type
    )

@app.route('/add', methods=['POST'])
def add_pricing():
    pricing = load_pricing()
    ptype = request.form['type']
    code = request.form['code']

    pricing[ptype][code] = {
        'name': request.form['name'],
        'hourly_rate': float(request.form['hourly_rate']),
        'annual_rate': float(request.form['annual_rate']),
        'unit': request.form['unit']
    }

    save_pricing(pricing)
    return redirect(url_for('index', message=f'Added {code}', type='success'))

@app.route('/delete', methods=['POST'])
def delete_pricing():
    pricing = load_pricing()
    ptype = request.form['type']
    code = request.form['code']

    if code in pricing[ptype]:
        del pricing[ptype][code]
        if pricing['active'].get(ptype) == code:
            pricing['active'][ptype] = ''
        save_pricing(pricing)
        return redirect(url_for('index', message=f'Deleted {code}', type='success'))

    return redirect(url_for('index', message='Pricing not found', type='error'))

@app.route('/set-active', methods=['POST'])
def set_active():
    pricing = load_pricing()
    ptype = request.form['type']
    code = request.form['code']

    if code in pricing[ptype]:
        pricing['active'][ptype] = code
        save_pricing(pricing)
        return redirect(url_for('index', message=f'Set {code} as active', type='success'))

    return redirect(url_for('index', message='Pricing not found', type='error'))

@app.route('/import-csv', methods=['POST'])
def import_csv():
    pricing = load_pricing()

    if 'file' not in request.files:
        return redirect(url_for('index', message='No file uploaded', type='error'))

    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('index', message='No file selected', type='error'))

    try:
        content = file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))

        count = 0
        for row in reader:
            ptype = row.get('type', '').lower()
            if ptype not in ['nci', 'nus']:
                continue

            code = row.get('product_code', '')
            if not code:
                continue

            pricing[ptype][code] = {
                'name': row.get('name', code),
                'hourly_rate': float(row.get('hourly_rate', 0)),
                'annual_rate': float(row.get('annual_rate', 0)),
                'unit': row.get('unit', 'core' if ptype == 'nci' else 'TiB')
            }
            count += 1

        save_pricing(pricing)
        return redirect(url_for('index', message=f'Imported {count} pricing entries', type='success'))

    except Exception as e:
        return redirect(url_for('index', message=f'Import error: {str(e)}', type='error'))

@app.route('/export-csv')
def export_csv():
    pricing = load_pricing()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['type', 'product_code', 'name', 'hourly_rate', 'annual_rate', 'unit'])

    for code, item in pricing.get('nci', {}).items():
        writer.writerow(['nci', code, item['name'], item['hourly_rate'], item['annual_rate'], item['unit']])

    for code, item in pricing.get('nus', {}).items():
        writer.writerow(['nus', code, item['name'], item['hourly_rate'], item['annual_rate'], item['unit']])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=pricing.csv'}
    )

@app.route('/export-json')
def export_json():
    pricing = load_pricing()
    return Response(
        json.dumps(pricing, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=pricing.json'}
    )

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint."""
    pricing = load_pricing()
    update_prometheus_metrics(pricing)
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route('/api/pricing')
def api_pricing():
    """API endpoint to get current pricing."""
    pricing = load_pricing()
    return jsonify(pricing)

@app.route('/api/active-rates')
def api_active_rates():
    """API endpoint to get active rates."""
    pricing = load_pricing()
    return jsonify({
        'nci': get_active_pricing(pricing, 'nci'),
        'nus': get_active_pricing(pricing, 'nus')
    })

if __name__ == '__main__':
    # Initialize metrics on startup
    pricing = load_pricing()
    update_prometheus_metrics(pricing)

    app.run(host='0.0.0.0', port=5000, debug=False)
