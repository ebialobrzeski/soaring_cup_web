"""File I/O operations for CUP and CSV formats."""

import csv
import requests
from typing import List
from pathlib import Path

from .models import Waypoint
from .utils import ddmm_to_deg, deg_to_ddmm
from .config import STYLE_OPTIONS, ELEVATION_API_URL, ELEVATION_API_TIMEOUT


def get_elevation(lat: float, lon: float) -> float:
    """
    Fetch elevation data from open-elevation API.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        
    Returns:
        Elevation in meters, or 0.0 if fetch fails
    """
    try:
        resp = requests.get(
            ELEVATION_API_URL,
            params={"locations": f"{lat},{lon}"},
            timeout=ELEVATION_API_TIMEOUT
        )
        return resp.json()['results'][0]['elevation']
    except Exception as e:
        print(f"Elevation fetch error for {lat}, {lon}: {e}")
        return 0.0


def parse_cup_file(filepath: str) -> List[Waypoint]:
    """
    Parse a CUP file and return list of Waypoint objects.
    
    Args:
        filepath: Path to the CUP file
        
    Returns:
        List of Waypoint objects
    """
    waypoints = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Skip header line
    for line_num, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        
        # Parse CSV line respecting quoted fields
        parts = []
        current = []
        in_quotes = False
        
        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                parts.append(''.join(current).strip().strip('"'))
                current = []
            else:
                current.append(char)
        parts.append(''.join(current).strip().strip('"'))
        
        # Ensure we have enough fields
        while len(parts) < 12:
            parts.append('')
        
        name, code, country, lat_str, lon_str, elev_str, style_str, rwdir, rwlen, rwwidth, freq, desc = parts[:12]
        
        try:
            lat = ddmm_to_deg(lat_str)
            lon = ddmm_to_deg(lon_str)
            style = int(style_str) if style_str else 1
            
            # Parse elevation - keep as string with unit
            elev = None
            if elev_str:
                elev = elev_str.strip()  # Keep as-is with unit (e.g., "504.0m" or "1654ft")
            
            waypoint = Waypoint(
                name=name,
                latitude=lat,
                longitude=lon,
                code=code,
                country=country,
                elevation=elev,
                style=style,
                runway_direction=rwdir,
                runway_length=rwlen,
                runway_width=rwwidth,
                frequency=freq,
                description=desc
            )
            waypoints.append(waypoint)
        except Exception as e:
            print(f"Error parsing line {line_num}: {line}\nError: {e}")
            continue
    
    return waypoints


def write_cup_file(filepath: str, waypoints: List[Waypoint], fetch_elevation: bool = True) -> None:
    """
    Write waypoints to CUP file format.
    
    Args:
        filepath: Path to save the CUP file
        waypoints: List of Waypoint objects to save
        fetch_elevation: Whether to fetch elevation from API if not present
    """
    rows = ["name,code,country,lat,lon,elev,style,rwdir,rwlen,rwwidth,freq,desc"]
    
    for waypoint in waypoints:
        # Get or fetch elevation
        if waypoint.elevation is not None and waypoint.elevation != "":
            # Elevation already has unit, use as-is
            elev_str = str(waypoint.elevation)
            # Ensure it has a unit
            if not any(unit in elev_str.lower() for unit in ['m', 'ft']):
                elev_str = f"{elev_str}m"  # Default to meters if no unit
        elif fetch_elevation:
            # Fetch elevation and add default unit (meters)
            elev_value = get_elevation(waypoint.latitude, waypoint.longitude)
            elev_str = f"{elev_value:.1f}m"
        else:
            elev_str = "0.0m"
        
        # Use description as-is (preserve empty descriptions)
        desc = waypoint.description if waypoint.description else ""
        
        # Convert coordinates to DDMM format
        lat_str = deg_to_ddmm(waypoint.latitude, True)
        lon_str = deg_to_ddmm(waypoint.longitude, False)
        
        # Format code and country (use defaults if empty)
        code = waypoint.code if waypoint.code else ""
        country = waypoint.country if waypoint.country else ""
        
        # Format runway information
        rwdir = waypoint.runway_direction if waypoint.runway_direction else ""
        rwlen = waypoint.runway_length if waypoint.runway_length else ""
        rwwidth = waypoint.runway_width if waypoint.runway_width else ""
        
        # Format frequency - only quote if it's empty or contains non-numeric text
        freq = waypoint.frequency if waypoint.frequency else ""
        if freq and not freq.replace('.', '').replace(',', '').isdigit():
            freq_formatted = f'"{freq}"'  # Quote if it's text
        else:
            freq_formatted = freq  # Don't quote numeric frequencies
        
        # Format description - only quote if not empty
        if desc:
            desc_formatted = f'"{desc}"'
        else:
            desc_formatted = ''
        
        # Build row - Quote fields that may contain special characters
        row = (
            f'"{waypoint.name}",'
            f'{code},'
            f'{country},'
            f'{lat_str},'
            f'{lon_str},'
            f'{elev_str},'
            f'{waypoint.style},'
            f'{rwdir},'
            f'{rwlen},'
            f'{rwwidth},'
            f'{freq_formatted},'
            f'{desc_formatted}'
        )
        rows.append(row)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))


def parse_csv_file(filepath: str) -> List[Waypoint]:
    """
    Parse a CSV file and return list of Waypoint objects.
    
    Args:
        filepath: Path to the CSV file
        
    Returns:
        List of Waypoint objects
    """
    waypoints = []
    
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row_num, row in enumerate(reader, start=2):
            try:
                waypoint = Waypoint(
                    name=row.get('name', ''),
                    latitude=float(row['latitude']),
                    longitude=float(row['longitude']),
                    code=row.get('code', ''),
                    country=row.get('country', ''),
                    elevation=row.get('elevation', None) if row.get('elevation') else None,
                    style=int(row.get('style', 1)),
                    runway_direction=row.get('runway_direction', ''),
                    runway_length=row.get('runway_length', ''),
                    runway_width=row.get('runway_width', ''),
                    frequency=row.get('frequency', ''),
                    description=row.get('description', '')
                )
                waypoints.append(waypoint)
            except (ValueError, KeyError) as e:
                print(f"Skipping invalid CSV row {row_num}: {row}, Error: {e}")
                continue
    
    return waypoints


def write_csv_file(filepath: str, waypoints: List[Waypoint]) -> None:
    """
    Write waypoints to CSV file.
    
    Args:
        filepath: Path to save the CSV file
        waypoints: List of Waypoint objects to save
    """
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'name', 'code', 'country', 'latitude', 'longitude', 'elevation', 
            'style', 'runway_direction', 'runway_length', 'runway_width', 
            'frequency', 'description'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for waypoint in waypoints:
            writer.writerow({
                'name': waypoint.name,
                'code': waypoint.code,
                'country': waypoint.country,
                'latitude': waypoint.latitude,
                'longitude': waypoint.longitude,
                'elevation': waypoint.elevation if waypoint.elevation is not None else '',
                'style': waypoint.style,
                'runway_direction': waypoint.runway_direction,
                'runway_length': waypoint.runway_length,
                'runway_width': waypoint.runway_width,
                'frequency': waypoint.frequency,
                'description': waypoint.description
            })
