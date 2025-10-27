"""
Flask web application for Soaring CUP File Editor.
Converts the desktop Tkinter app to a web-based interface.
"""

import os
import json
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from backend.models import Waypoint
from backend.file_io import (
    parse_cup_file, write_cup_file, parse_csv_file, write_csv_file, get_elevation
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


def get_session_data_file():
    """Get the path to the session data file."""
    session_id = session.get('session_id')
    if not session_id:
        import uuid
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
    """Store waypoints in session storage."""
    try:
        data_file = get_session_data_file()
        data = {
            'waypoints': [wp.to_dict() for wp in waypoints],
            'current_filename': session.get('current_filename', '')
        }
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app.logger.error(f"Error saving session data: {e}")


@app.route('/')
def index():
    """Main application page."""
    return render_template('index.html', style_options=STYLE_OPTIONS)


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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)