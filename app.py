"""
Flask web application for Soaring CUP File Editor.
Converts the desktop Tkinter app to a web-based interface.
"""

import os
import json
import uuid
import io
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
import time as _time

from backend.models import Waypoint
from backend.file_io import (
    parse_cup_file, write_cup_file, parse_csv_file, write_csv_file, get_elevation,
    format_coordinate, write_task_cup, write_task_lkt, write_task_tsk, write_task_xctsk, parse_task_cup
)
from backend.config import STYLE_OPTIONS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'soaring_cup_editor_secret_key_change_in_production')
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
DATA_FOLDER = 'data'
ALLOWED_EXTENSIONS = {'cup', 'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure logging
if not app.debug:
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        'logs/soaring_cup.log',
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Soaring CUP Web startup')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

# XCSoar repository cache
_xcsoar_repo_cache = None
_xcsoar_repo_cache_ts = 0.0


def get_session_data_file():
    """Get the path to the session data file."""
    session_id = session.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
    return os.path.join(DATA_FOLDER, f'session_{session_id}.json')


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_waypoints():
    """Get waypoints from session storage."""
    try:
        data_file = get_session_data_file()
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [Waypoint.from_dict(wp) for wp in data.get('waypoints', [])]
    except Exception as e:
        app.logger.error(f"Error loading session data: {e}")
    return []


def set_session_waypoints(waypoints):
    """Store waypoints in session storage (preserves task data)."""
    try:
        data_file = get_session_data_file()
        # Load existing data to preserve task state
        existing = {}
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        existing['waypoints'] = [wp.to_dict() for wp in waypoints]
        existing['current_filename'] = session.get('current_filename', '')
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app.logger.error(f"Error saving session data: {e}")


def get_session_task():
    """Get saved task from session storage."""
    try:
        data_file = get_session_data_file()
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('task')
    except Exception as e:
        app.logger.error(f"Error loading task data: {e}")
    return None


def set_session_task(task_data):
    """Store task in session storage (preserves waypoints)."""
    try:
        data_file = get_session_data_file()
        existing = {}
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        existing['task'] = task_data
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app.logger.error(f"Error saving task data: {e}")


@app.route('/')
def index():
    """Main application page."""
    return render_template('index.html', style_options=STYLE_OPTIONS,
                           view_mode=False, view_token='', view_task_name='')


@app.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    import requests
    
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }
    
    # Test external API connectivity
    try:
        response = requests.get('https://api.open-elevation.com/api/v1/lookup?locations=52.0,21.0', timeout=5)
        health_status['elevation_api'] = 'reachable' if response.status_code == 200 else 'unreachable'
        health_status['elevation_api_status'] = response.status_code
    except requests.exceptions.Timeout:
        health_status['elevation_api'] = 'timeout'
        app.logger.warning('Elevation API timeout during health check')
    except requests.exceptions.RequestException as e:
        health_status['elevation_api'] = f'error: {str(e)}'
        app.logger.warning(f'Elevation API error during health check: {e}')
    except Exception as e:
        health_status['elevation_api'] = f'unexpected error: {str(e)}'
        app.logger.error(f'Unexpected error during health check: {e}')
    
    return jsonify(health_status), 200


@app.route('/api/waypoints', methods=['GET'])
def get_waypoints():
    """Get all waypoints."""
    waypoints = get_session_waypoints()
    return jsonify([wp.to_dict() for wp in waypoints])


@app.route('/api/waypoints', methods=['POST'])
def add_waypoint():
    """Add a new waypoint."""
    try:
        data = request.get_json()
        
        # Auto-fetch elevation if not provided
        if not data.get('elevation') and data.get('latitude') and data.get('longitude'):
            try:
                elevation = get_elevation(data['latitude'], data['longitude'])
                if elevation and elevation > 0:  # Only use if valid elevation returned
                    data['elevation'] = f"{elevation}m"
                    app.logger.info(f"Auto-fetched elevation {elevation}m for waypoint at {data['latitude']}, {data['longitude']}")
            except Exception as e:
                app.logger.warning(f"Could not fetch elevation: {e}")
                # Continue without elevation - don't fail the whole operation
        
        waypoint = Waypoint.from_dict(data)
        
        waypoints = get_session_waypoints()
        waypoints.append(waypoint)
        # Sort by name like desktop app
        waypoints.sort(key=lambda w: w.name.lower())
        set_session_waypoints(waypoints)
        
        app.logger.info(f"Added waypoint: {waypoint.name}")
        return jsonify({'success': True, 'waypoint': waypoint.to_dict()})
    except Exception as e:
        import traceback
        app.logger.error(f"Add waypoint error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/waypoints/<int:index>', methods=['PUT'])
def update_waypoint(index):
    """Update an existing waypoint."""
    try:
        data = request.get_json()
        waypoints = get_session_waypoints()
        
        if 0 <= index < len(waypoints):
            original_waypoint = waypoints[index]
            
            # Check if coordinates changed and auto-fetch elevation if needed
            coords_changed = (original_waypoint.latitude != data.get('latitude') or 
                            original_waypoint.longitude != data.get('longitude'))
            
            if (coords_changed or not data.get('elevation')) and data.get('latitude') and data.get('longitude'):
                try:
                    elevation = get_elevation(data['latitude'], data['longitude'])
                    if elevation and elevation > 0:  # Only use if valid elevation returned
                        data['elevation'] = f"{elevation}m"
                        app.logger.info(f"Auto-fetched elevation {elevation}m for waypoint at {data['latitude']}, {data['longitude']}")
                except Exception as e:
                    app.logger.warning(f"Could not fetch elevation: {e}")
                    # Continue without elevation - don't fail the whole operation
            
            waypoint = Waypoint.from_dict(data)
            waypoints[index] = waypoint
            # Sort by name like desktop app
            waypoints.sort(key=lambda w: w.name.lower())
            set_session_waypoints(waypoints)
            
            app.logger.info(f"Updated waypoint: {waypoint.name}")
            return jsonify({'success': True, 'waypoint': waypoint.to_dict()})
        else:
            return jsonify({'success': False, 'error': 'Waypoint index out of range'}), 404
    except Exception as e:
        import traceback
        app.logger.error(f"Update waypoint error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/waypoints/<int:index>', methods=['DELETE'])
def delete_waypoint(index):
    """Delete a waypoint."""
    try:
        waypoints = get_session_waypoints()
        if 0 <= index < len(waypoints):
            deleted_waypoint = waypoints.pop(index)
            set_session_waypoints(waypoints)
            return jsonify({'success': True, 'deleted': deleted_waypoint.to_dict()})
        else:
            return jsonify({'success': False, 'error': 'Waypoint index out of range'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/elevation/<float:lat>/<float:lon>', methods=['GET'])
def fetch_elevation(lat, lon):
    """Fetch elevation for given coordinates."""
    try:
        app.logger.info(f"Fetching elevation for {lat}, {lon}")
        elevation = get_elevation(lat, lon)
        app.logger.info(f"Elevation result: {elevation}m")
        return jsonify({'success': True, 'elevation': elevation})
    except Exception as e:
        import traceback
        app.logger.error(f"Elevation fetch error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload and parse CUP or CSV file."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Parse based on file extension
                if filename.lower().endswith('.cup'):
                    waypoints = parse_cup_file(filepath)
                elif filename.lower().endswith('.csv'):
                    waypoints = parse_csv_file(filepath)
                else:
                    return jsonify({'success': False, 'error': 'Unsupported file type'}), 400
                
                # Store in session
                set_session_waypoints(waypoints)
                session['current_filename'] = filename
                
                # Clean up uploaded file
                os.remove(filepath)
                
                app.logger.info(f"Uploaded and parsed {filename}: {len(waypoints)} waypoints")
                return jsonify({
                    'success': True, 
                    'message': f'Loaded {len(waypoints)} waypoints from {filename}',
                    'waypoints': [wp.to_dict() for wp in waypoints]
                })
                
            except Exception as e:
                # Clean up on error
                if os.path.exists(filepath):
                    os.remove(filepath)
                app.logger.error(f"Error parsing file {filename}: {e}")
                return jsonify({'success': False, 'error': f'Error parsing file: {str(e)}'}), 400
        
        return jsonify({'success': False, 'error': 'Invalid file type. Only .cup and .csv files are allowed.'}), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download/<file_format>')
def download_file(file_format):
    """Download waypoints as CUP file."""
    try:
        waypoints = get_session_waypoints()
        if not waypoints:
            return jsonify({'success': False, 'error': 'No waypoints to download'}), 400
        
        # Only support CUP format
        if file_format.lower() != 'cup':
            return jsonify({'success': False, 'error': 'Only CUP format is supported.'}), 400
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.cup', encoding='utf-8') as tmp_file:
            tmp_path = tmp_file.name
        
        # Get CUP content as string and write to file
        content = write_cup_file(waypoints)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        filename = session.get('current_filename', 'waypoints.cup')
        if not filename.endswith('.cup'):
            filename = 'waypoints.cup'
        
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='text/plain'
        )
        
    except Exception as e:
        app.logger.error(f"Download error: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clear', methods=['POST'])
def clear_waypoints():
    """Clear all waypoints from session."""
    session.pop('waypoints', None)
    session.pop('current_filename', None)
    app.logger.info("Cleared all waypoints from session")
    return jsonify({'success': True, 'message': 'All waypoints cleared'})


@app.route('/api/style-options')
def get_style_options():
    """Get available waypoint style options."""
    return jsonify(STYLE_OPTIONS)


@app.route('/api/task/export', methods=['POST'])
def export_task():
    """Export a task as a CUP file with waypoints and task definition."""
    try:
        data = request.get_json()
        task_name = data.get('name', 'Task')
        task_points = data.get('points', [])  # [{waypointIndex, obsZone}, ...]
        task_options = data.get('options', {})

        if len(task_points) < 2:
            return jsonify({'success': False, 'error': 'A task needs at least 2 points (start + finish)'}), 400

        waypoints = get_session_waypoints()

        # Collect the waypoints used in the task
        task_waypoints = []
        for tp in task_points:
            idx = tp.get('waypointIndex')
            if idx is None or idx < 0 or idx >= len(waypoints):
                return jsonify({'success': False, 'error': f'Invalid waypoint index: {idx}'}), 400
            task_waypoints.append(waypoints[idx])

        # Build obs zones from the request
        obs_zones = [tp.get('obsZone', {}) for tp in task_points]

        content = write_task_cup(task_name, task_waypoints, obs_zones, task_options)

        return jsonify({'success': True, 'content': content})
    except Exception as e:
        import traceback
        app.logger.error(f"Task export error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/download', methods=['POST'])
def download_task():
    """Download a task in the requested format (cup, tsk, xctsk)."""
    try:
        data = request.get_json()
        task_name = data.get('name', 'Task')
        task_points = data.get('points', [])
        task_options = data.get('options', {})
        fmt = data.get('format', 'cup').lower()

        if len(task_points) < 2:
            return jsonify({'success': False, 'error': 'A task needs at least 2 points'}), 400

        waypoints = get_session_waypoints()

        task_waypoints = []
        for tp in task_points:
            idx = tp.get('waypointIndex')
            if idx is None or idx < 0 or idx >= len(waypoints):
                return jsonify({'success': False, 'error': f'Invalid waypoint index: {idx}'}), 400
            task_waypoints.append(waypoints[idx])

        obs_zones = [tp.get('obsZone', {}) for tp in task_points]

        if fmt == 'tsk':
            content = write_task_tsk(task_name, task_waypoints, obs_zones, task_options)
            suffix = '.tsk'
            mimetype = 'application/xml'
        elif fmt == 'xctsk':
            content = write_task_xctsk(task_name, task_waypoints, obs_zones, task_options)
            suffix = '.xctsk'
            mimetype = 'application/json'
        elif fmt == 'lkt':
            content = write_task_lkt(task_name, task_waypoints, obs_zones, task_options)
            suffix = '.lkt'
            mimetype = 'application/xml'
        else:
            content = write_task_cup(task_name, task_waypoints, obs_zones, task_options)
            suffix = '.cup'
            mimetype = 'text/plain'

        safe_name = task_name.replace(' ', '_')
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=suffix, encoding='utf-8') as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f"{safe_name}{suffix}",
            mimetype=mimetype
        )
    except Exception as e:
        app.logger.error(f"Task download error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Store QR download tokens: {token: file_path}
_qr_downloads = {}


@app.route('/api/task/qr', methods=['POST'])
def task_qr():
    """Generate a downloadable task file and return a short download URL for QR encoding."""
    try:
        data = request.get_json()
        task_name = data.get('name', 'Task')
        task_points = data.get('points', [])
        task_options = data.get('options', {})

        if len(task_points) < 2:
            return jsonify({'success': False, 'error': 'A task needs at least 2 points'}), 400

        waypoints = get_session_waypoints()

        task_waypoints = []
        for tp in task_points:
            idx = tp.get('waypointIndex')
            if idx is None or idx < 0 or idx >= len(waypoints):
                return jsonify({'success': False, 'error': f'Invalid waypoint index: {idx}'}), 400
            task_waypoints.append(waypoints[idx])

        obs_zones = [tp.get('obsZone', {}) for tp in task_points]
        content = write_task_cup(task_name, task_waypoints, obs_zones, task_options)

        # Save to a temp file with a unique token
        token = uuid.uuid4().hex[:12]
        filename = f"{task_name.replace(' ', '_')}.cup"
        tmp_path = os.path.join(DATA_FOLDER, f'qr_{token}.cup')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        _qr_downloads[token] = {'path': tmp_path, 'filename': filename}

        return jsonify({'success': True, 'token': token})
    except Exception as e:
        app.logger.error(f"Task QR error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/dl/<token>')
def qr_download(token):
    """Serve a task file by its QR download token."""
    info = _qr_downloads.get(token)
    if not info or not os.path.exists(info['path']):
        return 'File not found or expired', 404
    return send_file(
        info['path'],
        as_attachment=True,
        download_name=info['filename'],
        mimetype='text/plain'
    )


# ──────────── XCTSK v2 helpers ────────────

def _polyline_encode_num(num):
    """Encode a single signed integer using Google's polyline algorithm."""
    pnum = (num << 1) if num >= 0 else ~(num << 1)
    result = []
    while pnum > 0x1f:
        result.append(chr(((pnum & 0x1f) | 0x20) + 63))
        pnum >>= 5
    result.append(chr(pnum + 63))
    return ''.join(result)


def _xctsk_encode_z(lon, lat, alt, radius):
    """Encode (lon, lat, alt, radius) into XCTSK 'z' polyline field."""
    return (_polyline_encode_num(round(lon * 1e5)) +
            _polyline_encode_num(round(lat * 1e5)) +
            _polyline_encode_num(round(alt)) +
            _polyline_encode_num(round(radius)))


def build_xctsk_payload(task_points, waypoints, no_start='', goal_is_line=False):
    """Build XCTSK v2 JSON payload from task data."""
    n = len(task_points)
    turnpoints = []
    for i, tp in enumerate(task_points):
        idx = tp.get('waypointIndex')
        wp = waypoints[idx]
        oz = tp.get('obsZone', {})
        radius = int(oz.get('r1') or oz.get('R1') or 500)
        alt = int(wp.elevation) if wp.elevation else 0

        point = {
            'z': _xctsk_encode_z(wp.longitude, wp.latitude, alt, radius),
            'n': wp.name or ''
        }
        if wp.code:
            point['d'] = wp.code

        if i == 0:
            point['t'] = 2      # SSS
        if i == n - 1:
            point['t'] = 3      # ESS

        oz_overrides = {}
        is_line = oz.get('isLine') or int(oz.get('Line', 0) or 0) == 1
        if is_line:
            oz_overrides['l'] = 1
        a1 = int(oz.get('a1') or oz.get('A1') or 180)
        if a1 and a1 != 180:
            oz_overrides['a1'] = a1
        if oz_overrides:
            point['o'] = oz_overrides

        turnpoints.append(point)

    xctsk = {
        'taskType': 'CLASSIC',
        'version': 2,
        't': turnpoints,
        's': {'g': [], 'd': 1, 't': 1},
        'g': {'t': 1 if goal_is_line else 2}
    }
    if no_start:
        xctsk['s']['g'] = [no_start + 'Z']
    return xctsk


@app.route('/api/task/xctsk-qr', methods=['POST'])
def task_xctsk_qr():
    """Generate an XCTSK v2 QR code image (PNG) for the task."""
    try:
        import qrcode
        import qrcode.image.svg
        from PIL import Image

        data = request.get_json()
        task_points = data.get('points', [])
        no_start = data.get('noStart', '')

        if len(task_points) < 2:
            return jsonify({'success': False, 'error': 'A task needs at least 2 points'}), 400

        waypoints = get_session_waypoints()
        for tp in task_points:
            idx = tp.get('waypointIndex')
            if idx is None or idx < 0 or idx >= len(waypoints):
                return jsonify({'success': False, 'error': f'Invalid waypoint index: {idx}'}), 400

        last_oz = task_points[-1].get('obsZone', {})
        goal_is_line = last_oz.get('isLine') or int(last_oz.get('Line', 0) or 0) == 1

        xctsk = build_xctsk_payload(task_points, waypoints, no_start, goal_is_line)
        xctsk_string = 'XCTSK:' + json.dumps(xctsk, ensure_ascii=False, separators=(',', ':'))

        # Generate QR code as PNG, return as base64 data URL
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6,
            border=2
        )
        qr.add_data(xctsk_string.encode('utf-8'))
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        import base64
        img_b64 = base64.b64encode(buf.read()).decode('ascii')
        data_url = f'data:image/png;base64,{img_b64}'

        return jsonify({'success': True, 'dataUrl': data_url, 'xctskString': xctsk_string})
    except Exception as e:
        import traceback
        app.logger.error(f'XCTSK QR error: {e}\n{traceback.format_exc()}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/save', methods=['POST'])
def save_task():
    """Save task state to session."""
    try:
        data = request.get_json()
        set_session_task(data)
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Task save error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/load', methods=['GET'])
def load_task():
    """Load saved task state from session."""
    try:
        task = get_session_task()
        if task:
            return jsonify({'success': True, 'task': task})
        return jsonify({'success': True, 'task': None})
    except Exception as e:
        app.logger.error(f"Task load error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/task/import', methods=['POST'])
def import_task():
    """Import a task from an uploaded CUP file."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        content = file.read().decode('utf-8', errors='replace')
        result = parse_task_cup(content)

        if result is None:
            return jsonify({'success': False, 'error': 'No task section found in file'}), 400

        # Match task waypoint names to the session waypoints
        session_waypoints = get_session_waypoints()
        task_points = []

        for i, wp_name in enumerate(result['task_wp_names']):
            # Try to find matching waypoint in session by name
            matched_idx = -1
            for j, swp in enumerate(session_waypoints):
                if swp.name.strip('"') == wp_name.strip('"'):
                    matched_idx = j
                    break

            if matched_idx < 0:
                # Try matching from the file's own waypoints by name, then by coordinates in session
                file_wp = None
                for fwp in result['waypoints']:
                    if fwp['name'].strip('"') == wp_name.strip('"'):
                        file_wp = fwp
                        break
                if file_wp:
                    # Find closest session waypoint by coordinates
                    best_idx = -1
                    best_dist = float('inf')
                    for j, swp in enumerate(session_waypoints):
                        dlat = swp.latitude - file_wp['latitude']
                        dlon = swp.longitude - file_wp['longitude']
                        d = dlat * dlat + dlon * dlon
                        if d < best_dist:
                            best_dist = d
                            best_idx = j
                    # Accept if within ~500m (~0.005 degrees)
                    if best_dist < 0.005 * 0.005:
                        matched_idx = best_idx

            # Build obsZone for this point
            oz = {}
            if i < len(result['obs_zones']):
                oz = result['obs_zones'][i]

            task_points.append({
                'waypointIndex': matched_idx,
                'waypointName': wp_name.strip('"'),
                'obsZone': {
                    'style': oz.get('style', 1),
                    'r1': oz.get('r1', 3000),
                    'a1': oz.get('a1', 45),
                    'r2': oz.get('r2', 500),
                    'a2': oz.get('a2', 180),
                    'a12': oz.get('a12', 0),
                    'isLine': oz.get('isLine', False),
                    'move': oz.get('move', True),
                    'reduce': oz.get('reduce', False),
                    'directionMode': 'auto',
                    'fixedBearing': None
                },
                'fileWaypoint': None
            })

            # If not matched, include file waypoint data so frontend can display it
            if matched_idx < 0:
                for fwp in result['waypoints']:
                    if fwp['name'].strip('"') == wp_name.strip('"'):
                        task_points[-1]['fileWaypoint'] = fwp
                        break

        return jsonify({
            'success': True,
            'task_name': result['task_name'],
            'options': result['options'],
            'points': task_points
        })
    except Exception as e:
        import traceback
        app.logger.error(f"Task import error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


# ──────────── Task sharing ────────────

SHARE_TTL_SECONDS = 24 * 3600  # share links expire after 24 hours


def _get_base_url():
    """Return the base URL for share links.

    Uses the BASE_URL env variable when set (required behind reverse proxies).
    Falls back to Flask's request.host_url for direct deployments.
    """
    base = os.environ.get('BASE_URL', '').rstrip('/')
    return base if base else request.host_url.rstrip('/')


def _cleanup_expired_shares():
    """Delete share snapshots older than SHARE_TTL_SECONDS."""
    now = datetime.now().timestamp()
    for path in Path(DATA_FOLDER).glob('share_*.json'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if now - d.get('created', 0) > SHARE_TTL_SECONDS:
                path.unlink(missing_ok=True)
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


def _build_xctsk_from_stored(task_waypoints_data, obs_zones, no_start=''):
    """Build XCTSK v2 payload from already-resolved waypoint dicts."""
    fake_points = [
        {'waypointIndex': i, 'obsZone': obs_zones[i] if i < len(obs_zones) else {}}
        for i in range(len(task_waypoints_data))
    ]
    waypoints_list = [Waypoint.from_dict(d) for d in task_waypoints_data]
    last_oz = obs_zones[-1] if obs_zones else {}
    goal_is_line = bool(last_oz.get('isLine'))
    return build_xctsk_payload(fake_points, waypoints_list, no_start, goal_is_line)


def _load_share(token):
    """Load and validate a share snapshot. Returns (data, None) or (None, err_str)."""
    if len(token) != 16 or not token.isalnum():
        return None, 'invalid'
    share_path = os.path.join(DATA_FOLDER, f'share_{token}.json')
    if not os.path.exists(share_path):
        return None, 'expired'
    with open(share_path, 'r', encoding='utf-8') as f:
        share_data = json.load(f)
    if datetime.now().timestamp() - share_data.get('created', 0) > SHARE_TTL_SECONDS:
        try:
            os.unlink(share_path)
        except OSError:
            pass
        return None, 'expired'
    return share_data, None


@app.route('/api/task/share', methods=['POST'])
def create_share():
    """Save a self-contained task snapshot and return a shareable link."""
    try:
        _cleanup_expired_shares()
        data = request.get_json()
        task_name = data.get('name', 'Task')
        task_points = data.get('points', [])
        task_options = data.get('options', {})

        if len(task_points) < 2:
            return jsonify({'success': False, 'error': 'A task needs at least 2 points'}), 400

        waypoints = get_session_waypoints()
        task_waypoints = []
        for tp in task_points:
            idx = tp.get('waypointIndex')
            if idx is None or idx < 0 or idx >= len(waypoints):
                return jsonify({'success': False, 'error': f'Invalid waypoint index: {idx}'}), 400
            task_waypoints.append(waypoints[idx].to_dict())

        obs_zones = [tp.get('obsZone', {}) for tp in task_points]
        token = uuid.uuid4().hex[:16]
        share_data = {
            'created': datetime.now().timestamp(),
            'task_name': task_name,
            'task_waypoints': task_waypoints,
            'obs_zones': obs_zones,
            'options': task_options,
        }
        share_path = os.path.join(DATA_FOLDER, f'share_{token}.json')
        with open(share_path, 'w', encoding='utf-8') as f:
            json.dump(share_data, f, ensure_ascii=False, indent=2)

        share_url = _get_base_url() + f'/share/{token}'
        return jsonify({'success': True, 'url': share_url})
    except Exception as e:
        app.logger.error(f"Share create error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/share/<token>')
def share_page(token):
    """Render the shareable task page."""
    try:
        share_data, err = _load_share(token)
        if err:
            return render_template('share.html', expired=True, task_name='',
                                   token=token, qr_data_url=None,
                                   waypoint_names=[], expires_str='')

        import qrcode
        xctsk = _build_xctsk_from_stored(
            share_data['task_waypoints'],
            share_data['obs_zones'],
            share_data.get('options', {}).get('noStart', '')
        )
        xctsk_string = 'XCTSK:' + json.dumps(xctsk, ensure_ascii=False, separators=(',', ':'))
        qr = qrcode.QRCode(version=None,
                           error_correction=qrcode.constants.ERROR_CORRECT_L,
                           box_size=8, border=2)
        qr.add_data(xctsk_string.encode('utf-8'))
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        import base64
        qr_data_url = 'data:image/png;base64,' + base64.b64encode(buf.read()).decode('ascii')

        expires_dt = datetime.fromtimestamp(share_data['created'] + SHARE_TTL_SECONDS)
        expires_str = expires_dt.strftime('%d %b %Y %H:%M')
        waypoint_names = [wp['name'] for wp in share_data['task_waypoints']]

        return render_template('share.html',
                               expired=False,
                               task_name=share_data['task_name'],
                               token=token,
                               qr_data_url=qr_data_url,
                               waypoint_names=waypoint_names,
                               expires_str=expires_str)
    except Exception as e:
        app.logger.error(f"Share page error {token}: {e}")
        return 'Error loading task', 500


@app.route('/share/<token>/taskdata')
def share_taskdata(token):
    """Return task data JSON for the read-only map view."""
    try:
        share_data, err = _load_share(token)
        if err:
            return jsonify({'success': False, 'error': 'expired'}), 410
        return jsonify({
            'success': True,
            'task_name': share_data['task_name'],
            'waypoints': share_data['task_waypoints'],
            'obs_zones': share_data['obs_zones'],
            'options': share_data.get('options', {})
        })
    except Exception as e:
        app.logger.error(f"Share taskdata error {token}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/share/<token>/view')
def share_view(token):
    """Render the task in read-only map view inside the main editor."""
    share_data, err = _load_share(token)
    if err:
        return render_template('share.html', expired=True, task_name='',
                               token=token, qr_data_url=None,
                               waypoint_names=[], expires_str='')
    return render_template('index.html',
                           style_options=STYLE_OPTIONS,
                           view_mode=True,
                           view_token=token,
                           view_task_name=share_data['task_name'])


@app.route('/share/<token>/download')
def share_download(token):
    """Download a task file from a share snapshot."""
    try:
        share_data, err = _load_share(token)
        if err:
            return 'Share link has expired or does not exist', 410

        fmt = request.args.get('format', 'cup').lower()
        task_name = share_data['task_name']
        task_waypoints = [Waypoint.from_dict(d) for d in share_data['task_waypoints']]
        obs_zones = share_data['obs_zones']
        task_options = share_data.get('options', {})

        fmt_map = {
            'tsk': (write_task_tsk, '.tsk', 'application/xml'),
            'xctsk': (write_task_xctsk, '.xctsk', 'application/json'),
            'lkt': (write_task_lkt, '.lkt', 'application/xml'),
        }
        writer, suffix, mimetype = fmt_map.get(fmt, (write_task_cup, '.cup', 'text/plain'))
        content = writer(task_name, task_waypoints, obs_zones, task_options)
        safe_name = task_name.replace(' ', '_')
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=suffix, encoding='utf-8') as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        return send_file(tmp_path, as_attachment=True,
                         download_name=f'{safe_name}{suffix}', mimetype=mimetype)
    except Exception as e:
        app.logger.error(f"Share download error {token}: {e}")
        return 'Error', 500


# ──────────── XCSoar Repository ────────────

def _parse_xcsoar_repo(text):
    """Parse the XCSoar data repository index into a list of dicts."""
    entries = []
    for block in text.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        entry = {}
        for line in block.splitlines():
            if '=' in line:
                k, _, v = line.partition('=')
                entry[k.strip()] = v.strip()
        if entry.get('type') in ('waypoint', 'airspace') and 'uri' in entry:
            entries.append(entry)
    return entries


@app.route('/api/xcsoar-repo')
def xcsoar_repo_index():
    """Return the cached XCSoar repository entry list."""
    global _xcsoar_repo_cache, _xcsoar_repo_cache_ts
    now = _time.time()
    if _xcsoar_repo_cache is not None and (now - _xcsoar_repo_cache_ts) < 3600:
        return jsonify({'entries': _xcsoar_repo_cache})
    try:
        resp = requests.get('https://download.xcsoar.org/repository', timeout=15)
        resp.raise_for_status()
        entries = _parse_xcsoar_repo(resp.text)
        _xcsoar_repo_cache = entries
        _xcsoar_repo_cache_ts = now
        return jsonify({'entries': entries})
    except Exception as e:
        app.logger.error(f'XCSoar repo fetch error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/xcsoar-proxy')
def xcsoar_proxy():
    """Proxy-download a file from the XCSoar repository (allowlist enforced)."""
    global _xcsoar_repo_cache, _xcsoar_repo_cache_ts
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Ensure allowlist is populated
    if _xcsoar_repo_cache is None:
        try:
            resp = requests.get('https://download.xcsoar.org/repository', timeout=15)
            resp.raise_for_status()
            _xcsoar_repo_cache = _parse_xcsoar_repo(resp.text)
            _xcsoar_repo_cache_ts = _time.time()
        except Exception as e:
            app.logger.error(f'XCSoar repo fetch error (proxy): {e}')
            return jsonify({'error': 'Could not fetch repository index'}), 500

    allowed = {e['uri'] for e in _xcsoar_repo_cache}
    if url not in allowed:
        return jsonify({'error': 'URL not in XCSoar repository'}), 403

    try:
        from flask import Response
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        fname = url.split('/')[-1].split('?')[0] or 'download'
        return Response(
            r.content,
            content_type=r.headers.get('content-type', 'text/plain; charset=utf-8'),
            headers={'Content-Disposition': f'attachment; filename="{fname}"'}
        )
    except Exception as e:
        app.logger.error(f'XCSoar proxy error for {url}: {e}')
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)