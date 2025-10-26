"""
Data models for soaring waypoints.
"""

class Waypoint:
    """A soaring waypoint with all CUP format fields."""
    
    def __init__(self, name='', code='', country='', latitude=0.0, longitude=0.0,
                 elevation=0, style=1, runway_direction=0, runway_length=0,
                 frequency='', description=''):
        self.name = name
        self.code = code
        self.country = country
        self.latitude = float(latitude) if latitude else 0.0
        self.longitude = float(longitude) if longitude else 0.0
        self.elevation = int(elevation) if elevation else 0
        self.style = int(style) if style else 1
        self.runway_direction = int(runway_direction) if runway_direction else 0
        self.runway_length = int(runway_length) if runway_length else 0
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
        
        # Format runway
        runway = f"{self.runway_direction:03d}{self.runway_length:04d}" if self.runway_direction or self.runway_length else ""
        
        return f'"{self.name}","{self.code}","{self.country}",{lat_str},{lon_str},{self.elevation}m,{self.style},{runway},"{self.frequency}","{self.description}"'