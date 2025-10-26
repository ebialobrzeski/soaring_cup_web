"""Soaring CUP File Editor - A waypoint editor for soaring and flight planning software."""

__version__ = "3.0.0"
__author__ = "Soaring CUP Editor Team"

from .models import Waypoint
from .file_io import parse_cup_file, write_cup_file, parse_csv_file, write_csv_file
from .utils import ddmm_to_deg, deg_to_ddmm

__all__ = [
    'Waypoint',
    'parse_cup_file',
    'write_cup_file',
    'parse_csv_file',
    'write_csv_file',
    'ddmm_to_deg',
    'deg_to_ddmm',
]
