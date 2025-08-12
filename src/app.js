// Canvas Notes Application Logic
class CanvasNotesApp {
    constructor() {
        this.courses = [];
        this.config = {};
        this.timerInterval = null;
        this.hiddenCourses = new Set();
        this.showingHidden = false;
        this.showingPast = false;
        this.currentView = 'active'; // 'active', 'hidden', 'past', 'all'
        
        this.init();
    }
    
    async init() {
        try {
            console.log('Initializing Canvas Notes App...');
            
            // Load configuration and courses
            await this.loadConfig();
            await this.loadHiddenCourses();
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
    
    async loadHiddenCourses() {
        try {
            const stored = localStorage.getItem('hiddenCourses');
            if (stored) {
                this.hiddenCourses = new Set(JSON.parse(stored));
                console.log('Hidden courses loaded:', this.hiddenCourses.size);
            }
        } catch (error) {
            console.error('Failed to load hidden courses:', error);
            this.hiddenCourses = new Set();
        }
    }
    
    saveHiddenCourses() {
        try {
            localStorage.setItem('hiddenCourses', JSON.stringify([...this.hiddenCourses]));
            console.log('Hidden courses saved');
        } catch (error) {
            console.error('Failed to save hidden courses:', error);
        }
    }
    
    toggleCourseVisibility(courseId) {
        if (this.hiddenCourses.has(courseId)) {
            this.hiddenCourses.delete(courseId);
        } else {
            this.hiddenCourses.add(courseId);
        }
        this.saveHiddenCourses();
        this.updateUI();
    }
    
    setView(view) {
        this.currentView = view;
        this.updateViewButtons();
        this.updateUI();
    }
    
    updateViewButtons() {
        const viewBtn = document.getElementById('view-options-btn');
        const icon = viewBtn.querySelector('i');
        
        switch(this.currentView) {
            case 'hidden':
                viewBtn.innerHTML = '<i class="fas fa-eye-slash"></i> Hidden Courses <i class="fas fa-chevron-down"></i>';
                break;
            case 'past':
                viewBtn.innerHTML = '<i class="fas fa-history"></i> Past Courses <i class="fas fa-chevron-down"></i>';
                break;
            case 'all':
                viewBtn.innerHTML = '<i class="fas fa-list"></i> All Courses <i class="fas fa-chevron-down"></i>';
                break;
            default:
                viewBtn.innerHTML = '<i class="fas fa-eye"></i> Active Courses <i class="fas fa-chevron-down"></i>';
        }
    }
    
    getFilteredCourses() {
        let filteredCourses = [...this.courses];
        
        switch(this.currentView) {
            case 'hidden':
                filteredCourses = filteredCourses.filter(course => this.hiddenCourses.has(course.id));
                break;
            case 'past':
                filteredCourses = filteredCourses.filter(course => this.isCourseExpired(course));
                break;
            case 'all':
                // Show all courses regardless of hidden status
                break;
            default: // active
                filteredCourses = filteredCourses.filter(course => 
                    !this.hiddenCourses.has(course.id) && !this.isCourseExpired(course)
                );
        }
        
        return filteredCourses;
    }
    
    isCourseExpired(course) {
        if (!course.end_at) return false;
        const endDate = new Date(course.end_at);
        return endDate < new Date();
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
        
        // View options dropdown
        this.setupViewOptionsListeners();
        
        // Configuration modal event listeners
        this.setupConfigModalListeners();
    }
    
    setupViewOptionsListeners() {
        // Dropdown toggle
        const dropdownBtn = document.getElementById('view-options-btn');
        const dropdownMenu = document.getElementById('view-options-menu');
        
        if (dropdownBtn && dropdownMenu) {
            dropdownBtn.addEventListener('click', (e) => {
                e.preventDefault();
                dropdownBtn.parentElement.classList.toggle('active');
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', (e) => {
                if (!dropdownBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
                    dropdownBtn.parentElement.classList.remove('active');
                }
            });
        }
        
        // View option buttons
        const showAllBtn = document.getElementById('show-all-courses');
        const showHiddenBtn = document.getElementById('show-hidden-courses');
        const viewPastBtn = document.getElementById('view-past-courses');
        
        if (showAllBtn) {
            showAllBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.setView('active');
                dropdownBtn.parentElement.classList.remove('active');
            });
        }
        
        if (showHiddenBtn) {
            showHiddenBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.setView('hidden');
                dropdownBtn.parentElement.classList.remove('active');
            });
        }
        
        if (viewPastBtn) {
            viewPastBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.setView('past');
                dropdownBtn.parentElement.classList.remove('active');
            });
        }
    }
    
    updateUI() {
        console.log('Updating UI...');
        this.updateViewButtons();
        this.renderCourses();
        this.updateStatus();
        this.startCourseTimers();
    }
    
    calculateTimeRemaining(endDate) {
        if (!endDate) return null;
        
        const end = new Date(endDate);
        const now = new Date();
        const diff = end - now;
        
        if (diff <= 0) return { expired: true, text: 'Course Ended' };
        
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        
        if (days > 0) {
            return { expired: false, text: `${days} day${days !== 1 ? 's' : ''} left` };
        } else if (hours > 0) {
            return { expired: false, text: `${hours} hour${hours !== 1 ? 's' : ''} left` };
        } else if (minutes > 0) {
            return { expired: false, text: `${minutes} minute${minutes !== 1 ? 's' : ''} left` };
        } else {
            return { expired: false, text: 'Less than 1 minute left' };
        }
    }
    
    startCourseTimers() {
        // Clear existing timer
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
        }
        
        // Update timers every minute
        this.timerInterval = setInterval(() => {
            this.updateCourseTimers();
        }, 60000); // Update every minute
        
        // Initial update
        this.updateCourseTimers();
    }
    
    updateCourseTimers() {
        this.courses.forEach(course => {
            const timerElement = document.querySelector(`[data-course-id="${course.id}"] .course-timer`);
            if (timerElement && course.end_at) {
                const timeInfo = this.calculateTimeRemaining(course.end_at);
                if (timeInfo) {
                    timerElement.textContent = timeInfo.text;
                    timerElement.className = `course-timer ${timeInfo.expired ? 'expired' : ''}`;
                }
            }
        });
    }
    
    renderCourses() {
        const coursesGrid = document.getElementById('courses-grid');
        if (!coursesGrid) {
            console.error('Courses grid element not found!');
            return;
        }
        
        const filteredCourses = this.getFilteredCourses();
        
        if (filteredCourses.length === 0) {
            let message = 'No courses found';
            switch(this.currentView) {
                case 'hidden':
                    message = 'No hidden courses';
                    break;
                case 'past':
                    message = 'No past courses';
                    break;
                default:
                    message = 'No active courses';
            }
            coursesGrid.innerHTML = `<div class="no-data">${message}</div>`;
            return;
        }
        
        const coursesHTML = filteredCourses.map(course => {
            const timeInfo = this.calculateTimeRemaining(course.end_at);
            const timerHTML = timeInfo ? 
                `<div class="course-timer ${timeInfo.expired ? 'expired' : ''}">${timeInfo.text}</div>` : 
                '<div class="course-timer">No end date</div>';
            
            const isHidden = this.hiddenCourses.has(course.id);
            const isExpired = this.isCourseExpired(course);
            const hideButtonText = isHidden ? 'Show' : 'Hide';
            const hideButtonIcon = isHidden ? 'fa-eye' : 'fa-eye-slash';
                
            return `
                <div class="course-card ${isHidden ? 'hidden-course' : ''} ${isExpired ? 'past-course' : ''}" data-course-id="${course.id}">
                    <div class="course-header">
                        <h3 class="course-title">${course.name}</h3>
                        <div class="course-actions">
                            <button class="btn btn-sm btn-outline" onclick="app.openCourseNotes('${course.name}', ${course.id})">
                                <i class="fas fa-edit"></i> Notes
                            </button>
                            <button class="btn btn-sm btn-secondary" onclick="app.toggleCourseVisibility(${course.id})">
                                <i class="fas ${hideButtonIcon}"></i> ${hideButtonText}
                            </button>
                        </div>
                    </div>
                    <div class="course-info">
                        <span class="course-code">${course.course_code}</span>
                        <span class="course-term">${course.term || 'Current Term'}</span>
                        ${timerHTML}
                    </div>
                </div>
            `;
        }).join('');
        
        coursesGrid.innerHTML = coursesHTML;
        console.log('Courses rendered:', this.courses.length);
    }
    
    updateStatus() {
        const statusText = document.getElementById('status-text');
        if (statusText) {
            const filteredCourses = this.getFilteredCourses();
            const totalCourses = this.courses.length;
            const hiddenCount = this.hiddenCourses.size;
            
            let statusMessage = '';
            switch(this.currentView) {
                case 'hidden':
                    statusMessage = `${filteredCourses.length} hidden course${filteredCourses.length !== 1 ? 's' : ''}`;
                    break;
                case 'past':
                    statusMessage = `${filteredCourses.length} past course${filteredCourses.length !== 1 ? 's' : ''}`;
                    break;
                case 'all':
                    statusMessage = `${totalCourses} total course${totalCourses !== 1 ? 's' : ''} (${hiddenCount} hidden)`;
                    break;
                default:
                    statusMessage = `${filteredCourses.length} active course${filteredCourses.length !== 1 ? 's' : ''}`;
            }
            
            statusText.textContent = totalCourses > 0 ? statusMessage : 'No cached data';
        }
    }
    
    async refreshCourses() {
        try {
            console.log('Refreshing courses...');
            const response = await fetch('/api/courses', { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            });
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
        
        // Show the configuration modal
        const modal = document.getElementById('config-modal-overlay');
        modal.classList.remove('hidden');
        modal.classList.add('show');
        
        // Load current configuration
        const schoolInput = document.getElementById('canvas-school');
        const tokenInput = document.getElementById('canvas-token-modal');
        
        console.log('Current config:', this.config);
        
        if (this.config.canvas_url) {
            // Extract school name from URL (e.g., https://slcschools.instructure.com -> slcschools)
            const match = this.config.canvas_url.match(/https?:\/\/([^.]+)\.instructure\.com/);
            if (match) {
                schoolInput.value = match[1];
                console.log('Loaded school name:', match[1]);
            }
        } else {
            schoolInput.value = '';
        }
        
        if (this.config.canvas_token) {
            tokenInput.value = this.config.canvas_token;
            console.log('Loaded token:', {
                tokenLength: this.config.canvas_token.length,
                tokenPreview: `${this.config.canvas_token.substring(0, 10)}...`,
                inputValue: tokenInput.value,
                inputValueLength: tokenInput.value.length
            });
        } else {
            tokenInput.value = '';
            console.log('No token found in config:', this.config);
        }
        
        // Clear connection status
        const status = document.getElementById('connection-status');
        status.textContent = '';
        status.className = 'connection-status';
        
        // Debug: Check field values after a short delay
        setTimeout(() => {
            console.log('Modal field values after loading:', {
                school: schoolInput.value,
                token: tokenInput.value ? `${tokenInput.value.substring(0, 10)}...` : 'EMPTY',
                tokenLength: tokenInput.value.length
            });
        }, 100);
    }
    
    setupConfigModalListeners() {
        // Close modal buttons
        const closeBtn = document.getElementById('config-modal-close');
        const cancelBtn = document.getElementById('config-modal-cancel');
        const overlay = document.getElementById('config-modal-overlay');
        
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hideConfigModal());
        }
        
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.hideConfigModal());
        }
        
        // Close when clicking overlay
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    this.hideConfigModal();
                }
            });
        }
        
        // Test connection button
        const testBtn = document.getElementById('test-connection');
        if (testBtn) {
            testBtn.addEventListener('click', () => this.testConnection());
        }
        
        // Save configuration button  
        const saveBtn = document.getElementById('config-modal-save');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveConfiguration());
        }
    }
    
    hideConfigModal() {
        const modal = document.getElementById('config-modal-overlay');
        modal.classList.remove('show');
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 300);
    }
    
    async testConnection() {
        const schoolInput = document.getElementById('canvas-school');
        const tokenInput = document.getElementById('canvas-token-modal');
        const status = document.getElementById('connection-status');
        const testBtn = document.getElementById('test-connection');
        
        const school = schoolInput.value.trim();
        const token = tokenInput.value.trim();
        
        console.log('Testing connection with:', { 
            school: school,
            tokenLength: token.length, 
            tokenValue: token ? `${token.substring(0, 10)}...` : 'EMPTY',
            schoolInputExists: !!schoolInput,
            tokenInputExists: !!tokenInput
        });
        
        if (!school || school.length === 0) {
            status.textContent = 'Please enter your school/organization name';
            status.className = 'connection-status error';
            schoolInput.focus();
            return;
        }
        
        if (!token || token.length === 0) {
            console.error('Token validation failed:', {
                token: token,
                tokenLength: token.length,
                tokenInputValue: tokenInput.value,
                tokenInputValueLength: tokenInput.value.length
            });
            status.textContent = 'Please enter an access token';
            status.className = 'connection-status error';
            tokenInput.focus();
            return;
        }
        
        // Build Canvas URL from school name
        const canvas_url = `https://${school}.instructure.com`;
        
        // Show testing status
        status.textContent = `Testing connection to ${canvas_url}...`;
        status.className = 'connection-status testing';
        testBtn.disabled = true;
        
        try {
            const response = await fetch('/api/test-connection', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    canvas_url: canvas_url,
                    canvas_token: token
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                status.textContent = 'Connection successful!';
                status.className = 'connection-status success';
            } else {
                status.textContent = `Connection failed: ${result.error || 'Unknown error'}`;
                status.className = 'connection-status error';
            }
        } catch (error) {
            console.error('Test connection error:', error);
            status.textContent = `Connection failed: ${error.message}`;
            status.className = 'connection-status error';
        } finally {
            testBtn.disabled = false;
        }
    }
    
    async saveConfiguration() {
        const schoolInput = document.getElementById('canvas-school');
        const tokenInput = document.getElementById('canvas-token-modal');
        const saveBtn = document.getElementById('config-modal-save');
        
        const school = schoolInput.value.trim();
        const token = tokenInput.value.trim();
        
        console.log('Saving configuration with:', { school: school, tokenLength: token.length });
        
        if (!school || school.length === 0) {
            alert('Please enter your school/organization name');
            schoolInput.focus();
            return;
        }
        
        if (!token || token.length === 0) {
            alert('Please enter an access token');
            tokenInput.focus();
            return;
        }
        
        // Build Canvas URL from school name
        const canvas_url = `https://${school}.instructure.com`;
        
        // Show saving status
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        
        try {
            const response = await fetch('/api/save-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    canvas_url: canvas_url,
                    canvas_token: token
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Update local config
                this.config.canvas_url = canvas_url;
                this.config.canvas_token = token;
                
                // Hide modal
                this.hideConfigModal();
                
                // Refresh courses
                await this.refreshCourses();
                
                // Show success message
                this.showMessage('Configuration saved successfully!', 'success');
            } else {
                alert(`Failed to save configuration: ${result.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Save configuration error:', error);
            alert(`Failed to save configuration: ${error.message}`);
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Configuration';
        }
    }
    
    openCourseNotes(courseName, courseId) {
        console.log('Opening notes for:', courseName, 'ID:', courseId);
        
        // Show the course editor panel
        document.getElementById('course-dashboard').classList.add('hidden');
        document.getElementById('course-editor-panel').classList.remove('hidden');
        
        // Update course info in the editor
        document.getElementById('current-course-name').textContent = courseName;
        const course = this.courses.find(c => c.id === courseId);
        if (course) {
            document.getElementById('current-course-details').textContent = 
                `${course.course_code} • ${course.term || 'Current Term'}`;
        }
        
        // Load notes for this course
        this.loadCourseNotes(courseName, courseId);
        
        // Set up back button
        const backBtn = document.getElementById('back-to-courses');
        if (backBtn) {
            backBtn.onclick = () => this.closeCourseNotes();
        }
    }
    
    closeCourseNotes() {
        document.getElementById('course-editor-panel').classList.add('hidden');
        document.getElementById('course-dashboard').classList.remove('hidden');
    }
    
    async loadCourseNotes(courseName, courseId) {
        try {
            const response = await fetch(`/api/files/${courseId}`);
            const files = await response.json();
            
            this.renderFileList(files, courseName);
            
            // If there are files, load the first one
            if (files.length > 0) {
                this.loadNoteFile(courseName, files[0].name);
            } else {
                // Show empty editor
                this.showEmptyEditor(courseName);
            }
        } catch (error) {
            console.error('Failed to load course notes:', error);
            this.showEmptyEditor(courseName);
        }
    }
    
    renderFileList(files, courseName) {
        const fileList = document.getElementById('file-list');
        if (!fileList) return;
        
        if (files.length === 0) {
            fileList.innerHTML = `
                <div class="no-files">
                    <p>No notes yet</p>
                    <button class="btn btn-sm btn-primary" onclick="app.createNewNote('${courseName}')">
                        <i class="fas fa-plus"></i> Create Note
                    </button>
                </div>
            `;
        } else {
            const filesHTML = files.map(file => `
                <div class="file-item" onclick="app.loadNoteFile('${courseName}', '${file.name}')">
                    <i class="fas fa-file-text"></i>
                    <span>${file.name}</span>
                    <button class="btn btn-sm btn-danger" onclick="app.deleteNoteFile(event, '${courseName}', '${file.name}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('');
            
            fileList.innerHTML = `
                <div class="file-actions">
                    <button class="btn btn-sm btn-primary" onclick="app.createNewNote('${courseName}')">
                        <i class="fas fa-plus"></i> New Note
                    </button>
                </div>
                ${filesHTML}
            `;
        }
    }
    
    showEmptyEditor(courseName) {
        const editorContainer = document.getElementById('editor-container');
        if (editorContainer) {
            editorContainer.innerHTML = `
                <div class="empty-editor">
                    <h3>No notes selected</h3>
                    <p>Create a new note or select an existing one to start editing.</p>
                    <button class="btn btn-primary" onclick="app.createNewNote('${courseName}')">
                        <i class="fas fa-plus"></i> Create First Note
                    </button>
                </div>
            `;
        }
    }
    
    async loadNoteFile(courseName, fileName) {
        try {
            const response = await fetch(`/api/files/${courseName}/${fileName}`);
            const data = await response.json();
            
            this.showNoteEditor(courseName, fileName, data.content || '');
            
            // Update file selection
            document.querySelectorAll('.file-item').forEach(item => item.classList.remove('selected'));
            const selectedItem = [...document.querySelectorAll('.file-item')].find(item => 
                item.querySelector('span').textContent === fileName
            );
            if (selectedItem) selectedItem.classList.add('selected');
            
        } catch (error) {
            console.error('Failed to load note file:', error);
            this.showMessage('Failed to load note file', 'error');
        }
    }
    
    showNoteEditor(courseName, fileName, content) {
        const editorContainer = document.getElementById('editor-container');
        if (editorContainer) {
            editorContainer.innerHTML = `
                <div class="editor-header">
                    <div class="editor-info">
                        <h3>${fileName}</h3>
                        <span>Last modified: ${new Date().toLocaleString()}</span>
                    </div>
                    <div class="editor-actions">
                        <button class="btn btn-sm btn-success" onclick="app.saveCurrentNote()">
                            <i class="fas fa-save"></i> Save
                        </button>
                    </div>
                </div>
                <textarea id="note-editor" placeholder="Start writing your notes here...">${content}</textarea>
            `;
            
            // Store current file info for saving
            this.currentFile = { courseName, fileName };
        }
    }
    
    createNewNote(courseName) {
        const fileName = prompt('Enter note name:');
        if (fileName && fileName.trim()) {
            const cleanFileName = fileName.trim().replace(/[^a-zA-Z0-9\s\-_]/g, '') + '.txt';
            this.showNoteEditor(courseName, cleanFileName, '');
            this.currentFile = { courseName, fileName: cleanFileName };
        }
    }
    
    async saveCurrentNote() {
        if (!this.currentFile) return;
        
        const editor = document.getElementById('note-editor');
        if (!editor) return;
        
        try {
            const response = await fetch(`/api/files/${this.currentFile.courseName}/${this.currentFile.fileName}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    content: editor.value
                })
            });
            
            if (response.ok) {
                this.showMessage('Note saved successfully', 'success');
                // Refresh file list
                this.loadCourseNotes(this.currentFile.courseName);
            } else {
                this.showMessage('Failed to save note', 'error');
            }
        } catch (error) {
            console.error('Failed to save note:', error);
            this.showMessage('Failed to save note', 'error');
        }
    }
    
    async deleteNoteFile(event, courseName, fileName) {
        event.stopPropagation();
        
        if (confirm(`Are you sure you want to delete "${fileName}"?`)) {
            try {
                const response = await fetch(`/api/files/${courseName}/${fileName}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    this.showMessage('Note deleted successfully', 'success');
                    this.loadCourseNotes(courseName);
                } else {
                    this.showMessage('Failed to delete note', 'error');
                }
            } catch (error) {
                console.error('Failed to delete note:', error);
                this.showMessage('Failed to delete note', 'error');
            }
        }
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
    
    // Cleanup method for when the app is closed
    cleanup() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing app...');
    window.app = new CanvasNotesApp();
});

// Cleanup when page is unloaded
window.addEventListener('beforeunload', () => {
    if (window.app) {
        window.app.cleanup();
    }
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
