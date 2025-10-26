"""Dialog windows for the Soaring CUP Editor."""

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional, Callable

from ..config import STYLE_OPTIONS, STYLE_LABELS, LATITUDE_MIN, LATITUDE_MAX, LONGITUDE_MIN, LONGITUDE_MAX
from ..models import Waypoint


class WaypointDialog:
    """Dialog for adding or editing a waypoint with full CUP field support."""
    
    def __init__(self, parent: tk.Tk, waypoint: Optional[Waypoint] = None, 
                 on_save: Optional[Callable[[Waypoint], None]] = None):
        """
        Initialize the waypoint dialog.
        
        Args:
            parent: Parent window
            waypoint: Existing waypoint to edit (None for new waypoint)
            on_save: Callback function to call when waypoint is saved
        """
        self.parent = parent
        self.waypoint = waypoint
        self.on_save = on_save
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Edit Waypoint" if waypoint else "Add Waypoint")
        self.dialog.geometry("500x450")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._create_widgets()
        
        # Bind keyboard shortcuts
        self.dialog.bind('<Return>', lambda e: self._save())
        self.dialog.bind('<Escape>', lambda e: self.dialog.destroy())
        
        # Center dialog on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
    
    def _create_widgets(self):
        """Create dialog widgets with tabbed interface."""
        # Create notebook (tabbed interface)
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Basic Information
        basic_frame = ttk.Frame(notebook)
        notebook.add(basic_frame, text="Basic Info")
        self._create_basic_tab(basic_frame)
        
        # Tab 2: Airfield/Runway Information
        runway_frame = ttk.Frame(notebook)
        notebook.add(runway_frame, text="Airfield Info")
        self._create_runway_tab(runway_frame)
        
        # Tab 3: Additional Details
        details_frame = ttk.Frame(notebook)
        notebook.add(details_frame, text="Details")
        self._create_details_tab(details_frame)
        
        # Buttons at bottom
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(pady=10)
        
        save_btn = tk.Button(button_frame, text="Save", command=self._save, width=12)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="Cancel", command=self.dialog.destroy, width=12)
        cancel_btn.pack(side=tk.LEFT, padx=5)
    
    def _create_basic_tab(self, parent):
        """Create basic information tab."""
        row = 0
        
        # Name (required)
        tk.Label(parent, text="Name: *", font=('Arial', 9, 'bold')).grid(
            row=row, column=0, sticky='e', padx=5, pady=5
        )
        self.name_entry = tk.Entry(parent, width=40)
        self.name_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky='ew')
        row += 1
        
        # Code
        tk.Label(parent, text="Code:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        self.code_entry = tk.Entry(parent, width=15)
        self.code_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(e.g., EPBK for airports)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Country
        tk.Label(parent, text="Country:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        self.country_entry = tk.Entry(parent, width=15)
        self.country_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(2-letter code, e.g., PL, US)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Clipboard paste button
        paste_btn = tk.Button(parent, text="📋 Paste from Clipboard", command=self._paste_google_coords)
        paste_btn.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(Paste: lat, lon)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Latitude (required)
        tk.Label(parent, text="Latitude: *", font=('Arial', 9, 'bold')).grid(
            row=row, column=0, sticky='e', padx=5, pady=5
        )
        self.lat_entry = tk.Entry(parent, width=20)
        self.lat_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(decimal degrees, e.g., 52.765234)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Longitude (required)
        tk.Label(parent, text="Longitude: *", font=('Arial', 9, 'bold')).grid(
            row=row, column=0, sticky='e', padx=5, pady=5
        )
        self.lon_entry = tk.Entry(parent, width=20)
        self.lon_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(decimal degrees, e.g., 23.186700)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Elevation
        tk.Label(parent, text="Elevation:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        elev_frame = tk.Frame(parent)
        elev_frame.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        self.elev_entry = tk.Entry(elev_frame, width=12)
        self.elev_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.elev_unit_var = tk.StringVar(value="m")
        elev_unit_menu = ttk.Combobox(
            elev_frame, 
            textvariable=self.elev_unit_var, 
            values=["m", "ft"], 
            state="readonly", 
            width=5
        )
        elev_unit_menu.pack(side=tk.LEFT)
        tk.Label(parent, text="(leave empty to auto-fetch)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Style
        tk.Label(parent, text="Style:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        self.style_var = tk.StringVar()
        self.style_menu = ttk.Combobox(
            parent, 
            textvariable=self.style_var, 
            values=list(STYLE_OPTIONS.values()), 
            state="readonly", 
            width=30
        )
        self.style_menu.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky='ew')
        row += 1
        
        # Configure grid weights
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        
        # Prefill if editing
        if self.waypoint:
            self.name_entry.insert(0, self.waypoint.name)
            self.code_entry.insert(0, self.waypoint.code)
            self.country_entry.insert(0, self.waypoint.country)
            self.lat_entry.insert(0, str(self.waypoint.latitude))
            self.lon_entry.insert(0, str(self.waypoint.longitude))
            if self.waypoint.elevation is not None:
                # Parse elevation value and unit
                elev_str = str(self.waypoint.elevation)
                if 'ft' in elev_str.lower():
                    elev_value = elev_str.lower().replace('ft', '').strip()
                    self.elev_entry.insert(0, elev_value)
                    self.elev_unit_var.set('ft')
                elif 'm' in elev_str.lower():
                    elev_value = elev_str.lower().replace('m', '').strip()
                    self.elev_entry.insert(0, elev_value)
                    self.elev_unit_var.set('m')
                else:
                    # No unit specified, assume meters
                    self.elev_entry.insert(0, elev_str)
                    self.elev_unit_var.set('m')
            self.style_menu.set(STYLE_OPTIONS.get(self.waypoint.style, "Waypoint"))
        else:
            self.style_menu.set("Waypoint")
        
        # Focus on name entry
        self.name_entry.focus()
    
    def _create_runway_tab(self, parent):
        """Create airfield/runway information tab."""
        row = 0
        
        tk.Label(parent, text="Airfield & Runway Information", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, pady=10
        )
        row += 1
        
        # Runway Direction
        tk.Label(parent, text="Runway Direction:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        self.rwdir_entry = tk.Entry(parent, width=20)
        self.rwdir_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(3-digit heading: 070, 180, 270 or PG: 115.050)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Runway Length
        tk.Label(parent, text="Runway Length:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        rwlen_frame = tk.Frame(parent)
        rwlen_frame.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        self.rwlen_entry = tk.Entry(rwlen_frame, width=12)
        self.rwlen_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.rwlen_unit_var = tk.StringVar(value="m")
        rwlen_unit_menu = ttk.Combobox(
            rwlen_frame, 
            textvariable=self.rwlen_unit_var, 
            values=["m", "nm", "ml"], 
            state="readonly", 
            width=5
        )
        rwlen_unit_menu.pack(side=tk.LEFT)
        tk.Label(parent, text="(m=meters, nm=nautical miles, ml=statute miles)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Runway Width
        tk.Label(parent, text="Runway Width:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        rwwidth_frame = tk.Frame(parent)
        rwwidth_frame.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        self.rwwidth_entry = tk.Entry(rwwidth_frame, width=12)
        self.rwwidth_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.rwwidth_unit_var = tk.StringVar(value="m")
        rwwidth_unit_menu = ttk.Combobox(
            rwwidth_frame, 
            textvariable=self.rwwidth_unit_var, 
            values=["m", "nm", "ml"], 
            state="readonly", 
            width=5
        )
        rwwidth_unit_menu.pack(side=tk.LEFT)
        tk.Label(parent, text="(m=meters, nm=nautical miles, ml=statute miles)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Frequency
        tk.Label(parent, text="Radio Frequency:").grid(row=row, column=0, sticky='e', padx=5, pady=5)
        self.freq_entry = tk.Entry(parent, width=20)
        self.freq_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        tk.Label(parent, text="(MHz, e.g., 122.500)", font=('Arial', 8), fg='gray').grid(
            row=row, column=2, padx=5, pady=5, sticky='w'
        )
        row += 1
        
        # Configure grid weights
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        
        # Prefill if editing
        if self.waypoint:
            self.rwdir_entry.insert(0, self.waypoint.runway_direction)
            # Parse runway length value and unit
            rwlen_str = self.waypoint.runway_length
            if rwlen_str:
                if 'nm' in rwlen_str.lower():
                    rwlen_value = rwlen_str.lower().replace('nm', '').strip()
                    self.rwlen_entry.insert(0, rwlen_value)
                    self.rwlen_unit_var.set('nm')
                elif 'ml' in rwlen_str.lower():
                    rwlen_value = rwlen_str.lower().replace('ml', '').strip()
                    self.rwlen_entry.insert(0, rwlen_value)
                    self.rwlen_unit_var.set('ml')
                elif 'm' in rwlen_str.lower():
                    rwlen_value = rwlen_str.lower().replace('m', '').strip()
                    self.rwlen_entry.insert(0, rwlen_value)
                    self.rwlen_unit_var.set('m')
                else:
                    # No unit specified, assume meters
                    self.rwlen_entry.insert(0, rwlen_str)
                    self.rwlen_unit_var.set('m')
            # Parse runway width value and unit
            rwwidth_str = self.waypoint.runway_width
            if rwwidth_str:
                if 'nm' in rwwidth_str.lower():
                    rwwidth_value = rwwidth_str.lower().replace('nm', '').strip()
                    self.rwwidth_entry.insert(0, rwwidth_value)
                    self.rwwidth_unit_var.set('nm')
                elif 'ml' in rwwidth_str.lower():
                    rwwidth_value = rwwidth_str.lower().replace('ml', '').strip()
                    self.rwwidth_entry.insert(0, rwwidth_value)
                    self.rwwidth_unit_var.set('ml')
                elif 'm' in rwwidth_str.lower():
                    rwwidth_value = rwwidth_str.lower().replace('m', '').strip()
                    self.rwwidth_entry.insert(0, rwwidth_value)
                    self.rwwidth_unit_var.set('m')
                else:
                    # No unit specified, assume meters
                    self.rwwidth_entry.insert(0, rwwidth_str)
                    self.rwwidth_unit_var.set('m')
            self.freq_entry.insert(0, self.waypoint.frequency)
    
    def _create_details_tab(self, parent):
        """Create additional details tab."""
        row = 0
        
        tk.Label(parent, text="Additional Information", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=2, pady=10
        )
        row += 1
        
        # Description
        tk.Label(parent, text="Description:", anchor='nw').grid(
            row=row, column=0, sticky='ne', padx=5, pady=5
        )
        
        # Text widget with scrollbar for description
        desc_frame = tk.Frame(parent)
        desc_frame.grid(row=row, column=1, padx=5, pady=5, sticky='nsew')
        
        self.desc_text = tk.Text(desc_frame, width=40, height=10, wrap=tk.WORD)
        desc_scrollbar = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=self.desc_text.yview)
        self.desc_text.configure(yscrollcommand=desc_scrollbar.set)
        
        self.desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        row += 1
        
        tk.Label(parent, text="Free text description or notes", font=('Arial', 8), fg='gray').grid(
            row=row, column=1, padx=5, pady=(0, 5), sticky='w'
        )
        
        # Configure grid weights
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # Prefill if editing
        if self.waypoint and self.waypoint.description:
            self.desc_text.insert('1.0', self.waypoint.description)
    
    def _paste_google_coords(self):
        """Paste and parse coordinates from Google Maps format (lat, lon)."""
        try:
            # Get clipboard content
            clipboard_text = self.dialog.clipboard_get().strip()
            
            # Try to parse "lat, lon" format
            parts = clipboard_text.split(',')
            if len(parts) == 2:
                lat_str = parts[0].strip()
                lon_str = parts[1].strip()
                
                # Try to convert to float to validate
                lat = float(lat_str)
                lon = float(lon_str)
                
                # Check if in valid range
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    # Clear existing values and insert new ones
                    self.lat_entry.delete(0, tk.END)
                    self.lat_entry.insert(0, lat_str)
                    self.lon_entry.delete(0, tk.END)
                    self.lon_entry.insert(0, lon_str)
                    
                    messagebox.showinfo(
                        "Coordinates Pasted",
                        f"Latitude: {lat}\nLongitude: {lon}",
                        parent=self.dialog
                    )
                else:
                    messagebox.showerror(
                        "Invalid Coordinates",
                        f"Coordinates out of range:\nLat: {lat} (must be -90 to 90)\nLon: {lon} (must be -180 to 180)",
                        parent=self.dialog
                    )
            else:
                messagebox.showerror(
                    "Invalid Format",
                    f"Expected format: latitude, longitude\nExample: 53.57765449192929, 23.105890054191562\n\nFound: {clipboard_text}",
                    parent=self.dialog
                )
        except ValueError as e:
            messagebox.showerror(
                "Parse Error",
                f"Could not parse coordinates from clipboard.\nExpected format: latitude, longitude\nExample: 53.57765449192929, 23.105890054191562",
                parent=self.dialog
            )
        except tk.TclError:
            messagebox.showerror(
                "Clipboard Error",
                "Could not access clipboard. Please copy coordinates first.",
                parent=self.dialog
            )
    
    def _save(self):
        """Validate and save the waypoint."""
        # Get basic values
        name = self.name_entry.get().strip()
        code = self.code_entry.get().strip()
        country = self.country_entry.get().strip().upper()
        lat_text = self.lat_entry.get().strip()
        lon_text = self.lon_entry.get().strip()
        elev_text = self.elev_entry.get().strip()
        style_label = self.style_var.get()
        
        # Get runway values
        rwdir = self.rwdir_entry.get().strip()
        rwlen_text = self.rwlen_entry.get().strip()
        # Combine runway length with unit
        if rwlen_text:
            try:
                rwlen_value = float(rwlen_text)
                rwlen_unit = self.rwlen_unit_var.get()
                rwlen = f"{rwlen_value}{rwlen_unit}"
            except ValueError:
                messagebox.showerror("Invalid Input", "Runway length must be a number", parent=self.dialog)
                return
        else:
            rwlen = ""
        
        rwwidth_text = self.rwwidth_entry.get().strip()
        # Combine runway width with unit
        if rwwidth_text:
            try:
                rwwidth_value = float(rwwidth_text)
                rwwidth_unit = self.rwwidth_unit_var.get()
                rwwidth = f"{rwwidth_value}{rwwidth_unit}"
            except ValueError:
                messagebox.showerror("Invalid Input", "Runway width must be a number", parent=self.dialog)
                return
        else:
            rwwidth = ""
        
        freq = self.freq_entry.get().strip()
        
        # Get description
        desc = self.desc_text.get('1.0', tk.END).strip()
        
        # Validation
        if not name:
            messagebox.showerror("Invalid Input", "Name cannot be empty", parent=self.dialog)
            return
        
        if not lat_text or not lon_text:
            messagebox.showerror("Invalid Input", "Latitude and Longitude cannot be empty", parent=self.dialog)
            return
        
        try:
            lat = float(lat_text)
            lon = float(lon_text)
        except ValueError:
            messagebox.showerror(
                "Invalid Input", 
                "Latitude and Longitude must be valid numbers (e.g., 52.7652, 23.1867)",
                parent=self.dialog
            )
            return
        
        # Parse elevation if provided
        elev = None
        if elev_text:
            try:
                elev_value = float(elev_text)
                elev_unit = self.elev_unit_var.get()
                elev = f"{elev_value}{elev_unit}"
            except ValueError:
                messagebox.showerror("Invalid Input", "Elevation must be a number", parent=self.dialog)
                return
        
        style_code = STYLE_LABELS.get(style_label, 1)
        
        # Create or update waypoint (validation happens in __post_init__)
        try:
            if self.waypoint:
                # Update existing waypoint
                self.waypoint.name = name
                self.waypoint.code = code
                self.waypoint.country = country
                self.waypoint.latitude = lat
                self.waypoint.longitude = lon
                self.waypoint.elevation = elev
                self.waypoint.style = style_code
                self.waypoint.runway_direction = rwdir
                self.waypoint.runway_length = rwlen
                self.waypoint.runway_width = rwwidth
                self.waypoint.frequency = freq
                self.waypoint.description = desc
                # Re-validate
                self.waypoint.__post_init__()
                self.result = self.waypoint
            else:
                # Create new waypoint
                self.result = Waypoint(
                    name=name,
                    code=code,
                    country=country,
                    latitude=lat,
                    longitude=lon,
                    elevation=elev,
                    style=style_code,
                    runway_direction=rwdir,
                    runway_length=rwlen,
                    runway_width=rwwidth,
                    frequency=freq,
                    description=desc
                )
        except ValueError as e:
            messagebox.showerror("Validation Error", str(e), parent=self.dialog)
            return
        
        # Call callback if provided
        if self.on_save:
            self.on_save(self.result)
        
        self.dialog.destroy()
    
    def show(self) -> Optional[Waypoint]:
        """
        Show the dialog and wait for result.
        
        Returns:
            Waypoint object if saved, None if cancelled
        """
        self.dialog.wait_window()
        return self.result
