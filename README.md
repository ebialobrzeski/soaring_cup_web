# Soaring CUP File Editor - Web Application

A modern web-based application for editing and managing waypoint files in SeeYou CUP format, commonly used in soaring and gliding. This application has been converted from a desktop Tkinter application to a full web interface.

## Features

### File Operations
- **Open CUP/CSV files**: Upload and parse waypoint files
- **Save as CUP/CSV**: Download waypoints in either format
- **New file**: Start with an empty waypoint collection

### Waypoint Management
- **Add waypoints**: Create new waypoints with full validation
- **Edit waypoints**: Modify existing waypoint properties
- **Delete waypoints**: Remove selected waypoints
- **Batch operations**: Select multiple waypoints for bulk operations

### Interactive Map
- **Leaflet-based map**: View all waypoints on an interactive OpenStreetMap
- **Click to add**: Add new waypoints by clicking on the map
- **Popup details**: View waypoint information in map popups
- **Auto-fit bounds**: Automatically zoom to show all waypoints

### Data Validation
- **Coordinate validation**: Ensure latitude/longitude are within valid ranges
- **Style codes**: Support for SeeYou waypoint style codes (0-21)
- **Runway data**: Validate runway direction, length, and width formats
- **Elevation fetching**: Automatically fetch elevation data from open-elevation API

### User Interface
- **Responsive design**: Works on desktop, tablet, and mobile devices
- **Sortable table**: Click column headers to sort waypoints
- **Tab navigation**: Switch between list view and map view
- **Real-time status**: Status bar shows current operation and waypoint count

## Installation

### Prerequisites
- Python 3.7 or higher
- pip (Python package installer)

### Setup
1. **Clone or download** the project to your local machine

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Open your browser** and navigate to:
   ```
   http://localhost:5000
   ```

## Usage

### Loading Waypoints
1. Click **"Open File"** button
2. Select a `.cup` or `.csv` file from your computer
3. Waypoints will be loaded and displayed in both the table and map

### Adding Waypoints
1. Click **"Add Waypoint"** button, or
2. Switch to **Map View** and click **"Add Waypoint on Map"**, then click on the map
3. Fill in the waypoint details in the modal form
4. Click **"Save Waypoint"**

### Editing Waypoints
1. Select a waypoint in the table (checkbox)
2. Click **"Edit Selected"** button
3. Modify the waypoint details
4. Click **"Save Waypoint"**

### Saving Waypoints
1. Click **"Save CUP"** or **"Save CSV"** to download the file
2. The file will be downloaded to your default downloads folder

## File Formats

### CUP Format
The application supports the SeeYou CUP format with all standard fields:
- Name (required)
- Code (optional)
- Country (optional)
- Latitude/Longitude (required, decimal degrees)
- Elevation (optional, with units)
- Style (waypoint type, 0-21)
- Runway direction, length, width (for airfields)
- Radio frequency
- Description

### CSV Format
Standard comma-separated values format with the same fields as CUP.

## Technical Details

### Backend (Flask)
- **Flask web framework** with REST API endpoints
- **Session-based storage** for waypoint data
- **File upload/download** handling
- **Elevation API integration** using open-elevation.com
- **Data validation** using the existing Waypoint model

### Frontend
- **HTML5/CSS3/JavaScript** with modern ES6+ features
- **Leaflet maps** for interactive mapping
- **Responsive design** using CSS Grid and Flexbox
- **Font Awesome icons** for a polished interface
- **No external frameworks** - vanilla JavaScript for maximum compatibility

### API Endpoints
- `GET /api/waypoints` - Get all waypoints
- `POST /api/waypoints` - Add new waypoint
- `PUT /api/waypoints/<index>` - Update waypoint
- `DELETE /api/waypoints/<index>` - Delete waypoint
- `POST /api/upload` - Upload CUP/CSV file
- `GET /api/download/<format>` - Download as CUP/CSV
- `GET /api/elevation/<lat>/<lon>` - Fetch elevation data
- `POST /api/clear` - Clear all waypoints

## Project Structure

```
soaring_cup_web/
├── app.py                          # Flask web application
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── backend/                        # Original backend modules
│   └── soaring_cup_file_editor/
│       ├── models.py               # Waypoint data model
│       ├── file_io.py              # CUP/CSV file operations
│       ├── config.py               # Configuration constants
│       └── utils.py                # Utility functions
├── static/                         # Web assets
│   ├── css/
│   │   └── style.css               # Application styles
│   └── js/
│       └── app.js                  # JavaScript application
├── templates/                      # HTML templates
│   └── index.html                  # Main application page
└── uploads/                        # Temporary file storage
```

## Migration from Desktop App

This web application maintains full compatibility with the original desktop Tkinter application:

- **Same data models**: Uses the existing `Waypoint` class and validation
- **Same file I/O**: Reuses the existing CUP/CSV parsing and writing functions
- **Same features**: All functionality from the desktop app is preserved
- **Enhanced UI**: Improved user experience with modern web technologies

## Browser Compatibility

- **Modern browsers**: Chrome 60+, Firefox 60+, Safari 12+, Edge 79+
- **Mobile browsers**: iOS Safari, Chrome Mobile, Samsung Internet
- **Features used**: ES6 classes, async/await, CSS Grid, Flexbox

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project maintains the same license as the original desktop application.

## Support

For issues or questions:
1. Check the browser console for JavaScript errors
2. Check the Flask console for server errors
3. Ensure all required Python packages are installed
4. Verify your browser supports modern JavaScript features