"""
Flask web application for Soaring CUP File Editor.
Converts the desktop Tkinter app to a web-based interface.
"""

import os
import json
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from backend.soaring_cup_file_editor.models import Waypoint
from backend.soaring_cup_file_editor.file_io import (
    parse_cup_file, write_cup_file, parse_csv_file, write_csv_file, get_elevation
)
from backend.soaring_cup_file_editor.config import STYLE_OPTIONS

app = Flask(__name__)
app.secret_key = 'soaring_cup_editor_secret_key_change_in_production'
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'cup', 'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_waypoints():
    """Get waypoints from session storage."""
    waypoints_data = session.get('waypoints', [])
    return [Waypoint.from_dict(wp) for wp in waypoints_data]


def set_session_waypoints(waypoints):
    """Store waypoints in session storage."""
    session['waypoints'] = [wp.to_dict() for wp in waypoints]


@app.route('/')
def index():
    """Main application page."""
    return render_template('index.html', style_options=STYLE_OPTIONS)


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
        waypoint = Waypoint.from_dict(data)
        
        waypoints = get_session_waypoints()
        waypoints.append(waypoint)
        set_session_waypoints(waypoints)
        
        return jsonify({'success': True, 'waypoint': waypoint.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/waypoints/<int:index>', methods=['PUT'])
def update_waypoint(index):
    """Update an existing waypoint."""
    try:
        data = request.get_json()
        waypoint = Waypoint.from_dict(data)
        
        waypoints = get_session_waypoints()
        if 0 <= index < len(waypoints):
            waypoints[index] = waypoint
            set_session_waypoints(waypoints)
            return jsonify({'success': True, 'waypoint': waypoint.to_dict()})
        else:
            return jsonify({'success': False, 'error': 'Waypoint index out of range'}), 404
    except Exception as e:
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
        elevation = get_elevation(lat, lon)
        return jsonify({'success': True, 'elevation': elevation})
    except Exception as e:
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
                
                return jsonify({
                    'success': True, 
                    'message': f'Loaded {len(waypoints)} waypoints from {filename}',
                    'waypoints': [wp.to_dict() for wp in waypoints]
                })
                
            except Exception as e:
                # Clean up on error
                if os.path.exists(filepath):
                    os.remove(filepath)
                return jsonify({'success': False, 'error': f'Error parsing file: {str(e)}'}), 400
        
        return jsonify({'success': False, 'error': 'Invalid file type. Only .cup and .csv files are allowed.'}), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download/<file_format>')
def download_file(file_format):
    """Download waypoints as CUP or CSV file."""
    try:
        waypoints = get_session_waypoints()
        if not waypoints:
            return jsonify({'success': False, 'error': 'No waypoints to download'}), 400
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=f'.{file_format}') as tmp_file:
            tmp_path = tmp_file.name
            
            if file_format.lower() == 'cup':
                write_cup_file(waypoints, tmp_path)
                mimetype = 'text/plain'
                filename = session.get('current_filename', 'waypoints.cup')
                if not filename.endswith('.cup'):
                    filename = 'waypoints.cup'
            elif file_format.lower() == 'csv':
                write_csv_file(waypoints, tmp_path)
                mimetype = 'text/csv'
                filename = session.get('current_filename', 'waypoints.csv')
                if not filename.endswith('.csv'):
                    filename = 'waypoints.csv'
            else:
                os.unlink(tmp_path)
                return jsonify({'success': False, 'error': 'Invalid format. Use "cup" or "csv".'}), 400
        
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clear', methods=['POST'])
def clear_waypoints():
    """Clear all waypoints from session."""
    session.pop('waypoints', None)
    session.pop('current_filename', None)
    return jsonify({'success': True, 'message': 'All waypoints cleared'})


@app.route('/api/style-options')
def get_style_options():
    """Get available waypoint style options."""
    return jsonify(STYLE_OPTIONS)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)