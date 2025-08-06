// Canvas Notes Application Logic
class CanvasNotesApp {
    constructor() {
        this.courses = [];
        this.config = {};
        
        this.init();
    }
    
    async init() {
        try {
            console.log('Initializing Canvas Notes App...');
            
            // Load configuration and courses
            await this.loadConfig();
            await this.loadCourses();
            
            // Hide loading screen and show main content
            this.hideLoadingScreen();
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Initialize UI
            this.updateUI();
            
            console.log('App initialized successfully');
            
        } catch (error) {
            console.error('Failed to initialize app:', error);
            this.hideLoadingScreen();
            this.showError('Failed to initialize application: ' + error.message);
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();
            console.log('Config loaded:', this.config);
        } catch (error) {
            console.error('Failed to load config:', error);
            this.config = {};
        }
    }
    
    async loadCourses() {
        try {
            const response = await fetch('/api/courses');
            this.courses = await response.json();
            console.log('Courses loaded:', this.courses.length, 'courses');
        } catch (error) {
            console.error('Failed to load courses:', error);
            this.courses = [];
        }
    }
    
    hideLoadingScreen() {
        console.log('Hiding loading screen...');
        
        const loadingScreen = document.getElementById('loading-screen');
        if (loadingScreen) {
            loadingScreen.style.display = 'none';
            console.log('Loading screen hidden');
        }
        
        const mainApp = document.getElementById('main-app');
        if (mainApp) {
            mainApp.style.display = 'block';
            console.log('Main app shown');
        } else {
            console.error('Main app element not found!');
        }
    }
    
    setupEventListeners() {
        console.log('Setting up event listeners...');
        
        // Configure API button
        const configureBtn = document.getElementById('configure-api-btn');
        if (configureBtn) {
            configureBtn.addEventListener('click', () => this.showConfigModal());
        }
        
        // Refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshCourses());
        }
    }
    
    updateUI() {
        console.log('Updating UI...');
        this.renderCourses();
        this.updateStatus();
    }
    
    renderCourses() {
        const coursesGrid = document.getElementById('courses-grid');
        if (!coursesGrid) {
            console.error('Courses grid element not found!');
            return;
        }
        
        if (this.courses.length === 0) {
            coursesGrid.innerHTML = '<div class="no-data">No cached data</div>';
            return;
        }
        
        const coursesHTML = this.courses.map(course => `
            <div class="course-card" data-course-id="${course.id}">
                <div class="course-header">
                    <h3 class="course-title">${course.name}</h3>
                    <div class="course-actions">
                        <button class="btn btn-sm btn-outline" onclick="app.openCourseNotes('${course.name}')">
                            <i class="fas fa-edit"></i> Notes
                        </button>
                    </div>
                </div>
                <div class="course-info">
                    <span class="course-code">${course.course_code}</span>
                    <span class="course-term">${course.term || 'Current Term'}</span>
                </div>
            </div>
        `).join('');
        
        coursesGrid.innerHTML = coursesHTML;
        console.log('Courses rendered:', this.courses.length);
    }
    
    updateStatus() {
        const statusText = document.getElementById('status-text');
        if (statusText) {
            statusText.textContent = this.courses.length > 0 ? 
                `${this.courses.length} courses loaded` : 
                'No cached data';
        }
    }
    
    async refreshCourses() {
        try {
            console.log('Refreshing courses...');
            const response = await fetch('/api/courses', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                await this.loadCourses();
                this.updateUI();
                this.showMessage('Courses refreshed successfully', 'success');
            }
        } catch (error) {
            console.error('Failed to refresh courses:', error);
            this.showMessage('Failed to refresh courses', 'error');
        }
    }
    
    showConfigModal() {
        console.log('Configure API clicked');
        // Basic implementation - you can expand this
        alert('Configuration modal not yet implemented');
    }
    
    openCourseNotes(courseName) {
        console.log('Opening notes for:', courseName);
        // Basic implementation - you can expand this
        alert(`Notes for ${courseName} - not yet implemented`);
    }
    
    showMessage(message, type = 'info') {
        console.log(`${type.toUpperCase()}: ${message}`);
    }
    
    showError(message) {
        this.showMessage(message, 'error');
        
        // Also show error in the main app if loading screen is hidden
        const mainApp = document.getElementById('main-app');
        if (mainApp && mainApp.style.display !== 'none') {
            const coursesGrid = document.getElementById('courses-grid');
            if (coursesGrid) {
                coursesGrid.innerHTML = `<div class="error">Error: ${message}</div>`;
            }
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing app...');
    window.app = new CanvasNotesApp();
});

// Also initialize the updater
document.addEventListener('DOMContentLoaded', () => {
    if (typeof CanvasNotesUpdater !== 'undefined') {
        console.log('Initializing updater...');
        window.updater = new CanvasNotesUpdater();
    } else {
        console.log('CanvasNotesUpdater not found');
    }
});
