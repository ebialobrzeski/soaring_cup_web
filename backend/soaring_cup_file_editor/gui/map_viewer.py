"""
Map viewer for displaying and interacting with waypoints on an OpenStreetMap.
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
from ..utils import ddmm_to_deg


class MapViewerWindow:
    """Window for viewing waypoints on a map."""
    
    def __init__(self, parent, waypoints: List[Waypoint], on_waypoint_select: Optional[Callable] = None):
        """
        Initialize the map viewer window.
        
        Args:
            parent: Parent window
            waypoints: List of waypoints to display
            on_waypoint_select: Callback when waypoint is selected (receives waypoint)
        """
        self.parent = parent
        self.waypoints = waypoints
        self.on_waypoint_select = on_waypoint_select
        self.markers = {}  # waypoint_name -> marker
        
        if not MAP_AVAILABLE:
            messagebox.showerror(
                "Map Not Available",
                "Map functionality requires 'tkintermapview' package.\n\n"
                "Install it with:\n"
                "pip install tkintermapview"
            )
            return
        
        # Create top-level window
        self.window = tk.Toplevel(parent)
        self.window.title("Waypoint Map Viewer")
        self.window.geometry("1000x700")
        
        self._create_widgets()
        self._load_waypoints()
        
    def _create_widgets(self):
        """Create the map viewer widgets."""
        # Top toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Label(toolbar, text="Map Controls:").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            toolbar,
            text="🔄 Refresh Waypoints",
            command=self._load_waypoints
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            toolbar,
            text="🎯 Fit All Waypoints",
            command=self._fit_all_waypoints
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            toolbar,
            text="🏠 Reset View",
            command=self._reset_view
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Map type selector
        ttk.Label(toolbar, text="Map Type:").pack(side=tk.LEFT, padx=5)
        self.map_type = tk.StringVar(value="OpenStreetMap")
        map_selector = ttk.Combobox(
            toolbar,
            textvariable=self.map_type,
            values=["OpenStreetMap", "Google Normal", "Google Satellite"],
            state="readonly",
            width=20
        )
        map_selector.pack(side=tk.LEFT, padx=2)
        map_selector.bind("<<ComboboxSelected>>", self._change_map_type)
        
        # Info label
        self.info_label = ttk.Label(toolbar, text="")
        self.info_label.pack(side=tk.RIGHT, padx=5)
        
        # Map widget
        self.map_widget = TkinterMapView(self.window, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Set initial position (center of Europe - good default for gliding)
        self.map_widget.set_position(48.0, 11.0)  # Munich area
        self.map_widget.set_zoom(6)
        
        # Add right-click menu for coordinates
        self.map_widget.add_right_click_menu_command(
            label="📍 Get Coordinates",
            command=self._show_coordinates,
            pass_coords=True
        )
        
        self.map_widget.add_right_click_menu_command(
            label="➕ Add Waypoint Here",
            command=self._add_waypoint_at_position,
            pass_coords=True
        )
    
    def _change_map_type(self, event=None):
        """Change the map tile server."""
        map_type = self.map_type.get()
        if map_type == "OpenStreetMap":
            self.map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
        elif map_type == "Google Normal":
            self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
        elif map_type == "Google Satellite":
            self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
    
    def _load_waypoints(self):
        """Load all waypoints onto the map."""
        # Clear existing markers
        for marker in self.markers.values():
            marker.delete()
        self.markers.clear()
        
        if not self.waypoints:
            self.info_label.config(text="No waypoints to display")
            return
        
        # Add markers for each waypoint
        for waypoint in self.waypoints:
            try:
                lat = ddmm_to_deg(waypoint.latitude)
                lon = ddmm_to_deg(waypoint.longitude)
                
                # Determine marker color based on style
                color = self._get_style_color(waypoint.style)
                
                # Create marker
                marker = self.map_widget.set_marker(
                    lat,
                    lon,
                    text=waypoint.name,
                    command=lambda wp=waypoint: self._on_marker_click(wp)
                )
                
                # Store marker reference
                self.markers[waypoint.name] = marker
                
            except Exception as e:
                print(f"Error adding waypoint {waypoint.name}: {e}")
        
        self.info_label.config(text=f"Displaying {len(self.markers)} waypoints")
        
        # Fit all waypoints in view
        if len(self.markers) > 0:
            self._fit_all_waypoints()
    
    def _get_style_color(self, style: Optional[int]) -> str:
        """Get marker color based on waypoint style."""
        if style is None:
            return "gray"
        
        # Style colors based on type
        style_colors = {
            2: "blue",      # Airfield grass
            3: "blue",      # Outlanding
            4: "green",     # Glider site
            5: "red",       # Airfield solid
            6: "orange",    # Mountain pass
            7: "orange",    # Mountain top
            8: "purple",    # Sender
            9: "brown",     # VOR
            10: "brown",    # NDB
            11: "gray",     # Cool tower
            12: "cyan",     # Dam
            13: "green",    # Tunnel
            14: "gray",     # Bridge
            15: "red",      # Power plant
            16: "yellow",   # Castle
            17: "pink",     # Intersection
        }
        
        return style_colors.get(style, "gray")
    
    def _fit_all_waypoints(self):
        """Zoom and pan to show all waypoints."""
        if not self.waypoints:
            return
        
        try:
            lats = []
            lons = []
            
            for waypoint in self.waypoints:
                lat = ddmm_to_deg(waypoint.latitude)
                lon = ddmm_to_deg(waypoint.longitude)
                lats.append(lat)
                lons.append(lon)
            
            if lats and lons:
                # Calculate center and boundaries
                center_lat = (max(lats) + min(lats)) / 2
                center_lon = (max(lons) + min(lons)) / 2
                
                # Set position to center
                self.map_widget.set_position(center_lat, center_lon)
                
                # Calculate appropriate zoom level
                lat_diff = max(lats) - min(lats)
                lon_diff = max(lons) - min(lons)
                max_diff = max(lat_diff, lon_diff)
                
                # Rough zoom calculation
                if max_diff > 10:
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
                else:
                    zoom = 12
                
                self.map_widget.set_zoom(zoom)
                
        except Exception as e:
            print(f"Error fitting waypoints: {e}")
    
    def _reset_view(self):
        """Reset to default view."""
        self.map_widget.set_position(48.0, 11.0)
        self.map_widget.set_zoom(6)
    
    def _on_marker_click(self, waypoint: Waypoint):
        """Handle marker click."""
        # Show waypoint info
        info = f"Selected: {waypoint.name}"
        if waypoint.code:
            info += f" ({waypoint.code})"
        if waypoint.elevation:
            info += f" - {waypoint.elevation}"
        
        self.info_label.config(text=info)
        
        # Call callback if provided
        if self.on_waypoint_select:
            self.on_waypoint_select(waypoint)
    
    def _show_coordinates(self, coords):
        """Show coordinates at clicked position."""
        lat, lon = coords
        message = f"Coordinates:\n\nLatitude: {lat:.6f}\nLongitude: {lon:.6f}"
        messagebox.showinfo("Coordinates", message, parent=self.window)
    
    def _add_waypoint_at_position(self, coords):
        """Placeholder for adding waypoint at clicked position."""
        lat, lon = coords
        message = f"Add new waypoint at:\n\nLat: {lat:.6f}\nLon: {lon:.6f}\n\nThis feature will be implemented soon!"
        messagebox.showinfo("Add Waypoint", message, parent=self.window)
    
    def update_waypoints(self, waypoints: List[Waypoint]):
        """Update the waypoint list and refresh the map."""
        self.waypoints = waypoints
        self._load_waypoints()
    
    def highlight_waypoint(self, waypoint_name: str):
        """Highlight and center on a specific waypoint."""
        for waypoint in self.waypoints:
            if waypoint.name == waypoint_name:
                try:
                    lat = ddmm_to_deg(waypoint.latitude)
                    lon = ddmm_to_deg(waypoint.longitude)
                    self.map_widget.set_position(lat, lon)
                    self.map_widget.set_zoom(13)
                    
                    # Update info
                    self._on_marker_click(waypoint)
                    
                except Exception as e:
                    print(f"Error highlighting waypoint: {e}")
                break


def show_map_viewer(parent, waypoints: List[Waypoint], on_waypoint_select: Optional[Callable] = None):
    """
    Show the map viewer window.
    
    Args:
        parent: Parent window
        waypoints: List of waypoints to display
        on_waypoint_select: Optional callback when waypoint is selected
    
    Returns:
        MapViewerWindow instance or None if map not available
    """
    if not MAP_AVAILABLE:
        return None
    
    return MapViewerWindow(parent, waypoints, on_waypoint_select)
