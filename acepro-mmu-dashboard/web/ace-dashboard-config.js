// ValgACE Dashboard Configuration
// ACE Dashboard Configuration

const ACE_DASHBOARD_CONFIG = {
    // Moonraker API base URL
    // Defaults to current host. Override if needed, e.g.:
    // apiBase: 'http://localhost:7125',
    // apiBase: 'http://192.168.1.100:7125',
    // apiBase: 'https://moonraker.example.com',
    apiBase: window.location.origin,
    
    // WebSocket base URL
    // Automatically derived from apiBase if null.
    // Override if needed, e.g.:
    // wsBase: 'ws://localhost:7125',
    // wsBase: 'wss://moonraker.example.com',
    wsBase: null,
    
    // Auto-refresh interval in milliseconds
    autoRefreshInterval: 10000,
    
    // WebSocket reconnection timeout in milliseconds
    wsReconnectTimeout: 3000,
    
    // Enable debug console messages
    debug: false,
    
    // Default values for commands
    defaults: {
        feedLength: 50,          // Default feed length (mm)
        feedSpeed: 25,           // Default feed speed (mm/s)
        retractLength: 50,       // Default retract length (mm)
        retractSpeed: 25,        // Default retract speed (mm/s)
        dryingTemp: 50,          // Default drying temperature (°C)
        dryingDuration: 240,     // Default drying duration (minutes)
        presetFeedLength: 50,    // Quick feed preset (mm)
        presetRetractLength: 50  // Quick retract preset (mm)
    }
};

// Helper to build WebSocket URL
function getWebSocketUrl() {
    if (ACE_DASHBOARD_CONFIG.wsBase) {
        return ACE_DASHBOARD_CONFIG.wsBase;
    }
    
    const apiBase = ACE_DASHBOARD_CONFIG.apiBase;
    if (apiBase.startsWith('https://')) {
        return apiBase.replace('https://', 'wss://') + '/websocket';
    } else if (apiBase.startsWith('http://')) {
        return apiBase.replace('http://', 'ws://') + '/websocket';
    } else {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/websocket`;
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ACE_DASHBOARD_CONFIG, getWebSocketUrl };
}