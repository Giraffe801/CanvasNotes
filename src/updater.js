// Canvas Notes Updater
// Simple updater functionality for the Canvas Notes application

class CanvasNotesUpdater {
    constructor() {
        this.currentVersion = '1.4.5';
        this.updateCheckUrl = 'https://raw.githubusercontent.com/Giraffe801/CanvasNotes/main/version.txt';
        this.downloadUrl = 'https://github.com/Giraffe801/CanvasNotes/releases/latest/download/canvas_dashboard.exe';
        
        this.initUpdater();
    }
    
    initUpdater() {
        // Check for updates on startup
        this.checkForUpdates();
        
        // Set up periodic update checks (every 24 hours)
        setInterval(() => {
            this.checkForUpdates();
        }, 24 * 60 * 60 * 1000);
    }
    
    async checkForUpdates() {
        try {
            const response = await fetch(this.updateCheckUrl);
            if (!response.ok) throw new Error('Failed to check for updates');
            
            const latestVersion = (await response.text()).trim();
            
            if (this.isNewVersion(latestVersion, this.currentVersion)) {
                this.showUpdateNotification(latestVersion);
            }
        } catch (error) {
            console.log('Update check failed:', error);
        }
    }
    
    isNewVersion(latest, current) {
        const parseVersion = (v) => v.split('.').map(Number);
        const latestParts = parseVersion(latest);
        const currentParts = parseVersion(current);
        
        for (let i = 0; i < Math.max(latestParts.length, currentParts.length); i++) {
            const latestPart = latestParts[i] || 0;
            const currentPart = currentParts[i] || 0;
            
            if (latestPart > currentPart) return true;
            if (latestPart < currentPart) return false;
        }
        
        return false;
    }
    
    showUpdateNotification(latestVersion) {
        const notification = document.createElement('div');
        notification.className = 'update-notification';
        notification.innerHTML = `
            <div class="update-content">
                <h3>📥 Update Available</h3>
                <p>Canvas Notes v${latestVersion} is now available!</p>
                <div class="update-buttons">
                    <button onclick="updater.downloadUpdate('${latestVersion}')" class="btn-primary">
                        Download Update
                    </button>
                    <button onclick="updater.dismissUpdate()" class="btn-secondary">
                        Later
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-dismiss after 10 seconds if user doesn't interact
        setTimeout(() => {
            if (document.body.contains(notification)) {
                this.dismissUpdate();
            }
        }, 10000);
    }
    
    downloadUpdate(version) {
        // Open the download URL in a new tab
        window.open(this.downloadUrl, '_blank');
        this.dismissUpdate();
    }
    
    dismissUpdate() {
        const notification = document.querySelector('.update-notification');
        if (notification) {
            notification.remove();
        }
    }
    
    // Manual update check for user-triggered updates
    manualUpdateCheck() {
        this.showUpdateCheckingIndicator();
        this.checkForUpdates().finally(() => {
            this.hideUpdateCheckingIndicator();
        });
    }
    
    showUpdateCheckingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'update-checking';
        indicator.innerHTML = '<p>🔄 Checking for updates...</p>';
        document.body.appendChild(indicator);
    }
    
    hideUpdateCheckingIndicator() {
        const indicator = document.querySelector('.update-checking');
        if (indicator) {
            setTimeout(() => indicator.remove(), 1000);
        }
    }
}

// Initialize the updater when the page loads
let updater;
document.addEventListener('DOMContentLoaded', () => {
    updater = new CanvasNotesUpdater();
    
    // Add update check button to the page if needed
    const updateButton = document.getElementById('check-updates');
    if (updateButton) {
        updateButton.addEventListener('click', (e) => {
            e.preventDefault();
            updater.manualUpdateCheck();
        });
    }
});

// Export for use in Python web server
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CanvasNotesUpdater;
}
