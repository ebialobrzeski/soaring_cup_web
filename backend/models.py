"""
Data models for soaring waypoints.
"""
import re

class Waypoint:
    """A soaring waypoint with all CUP format fields."""
    
    @staticmethod
    def _parse_numeric_with_unit(value):
        """Parse numeric value that may include units (e.g., '1350m', '30.0m', or just '1350')."""
        if not value:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        # Remove all non-numeric characters except decimal point and minus
        numeric_str = re.sub(r'[^\d.-]', '', str(value))
        try:
            return int(float(numeric_str)) if numeric_str else 0
        except (ValueError, AttributeError):
            return 0
    
    def __init__(self, name='', code='', country='', latitude=0.0, longitude=0.0,
                 elevation=0, style=1, runway_direction=0, runway_length=0,
                 runway_width=0, frequency='', description=''):
        self.name = name
        self.code = code
        self.country = country
        self.latitude = float(latitude) if latitude else 0.0
        self.longitude = float(longitude) if longitude else 0.0
        self.elevation = self._parse_numeric_with_unit(elevation)
        self.style = int(style) if style else 1
        self.runway_direction = self._parse_numeric_with_unit(runway_direction)
        self.runway_length = self._parse_numeric_with_unit(runway_length)
        self.runway_width = self._parse_numeric_with_unit(runway_width)
        self.frequency = str(frequency) if frequency else ''
        self.description = str(description) if description else ''
    
    def to_dict(self):
        """Convert waypoint to dictionary."""
        return {
            'name': self.name,
            'code': self.code,
            'country': self.country,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'elevation': self.elevation,
            'style': self.style,
            'runway_direction': self.runway_direction,
            'runway_length': self.runway_length,
            'runway_width': self.runway_width,
            'frequency': self.frequency,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create waypoint from dictionary."""
        return cls(
            name=data.get('name', ''),
            code=data.get('code', ''),
            country=data.get('country', ''),
            latitude=data.get('latitude', 0.0),
            longitude=data.get('longitude', 0.0),
            elevation=data.get('elevation', 0),
            style=data.get('style', 1),
            runway_direction=data.get('runway_direction', 0),
            runway_length=data.get('runway_length', 0),
            runway_width=data.get('runway_width', 0),
            frequency=data.get('frequency', ''),
            description=data.get('description', '')
        )
    
    def to_cup_string(self):
        """Convert waypoint to CUP format string."""
        # Format coordinates
        lat_deg = int(abs(self.latitude))
        lat_min = (abs(self.latitude) - lat_deg) * 60
        lat_dir = 'N' if self.latitude >= 0 else 'S'
        lat_str = f"{lat_deg:02d}{lat_min:06.3f}{lat_dir}"
        
        lon_deg = int(abs(self.longitude))
        lon_min = (abs(self.longitude) - lon_deg) * 60
        lon_dir = 'E' if self.longitude >= 0 else 'W'
        lon_str = f"{lon_deg:03d}{lon_min:06.3f}{lon_dir}"
        
        # Format runway (use modern format with separate fields and units)
        rwdir = str(self.runway_direction) if self.runway_direction else ""
        rwlen = f"{self.runway_length}.0m" if self.runway_length else ""
        rwwidth = f"{self.runway_width}.0m" if self.runway_width else ""
        
        return f'"{self.name}","{self.code}","{self.country}",{lat_str},{lon_str},{self.elevation}m,{self.style},{rwdir},{rwlen},{rwwidth},"{self.frequency}","{self.description}"'