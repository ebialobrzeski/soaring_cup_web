"""Utility functions for coordinate conversions."""


def ddmm_to_deg(coord_str: str) -> float:
    """
    Convert DDMM.MMM format to decimal degrees.
    
    Args:
        coord_str: Coordinate string in DDMM.MMMX format where X is N/S/E/W
        
    Returns:
        Decimal degrees as float
        
    Example:
        >>> ddmm_to_deg("5245.91404N")
        52.765234
    """
    coord_str = coord_str.strip()
    direction = coord_str[-1]
    coord_str = coord_str[:-1]
    
    # Find where minutes start (after 2 or 3 digits for lat/lon)
    if direction in ['N', 'S']:
        degrees = int(coord_str[:2])
        minutes = float(coord_str[2:])
    else:  # E, W
        degrees = int(coord_str[:3])
        minutes = float(coord_str[3:])
    
    decimal = degrees + (minutes / 60.0)
    
    if direction in ['S', 'W']:
        decimal = -decimal
    
    return decimal


def deg_to_ddmm(value: float, is_lat: bool) -> str:
    """
    Convert decimal degrees to DDMM.MMM format.
    
    Args:
        value: Decimal degrees
        is_lat: True if latitude, False if longitude
        
    Returns:
        Coordinate string in DDMM.MMMX format where X is N/S/E/W
        
    Example:
        >>> deg_to_ddmm(52.765234, True)
        '5245.914N'
    """
    degrees = int(abs(value))
    minutes = (abs(value) - degrees) * 60
    suffix = "N" if is_lat and value >= 0 else "S" if is_lat else "E" if value >= 0 else "W"
    deg_format = "{:02d}" if is_lat else "{:03d}"
    # Use 3 decimal places for minutes per CUP specification
    return f"{deg_format.format(degrees)}{minutes:06.3f}{suffix}"
