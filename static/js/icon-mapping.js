/**
 * Waypoint icon mapping based on XCSoar icons
 * Maps waypoint style numbers to appropriate icon URLs
 */

const WAYPOINT_ICONS = {
    0: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_small.svg',
        name: 'Unknown',
        color: '#6b7280'
    },
    1: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_turnpoint.svg',
        name: 'Waypoint',
        color: '#2563eb'
    },
    2: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/alt_landable_field.svg',
        name: 'Airfield (grass)',
        color: '#059669'
    },
    3: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/alt_landable_field.svg',
        name: 'Outlanding',
        color: '#dc2626'
    },
    4: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/alt_landable_airport.svg',
        name: 'Gliding airfield',
        color: '#059669'
    },
    5: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/alt_landable_airport.svg',
        name: 'Airfield (solid)',
        color: '#059669'
    },
    6: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_pass.svg',
        name: 'Mountain Pass',
        color: '#8b5cf6'
    },
    7: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_mountain_top.svg',
        name: 'Mountain Top',
        color: '#8b5cf6'
    },
    8: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_tower.svg',
        name: 'Transmitter Mast',
        color: '#f59e0b'
    },
    9: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_vor.svg',
        name: 'VOR',
        color: '#3b82f6'
    },
    10: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_ndb.svg',
        name: 'NDB',
        color: '#3b82f6'
    },
    11: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_tower.svg',
        name: 'Cooling Tower',
        color: '#6b7280'
    },
    12: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_dam.svg',
        name: 'Dam',
        color: '#0ea5e9'
    },
    13: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_tunnel.svg',
        name: 'Tunnel',
        color: '#6b7280'
    },
    14: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_bridge.svg',
        name: 'Bridge',
        color: '#6b7280'
    },
    15: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_power_plant.svg',
        name: 'Power Plant',
        color: '#f59e0b'
    },
    16: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_castle.svg',
        name: 'Castle',
        color: '#8b5cf6'
    },
    17: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_intersection.svg',
        name: 'Intersection',
        color: '#6b7280'
    },
    18: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_flag.svg',
        name: 'Marker',
        color: '#ef4444'
    },
    19: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_reporting_point.svg',
        name: 'Reporting Point',
        color: '#3b82f6'
    },
    20: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_pgtakeoff.svg',
        name: 'PG Take Off',
        color: '#10b981'
    },
    21: {
        icon: 'https://raw.githubusercontent.com/XCSoar/XCSoar/master/Data/icons/map_pglanding.svg',
        name: 'PG Landing',
        color: '#f59e0b'
    }
};

/**
 * Get icon configuration for a waypoint style
 * @param {number} style - Waypoint style number (0-21)
 * @returns {object} Icon configuration object
 */
function getWaypointIcon(style) {
    return WAYPOINT_ICONS[style] || WAYPOINT_ICONS[1]; // Default to waypoint icon
}

/**
 * Create a Leaflet icon for a waypoint style
 * @param {number} style - Waypoint style number (0-21)
 * @param {number} size - Icon size in pixels (default: 24)
 * @returns {L.Icon} Leaflet icon object
 */
function createWaypointIcon(style, size = 24) {
    const iconConfig = getWaypointIcon(style);
    
    return L.divIcon({
        html: `<div style="
            width: ${size}px; 
            height: ${size}px; 
            background-image: url('${iconConfig.icon}'); 
            background-size: contain; 
            background-repeat: no-repeat; 
            background-position: center;
            filter: drop-shadow(1px 1px 2px rgba(0,0,0,0.3));
        "></div>`,
        className: 'waypoint-icon',
        iconSize: [size, size],
        iconAnchor: [size/2, size/2],
        popupAnchor: [0, -size/2]
    });
}