/**
 * KeepAI Configuration
 * 
 * IMPORTANT: Update API_HOST with your server's IP address
 * when accessing from other devices on the network
 */

// Configuration
const CONFIG = {
    // For local access only (same computer)
    LOCAL_HOST: '127.0.0.1',
    
    // For network access (replace with your server's IP)
    // Find your IP: Run 'ipconfig' in Command Prompt
    NETWORK_HOST: '192.168.18.68',
    
    // Port number
    PORT: '8000',
    
    // Use network mode? Set to true for multi-device access
    USE_NETWORK_MODE: false
};

// Auto-generate API base URL
const getApiBase = () => {
    const host = CONFIG.USE_NETWORK_MODE ? CONFIG.NETWORK_HOST : CONFIG.LOCAL_HOST;
    return `http://${host}:${CONFIG.PORT}/api`;
};

// Export for use in HTML files
window.API_BASE = getApiBase();
var API_BASE = window.API_BASE;

console.log('🔧 API Configuration:');
console.log('   Mode:', CONFIG.USE_NETWORK_MODE ? 'Network Access' : 'Local Only');
console.log('   API Base:', API_BASE);
