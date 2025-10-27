"""
File I/O operations for CUP and CSV waypoint files.
"""

import re
import csv
import io
import requests
from .models import Waypoint


def parse_coordinate(coord_str):
    """Parse CUP coordinate format to decimal degrees."""
    # Remove any whitespace
    coord_str = coord_str.strip()
    
    # Pattern for CUP coordinates: DDmm.mmmD (where D is N/S/E/W)
    match = re.match(r'(\d{2,3})(\d{2})\.(\d{3})([NSEW])', coord_str)
    if not match:
        return 0.0
    
    degrees = int(match.group(1))
    minutes = int(match.group(2))
    decimals = int(match.group(3))
    direction = match.group(4)
    
    # Convert to decimal degrees
    decimal_degrees = degrees + (minutes + decimals / 1000.0) / 60.0
    
    # Apply direction
    if direction in ['S', 'W']:
        decimal_degrees = -decimal_degrees
    
    return decimal_degrees


def format_coordinate(decimal_degrees, is_longitude=False):
    """Format decimal degrees to CUP coordinate format."""
    abs_deg = abs(decimal_degrees)
    degrees = int(abs_deg)
    minutes = (abs_deg - degrees) * 60
    
    if is_longitude:
        if decimal_degrees >= 0:
            return f"{degrees:03d}{minutes:06.3f}E"
        else:
            return f"{degrees:03d}{minutes:06.3f}W"
    else:
        if decimal_degrees >= 0:
            return f"{degrees:02d}{minutes:06.3f}N"
        else:
            return f"{degrees:02d}{minutes:06.3f}S"


def parse_cup_file(file_path):
    """Parse CUP file and return list of waypoints."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    waypoints = []
    lines = content.strip().split('\n')
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('name,code'):  # Skip header
            continue
        
        try:
            # Parse CSV-like format with quoted fields
            reader = csv.reader([line])
            fields = next(reader)
            
            if len(fields) < 6:
                continue
            
            # Extract fields
            name = fields[0] if len(fields) > 0 else ''
            code = fields[1] if len(fields) > 1 else ''
            country = fields[2] if len(fields) > 2 else ''
            
            # Parse coordinates
            latitude = parse_coordinate(fields[3]) if len(fields) > 3 else 0.0
            longitude = parse_coordinate(fields[4]) if len(fields) > 4 else 0.0
            
            # Parse elevation - use helper function to handle units
            elevation_str = fields[5] if len(fields) > 5 else '0'
            try:
                # Remove units but keep decimal point
                elevation = int(float(re.sub(r'[^\d.-]', '', elevation_str))) if elevation_str else 0
            except (ValueError, AttributeError):
                elevation = 0
            
            # Parse style
            style = int(fields[6]) if len(fields) > 6 and fields[6] else 1
            
            # Parse runway info - CUP format can have two variants:
            # Variant 1 (old): Single field with DDDLLLLWWW format (10 digits) or DDDLLLL (7 digits)
            # Variant 2 (new): Three separate fields: rwdir (number), rwlen (with unit like "1350.0m"), rwwidth (with unit like "30.0m")
            runway_direction = 0
            runway_length = 0
            runway_width = 0
            frequency = ''
            description = ''
            
            # Check if we have runway data and determine format
            if len(fields) > 7 and fields[7]:
                runway_str = fields[7].strip()
                
                # Check if field 8 contains units (this determines the format)
                # New format has: field7=number, field8=length with unit, field9=width with unit
                has_units_in_field8 = len(fields) > 8 and fields[8] and ('m' in fields[8].lower() or 'ft' in fields[8].lower() or 'nm' in fields[8].lower())
                
                if has_units_in_field8:
                    # New format: separate fields
                    # Field 7 = rwdir (direction, just a number)
                    try:
                        runway_direction = int(float(runway_str)) if runway_str else 0
                    except (ValueError, AttributeError):
                        runway_direction = 0
                    
                    # Field 8 = rwlen (length with unit like "1350.0m")
                    if len(fields) > 8 and fields[8]:
                        try:
                            runway_length = int(float(re.sub(r'[^\d.]', '', fields[8])))
                        except (ValueError, AttributeError):
                            runway_length = 0
                    
                    # Field 9 = rwwidth (width with unit like "30.0m")
                    if len(fields) > 9 and fields[9]:
                        try:
                            runway_width = int(float(re.sub(r'[^\d.]', '', fields[9])))
                        except (ValueError, AttributeError):
                            runway_width = 0
                    
                    # Frequency is in field 10
                    frequency = fields[10] if len(fields) > 10 else ''
                    # Description is in field 11
                    description = fields[11] if len(fields) > 11 else ''
                    
                elif runway_str.isdigit():
                    # Old format: combined string DDDLLLLWWW or DDDLLLL
                    if len(runway_str) >= 10:  # DDDLLLLWWW format (10 digits)
                        runway_direction = int(runway_str[:3])
                        runway_length = int(runway_str[3:7])
                        runway_width = int(runway_str[7:10])
                    elif len(runway_str) >= 7:  # Old format DDDLLLL (7 digits)
                        runway_direction = int(runway_str[:3])
                        runway_length = int(runway_str[3:7])
                    
                    # Frequency is in field 8
                    frequency = fields[8] if len(fields) > 8 else ''
                    # Description is in field 9
                    description = fields[9] if len(fields) > 9 else ''
                else:
                    # Empty or invalid runway field
                    frequency = fields[8] if len(fields) > 8 else ''
                    description = fields[9] if len(fields) > 9 else ''
            else:
                # No runway info at all - fields shift back
                frequency = fields[8] if len(fields) > 8 else ''
                description = fields[9] if len(fields) > 9 else ''
            
            waypoint = Waypoint(
                name=name,
                code=code,
                country=country,
                latitude=latitude,
                longitude=longitude,
                elevation=elevation,
                style=style,
                runway_direction=runway_direction,
                runway_length=runway_length,
                runway_width=runway_width,
                frequency=frequency,
                description=description
            )
            
            waypoints.append(waypoint)
            
        except Exception as e:
            print(f"Error parsing line {line_num}: {line} - {e}")
            continue
    
    return waypoints


def write_cup_file(waypoints):
    """Write waypoints to CUP format string."""
    lines = ['name,code,country,lat,lon,elev,style,rwdir,rwlen,rwwidth,freq,desc']
    
    for waypoint in waypoints:
        lines.append(waypoint.to_cup_string())
    
    return '\n'.join(lines)


def parse_csv_file(file_path):
    """Parse CSV file and return list of waypoints."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    waypoints = []
    
    # Try to detect delimiter
    sniffer = csv.Sniffer()
    delimiter = sniffer.sniff(content[:1024]).delimiter
    
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    
    for row in reader:
        # Map common CSV field names to our waypoint fields
        name = row.get('name', row.get('Name', ''))
        code = row.get('code', row.get('Code', row.get('ID', '')))
        country = row.get('country', row.get('Country', ''))
        
        # Try different latitude field names
        latitude = 0.0
        for lat_field in ['latitude', 'lat', 'Latitude', 'Lat']:
            if lat_field in row and row[lat_field]:
                try:
                    latitude = float(row[lat_field])
                    break
                except ValueError:
                    continue
        
        # Try different longitude field names
        longitude = 0.0
        for lon_field in ['longitude', 'lon', 'Longitude', 'Lon']:
            if lon_field in row and row[lon_field]:
                try:
                    longitude = float(row[lon_field])
                    break
                except ValueError:
                    continue
        
        # Try elevation fields
        elevation = 0
        for elev_field in ['elevation', 'elev', 'Elevation', 'Elev', 'altitude', 'alt']:
            if elev_field in row and row[elev_field]:
                try:
                    elevation = int(float(row[elev_field]))
                    break
                except ValueError:
                    continue
        
        style = 1
        if 'style' in row and row['style']:
            try:
                style = int(row['style'])
            except ValueError:
                pass
        
        # Parse runway fields
        runway_direction = 0
        if 'runway_direction' in row and row['runway_direction']:
            try:
                runway_direction = int(row['runway_direction'])
            except ValueError:
                pass
        
        runway_length = 0
        if 'runway_length' in row and row['runway_length']:
            try:
                runway_length = int(row['runway_length'])
            except ValueError:
                pass
        
        runway_width = 0
        if 'runway_width' in row and row['runway_width']:
            try:
                runway_width = int(row['runway_width'])
            except ValueError:
                pass
        
        description = row.get('description', row.get('Description', ''))
        frequency = row.get('frequency', row.get('Frequency', ''))
        
        waypoint = Waypoint(
            name=name,
            code=code,
            country=country,
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            style=style,
            runway_direction=runway_direction,
            runway_length=runway_length,
            runway_width=runway_width,
            frequency=frequency,
            description=description
        )
        
        waypoints.append(waypoint)
    
    return waypoints


def write_csv_file(waypoints):
    """Write waypoints to CSV format string."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['name', 'code', 'country', 'latitude', 'longitude', 'elevation', 'style', 'runway_direction', 'runway_length', 'runway_width', 'frequency', 'description'])
    
    # Write waypoints
    for waypoint in waypoints:
        writer.writerow([
            waypoint.name,
            waypoint.code,
            waypoint.country,
            waypoint.latitude,
            waypoint.longitude,
            waypoint.elevation,
            waypoint.style,
            waypoint.runway_direction,
            waypoint.runway_length,
            waypoint.runway_width,
            waypoint.frequency,
            waypoint.description
        ])
    
    return output.getvalue()


def get_elevation(latitude, longitude):
    """
    Get elevation for coordinates using online API.
    
    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
    
    Returns:
        int: Elevation in meters, or 0 if unavailable
    """
    try:
        # Use open-elevation API
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={latitude},{longitude}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        if response.status_code == 200:
            data = response.json()
            if data.get('results') and len(data['results']) > 0:
                elevation = data['results'][0].get('elevation', 0)
                return int(elevation) if elevation is not None else 0
        
        return 0
    except requests.exceptions.Timeout:
        print(f"Timeout fetching elevation for {latitude}, {longitude}")
        return 0
    except requests.exceptions.RequestException as e:
        print(f"Error fetching elevation for {latitude}, {longitude}: {e}")
        return 0
    except Exception as e:
        print(f"Unexpected error fetching elevation: {e}")
        return 0