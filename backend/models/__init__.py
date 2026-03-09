"""Models package — SQLAlchemy ORM models and legacy dataclasses."""
from backend.models.base import Base
from backend.models.user import User
from backend.models.waypoint_file import WaypointFile, WaypointEntry
from backend.models.task import SavedTask
from backend.models.legacy import Waypoint  # backwards-compat for file_io and app.py

__all__ = ['Base', 'User', 'WaypointFile', 'WaypointEntry', 'SavedTask', 'Waypoint']
