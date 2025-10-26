"""
Map tab for displaying and interacting with waypoints on an OpenStreetMap.
Embedded in the main window as a tab.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional, Callable
try:
    from tkintermapview import TkinterMapView
    MAP_AVAILABLE = True
except ImportError:
    MAP_AVAILABLE = False

from ..models import Waypoint
from ..utils import deg_to_ddmm


class MapTab:
    """Map tab for the main window."""
    
    def __init__(self, parent, notebook: ttk.Notebook, on_waypoint_select: Callable,
                 on_waypoint_add: Callable, on_waypoint_edit: Callable):
        """
        Initialize the map tab.
        
        Args:
            parent: Parent window
            notebook: Notebook widget to add tab to
            on_waypoint_select: Callback when waypoint is selected (receives waypoint)
            on_waypoint_add: Callback to add new waypoint (receives lat, lon)
            on_waypoint_edit: Callback to edit waypoint (receives waypoint, new_lat, new_lon)
        """
        self.parent = parent
        self.notebook = notebook
        self.on_waypoint_select = on_waypoint_select
        self.on_waypoint_add = on_waypoint_add
        self.on_waypoint_edit = on_waypoint_edit
        
        self.waypoints: List[Waypoint] = []
        self.markers = {}  # waypoint_name -> marker
        self.selected_marker = None
        self.drag_mode = False
        
        if not MAP_AVAILABLE:
            self._create_unavailable_tab()
            return
        
        # Create map tab
        self.map_frame = ttk.Frame(notebook)
        notebook.add(self.map_frame, text="🗺️ Map View")
        
        self._create_widgets()
        
    def _create_unavailable_tab(self):
        """Create a tab explaining map is not available."""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🗺️ Map View")
        
        msg = ttk.Label(
            frame,
            text="Map functionality requires 'tkintermapview' package.\n\n"
                 "Install it with:\n"
                 "pip install tkintermapview\n\n"
                 "Then restart the application.",
            justify=tk.CENTER,
            font=("Arial", 12)
        )
        msg.pack(expand=True, pady=50)
    
    def _create_widgets(self):
        """Create the map tab widgets."""
        # Top toolbar
        toolbar = ttk.Frame(self.map_frame)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Label(toolbar, text="Map Controls:").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            toolbar,
            text="🎯 Fit All",
            command=self._fit_all_waypoints
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            toolbar,
            text="🔄 Refresh",
            command=self._refresh_markers
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Mode selector
        ttk.Label(toolbar, text="Mode:").pack(side=tk.LEFT, padx=5)
        self.mode = tk.StringVar(value="view")
        
        ttk.Radiobutton(
            toolbar,
            text="👁️ View",
            variable=self.mode,
            value="view",
            command=self._mode_changed
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Radiobutton(
            toolbar,
            text="➕ Add",
            variable=self.mode,
            value="add",
            command=self._mode_changed
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Radiobutton(
            toolbar,
            text="✏️ Edit",
            variable=self.mode,
            value="edit",
            command=self._mode_changed
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Info label
        self.info_label = ttk.Label(toolbar, text="Click 'Fit All' to view waypoints")
        self.info_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Map widget
        self.map_widget = TkinterMapView(self.map_frame, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Set initial position (will be overridden when waypoints load)
        self.map_widget.set_position(48.0, 11.0)  # Central Europe
        self.map_widget.set_zoom(6)
        
        # Bind click events
        self.map_widget.add_left_click_map_command(self._on_map_click)
    
    def _mode_changed(self):
        """Handle mode change."""
        mode = self.mode.get()
        if mode == "view":
            self.info_label.config(text="👁️ VIEW MODE: Click markers to view waypoint information")
            self.selected_marker = None
        elif mode == "add":
            self.info_label.config(text="➕ ADD MODE: Click anywhere on map to add a new waypoint")
            self.selected_marker = None
        elif mode == "edit":
            self.info_label.config(text="✏️ EDIT MODE: Click a marker to open edit dialog")
            self.selected_marker = None
    
    def _on_map_click(self, coords):
        """Handle map click based on current mode."""
        lat, lon = coords
        mode = self.mode.get()
        
        print(f"Map clicked at {lat:.6f}, {lon:.6f} in mode: {mode}")  # Debug
        
        if mode == "add":
            # Add new waypoint at clicked location
            self._add_waypoint_at(lat, lon)
        elif mode == "edit" and self.selected_marker:
            # Move selected waypoint to new location
            self._move_waypoint_to(lat, lon)
    
    def _add_waypoint_at(self, lat: float, lon: float):
        """Add a new waypoint at the specified coordinates."""
        # Convert to DDMM.MMM format for display
        lat_str = deg_to_ddmm(lat, is_lat=True)
        lon_str = deg_to_ddmm(lon, is_lat=False)
        
        self.info_label.config(
            text=f"Adding waypoint at {lat:.6f}, {lon:.6f} - Fetching location name..."
        )
        
        # Try to get location name from reverse geocoding
        location_name = self._get_location_name(lat, lon)
        
        if location_name:
            self.info_label.config(
                text=f"Adding waypoint: {location_name}"
            )
        
        # Call the callback to open add dialog
        self.on_waypoint_add(lat, lon, location_name)
    
    def _get_location_name(self, lat: float, lon: float) -> str:
        """Get location name from coordinates using reverse geocoding."""
        try:
            import requests
            # Use OpenStreetMap Nominatim service for reverse geocoding
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 10,  # City/town level
                "addressdetails": 1
            }
            headers = {
                "User-Agent": "SoaringCUPEditor/3.0"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})
                
                # Try to get the most relevant name
                # Priority: city > town > village > hamlet > suburb
                for key in ["city", "town", "village", "hamlet", "suburb"]:
                    if key in address:
                        return address[key]
                
                # Fallback to display_name
                if "display_name" in data:
                    # Get first part before first comma
                    return data["display_name"].split(",")[0].strip()
            
            return None
        except Exception as e:
            print(f"Error fetching location name: {e}")
            return None
    
    def _move_waypoint_to(self, lat: float, lon: float):
        """Move the selected waypoint to new coordinates."""
        if not self.selected_marker:
            return
        
        # Find the waypoint
        waypoint = None
        for wp in self.waypoints:
            if self.markers.get(wp.name) == self.selected_marker:
                waypoint = wp
                break
        
        if waypoint:
            # Convert to DDMM.MMM format for display
            lat_str = deg_to_ddmm(lat, is_lat=True)
            lon_str = deg_to_ddmm(lon, is_lat=False)
            
            self.info_label.config(
                text=f"Moving '{waypoint.name}' to {lat:.6f}, {lon:.6f}"
            )
            
            # Call the callback to update waypoint
            self.on_waypoint_edit(waypoint, lat, lon)
            
            # Clear selection
            self.selected_marker = None
    
    def load_waypoints(self, waypoints: List[Waypoint]):
        """Load waypoints onto the map."""
        self.waypoints = waypoints
        self._refresh_markers()
        
        # Auto-fit to show all waypoints
        if self.waypoints:
            self._fit_all_waypoints()
    
    def _refresh_markers(self):
        """Refresh all markers on the map."""
        print(f"DEBUG: Refreshing markers for {len(self.waypoints)} waypoints")  # Debug
        
        # Clear existing markers
        for marker in self.markers.values():
            marker.delete()
        self.markers.clear()
        self.selected_marker = None
        
        if not self.waypoints:
            self.info_label.config(text="No waypoints to display")
            return
        
        # Add markers for each waypoint
        for waypoint in self.waypoints:
            try:
                # Coordinates are already in decimal degrees (float)
                lat = waypoint.latitude
                lon = waypoint.longitude
                
                # Determine marker color based on style
                color = self._get_style_color(waypoint.style)
                
                # Create a marker with command that wraps the waypoint
                # We need to capture the waypoint in a closure
                def make_command(wp):
                    def cmd(marker):
                        # Manually set the waypoint data since tkintermapview might not preserve it
                        if not hasattr(marker, 'data') or 'waypoint' not in marker.data:
                            marker.data = {"waypoint": wp}
                        self._on_marker_click(marker)
                    return cmd
                
                marker = self.map_widget.set_marker(
                    lat,
                    lon,
                    text=waypoint.name,
                    text_color="black",
                    font=("Arial", 8),
                    marker_color_circle=color,
                    marker_color_outside=self._darken_color(color),
                    command=make_command(waypoint)
                )
                
                # Store waypoint reference in marker's data attribute
                marker.data = {"waypoint": waypoint}
                
                # Store marker reference
                self.markers[waypoint.name] = marker
                
                print(f"DEBUG: Added marker for {waypoint.name}")  # Debug
                
            except Exception as e:
                print(f"Error adding waypoint {waypoint.name}: {e}")
                
                # Store marker reference
                self.markers[waypoint.name] = marker
                
            except Exception as e:
                print(f"Error adding waypoint {waypoint.name}: {e}")
        
        count = len(self.markers)
        self.info_label.config(text=f"Displaying {count} waypoint{'s' if count != 1 else ''}")
    
    def _get_style_color(self, style: Optional[int]) -> str:
        """Get marker color based on waypoint style."""
        if style is None:
            return "gray"
        
        # Style colors based on type
        style_colors = {
            2: "#2196F3",    # Airfield grass - blue
            3: "#2196F3",    # Outlanding - blue
            4: "#4CAF50",    # Glider site - green
            5: "#1976D2",    # Airfield solid - dark blue
            6: "#FF9800",    # Mountain pass - orange
            7: "#FF9800",    # Mountain top - orange
            8: "#9C27B0",    # Sender - purple
            9: "#795548",    # VOR - brown
            10: "#795548",   # NDB - brown
            11: "#757575",   # Cool tower - gray
            12: "#00BCD4",   # Dam - cyan
            13: "#4CAF50",   # Tunnel - green
            14: "#757575",   # Bridge - gray
            15: "#F44336",   # Power plant - red
            16: "#FFEB3B",   # Castle - yellow
            17: "#E91E63",   # Intersection - pink
        }
        
        return style_colors.get(style, "#757575")  # Default gray
    
    def _darken_color(self, hex_color: str) -> str:
        """Darken a hex color for marker outline."""
        if not hex_color.startswith("#"):
            return "#000000"
        
        try:
            # Remove # and convert to RGB
            hex_color = hex_color.lstrip("#")
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            
            # Darken by 30%
            r = int(r * 0.7)
            g = int(g * 0.7)
            b = int(b * 0.7)
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return "#000000"
    
    def _fit_all_waypoints(self):
        """Zoom and pan to show all waypoints."""
        if not self.waypoints:
            messagebox.showinfo("No Waypoints", "No waypoints to display on map.")
            return
        
        try:
            lats = []
            lons = []
            
            for waypoint in self.waypoints:
                # Coordinates are already in decimal degrees (float)
                lat = waypoint.latitude
                lon = waypoint.longitude
                lats.append(lat)
                lons.append(lon)
            
            if lats and lons:
                # Calculate center
                center_lat = (max(lats) + min(lats)) / 2
                center_lon = (max(lons) + min(lons)) / 2
                
                # Set position to center
                self.map_widget.set_position(center_lat, center_lon)
                
                # Calculate appropriate zoom level based on spread
                lat_diff = max(lats) - min(lats)
                lon_diff = max(lons) - min(lons)
                max_diff = max(lat_diff, lon_diff)
                
                # Rough zoom calculation (adjust these values for better fit)
                if max_diff > 20:
                    zoom = 5
                elif max_diff > 10:
                    zoom = 6
                elif max_diff > 5:
                    zoom = 7
                elif max_diff > 2:
                    zoom = 8
                elif max_diff > 1:
                    zoom = 9
                elif max_diff > 0.5:
                    zoom = 10
                elif max_diff > 0.2:
                    zoom = 11
                elif max_diff > 0.1:
                    zoom = 12
                else:
                    zoom = 13
                
                self.map_widget.set_zoom(zoom)
                
                self.info_label.config(
                    text=f"Showing {len(self.waypoints)} waypoints (center: {center_lat:.4f}, {center_lon:.4f})"
                )
                
        except Exception as e:
            messagebox.showerror("Map Error", f"Error fitting waypoints to view:\n{str(e)}")
            print(f"Error fitting waypoints: {e}")
    
    def _on_marker_click(self, marker):
        """Handle marker click based on mode."""
        # Extract waypoint from marker's data
        if not hasattr(marker, 'data') or 'waypoint' not in marker.data:
            print(f"Error: Marker has no waypoint data")
            return
        
        waypoint = marker.data['waypoint']
        mode = self.mode.get()
        
        print(f"Marker clicked: {waypoint.name} in mode: {mode}")  # Debug
        
        if mode == "view":
            # Show read-only info popup
            self._show_waypoint_info(waypoint)
            
        elif mode == "edit":
            # Open full edit dialog through callback
            self.on_waypoint_select(waypoint)
    
    def _show_waypoint_info(self, waypoint: Waypoint):
        """Show a read-only popup with waypoint information."""
        info_lines = []
        info_lines.append(f"Name: {waypoint.name}")
        
        if waypoint.code:
            info_lines.append(f"Code: {waypoint.code}")
        
        if waypoint.country:
            info_lines.append(f"Country: {waypoint.country}")
        
        info_lines.append(f"Latitude: {waypoint.latitude:.6f}°")
        info_lines.append(f"Longitude: {waypoint.longitude:.6f}°")
        
        if waypoint.elevation:
            info_lines.append(f"Elevation: {waypoint.elevation}")
        
        # Get style label
        from ..config import STYLE_OPTIONS
        style_label = STYLE_OPTIONS.get(waypoint.style, 'Unknown')
        info_lines.append(f"Type: {style_label}")
        
        if waypoint.runway_direction:
            info_lines.append(f"Runway Direction: {waypoint.runway_direction}")
        
        if waypoint.runway_length:
            info_lines.append(f"Runway Length: {waypoint.runway_length}")
        
        if waypoint.runway_width:
            info_lines.append(f"Runway Width: {waypoint.runway_width}")
        
        if waypoint.frequency:
            info_lines.append(f"Frequency: {waypoint.frequency}")
        
        if waypoint.description:
            info_lines.append(f"\nDescription:\n{waypoint.description}")
        
        info_text = "\n".join(info_lines)
        
        # Update info label with brief summary
        brief = f"Viewing: {waypoint.name}"
        if waypoint.elevation:
            brief += f" ({waypoint.elevation})"
        self.info_label.config(text=brief)
        
        # Show popup dialog
        messagebox.showinfo(f"Waypoint: {waypoint.name}", info_text, parent=self.parent)
    
    def highlight_waypoint(self, waypoint_name: str):
        """Highlight and center on a specific waypoint."""
        for waypoint in self.waypoints:
            if waypoint.name == waypoint_name:
                try:
                    # Coordinates are already in decimal degrees (float)
                    lat = waypoint.latitude
                    lon = waypoint.longitude
                    self.map_widget.set_position(lat, lon)
                    self.map_widget.set_zoom(13)
                    
                    # Update info
                    info = f"Centered on: {waypoint.name}"
                    if waypoint.elevation:
                        info += f" ({waypoint.elevation})"
                    self.info_label.config(text=info)
                    
                except Exception as e:
                    print(f"Error highlighting waypoint: {e}")
                break
    
    def update_waypoint(self, old_name: str, updated_waypoint: Waypoint):
        """Update a waypoint's position on the map."""
        # Find and update in waypoint list
        for i, wp in enumerate(self.waypoints):
            if wp.name == old_name:
                self.waypoints[i] = updated_waypoint
                break
        
        # Refresh markers
        self._refresh_markers()
    
    def add_waypoint_marker(self, waypoint: Waypoint):
        """Add a single waypoint marker to the map."""
        if waypoint not in self.waypoints:
            self.waypoints.append(waypoint)
        
        self._refresh_markers()
        self.highlight_waypoint(waypoint.name)
    
    def remove_waypoint_marker(self, waypoint_name: str):
        """Remove a waypoint marker from the map."""
        # Remove from waypoint list
        self.waypoints = [wp for wp in self.waypoints if wp.name != waypoint_name]
        
        # Refresh markers
        self._refresh_markers()


def create_map_tab(parent, notebook: ttk.Notebook, on_waypoint_select: Callable,
                   on_waypoint_add: Callable, on_waypoint_edit: Callable) -> Optional[MapTab]:
    """
    Create and add a map tab to the notebook.
    
    Args:
        parent: Parent window
        notebook: Notebook widget to add tab to
        on_waypoint_select: Callback when waypoint is selected
        on_waypoint_add: Callback to add new waypoint
        on_waypoint_edit: Callback to edit waypoint
    
    Returns:
        MapTab instance or None if map not available
    """
    return MapTab(parent, notebook, on_waypoint_select, on_waypoint_add, on_waypoint_edit)
