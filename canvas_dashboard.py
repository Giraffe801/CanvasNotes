import sys
import tkinter as tk
from tkinter import ttk
import json
import os
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re
import tempfile
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import socket
try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False
    import webbrowser

APP_VERSION = "1.0.0"

@dataclass
class Course:
    id: int
    name: str
    course_code: str
    workflow_state: str
    term: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None

class CanvasAPI:

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def make_request(self, endpoint: str) -> Any:
        
        url = f"{self.base_url}/api/v1/{endpoint}"
        
        try:
            request = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            print(f"API request failed: {e}")
            return []
    
    def get_courses(self) -> List[Course]:
        courses_data = self.make_request("courses?enrollment_state=active&per_page=100")
        if not courses_data:
            return []
        
        courses = []
        for course_data in courses_data:
            term = self.extract_term(course_data)
            
            course = Course(
                id=course_data.get('id'),
                name=course_data.get('name', 'Unknown Course'),
                course_code=course_data.get('course_code', ''),
                workflow_state=course_data.get('workflow_state', 'available'),
                term=term,
                start_at=course_data.get('start_at'),
                end_at=course_data.get('end_at')
            )
            courses.append(course)
        
        return courses
    
    def extract_term(self, course_data: Dict) -> str:
        if 'term' in course_data and course_data['term']:
            return course_data['term'].get('name', '')

        name = course_data.get('name', '')
        course_code = course_data.get('course_code', '')

        term_pattern = r'(Fall|Spring|Summer|Winter)\s*(\d{4})'

        match = re.search(term_pattern, name, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        match = re.search(term_pattern, course_code, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        year_pattern = r'(\d{4})'
        match = re.search(year_pattern, name)
        if match:
            return match.group(1)
        
        match = re.search(year_pattern, course_code)
        if match:
            return match.group(1)

        term_id_pattern = r'Term:\s*(\d+)'
        if 'Term:' in name:
            match = re.search(term_id_pattern, name)
            if match:
                return f"Term: {match.group(1)}"
        
        return "Current Term"

class CanvasNotesServer(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, app_instance=None, **kwargs):
        self.app_instance = app_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/':
            self.path = '/src/index.html'
        elif self.path.startswith('/api/'):
            self.handle_api_request()
            return
        elif not self.path.startswith('/src/'):
            # Redirect requests for CSS, JS, and other assets to src folder
            if self.path.startswith('/'):
                self.path = '/src' + self.path
        return super().do_GET()
    
    def do_POST(self):
        if self.path.startswith('/api/'):
            self.handle_api_request()
        else:
            self.send_error(404)
    
    def handle_api_request(self):
        try:
            if self.path == '/api/courses':
                self.handle_courses_request()
            elif self.path == '/api/config':
                self.handle_config_request()
            elif self.path == '/api/update-check':
                self.handle_update_check()
            elif self.path.startswith('/api/files'):
                self.handle_file_request()
            else:
                self.send_error(404)
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_courses_request(self):
        if self.command == 'GET':
            courses_data = []
            if self.app_instance and self.app_instance.courses:
                for course in self.app_instance.courses:
                    courses_data.append({
                        'id': course.id,
                        'name': course.name,
                        'course_code': course.course_code,
                        'workflow_state': course.workflow_state,
                        'term': course.term,
                        'start_at': course.start_at,
                        'end_at': course.end_at
                    })
            
            self.send_json_response(courses_data)
        
        elif self.command == 'POST':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            if self.app_instance:
                self.app_instance.refresh_courses_from_api()
                self.send_json_response({'success': True})
    
    def handle_config_request(self):
        if self.command == 'GET':
            config = {}
            if self.app_instance and hasattr(self.app_instance, 'canvas_api'):
                if self.app_instance.canvas_api:
                    config = {
                        'canvas_url': self.app_instance.canvas_api.base_url,
                        'has_token': bool(self.app_instance.canvas_api.token)
                    }
            self.send_json_response(config)
        
        elif self.command == 'POST':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            if self.app_instance:
                success = self.app_instance.save_api_config_from_web(data)
                self.send_json_response({'success': success})
    
    def handle_update_check(self):
        if self.app_instance:
            update_info = self.app_instance.check_for_updates_api()
            self.send_json_response(update_info)
    
    def handle_file_request(self):
        path_parts = self.path.split('/')
        if len(path_parts) >= 4:
            course_name = path_parts[3]
            
            if self.command == 'GET':
                files = self.app_instance.get_course_files(course_name)
                self.send_json_response(files)
            
            elif self.command == 'POST':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                success = self.app_instance.save_course_file(
                    course_name, data.get('filename'), data.get('content'))
                self.send_json_response({'success': success})
    
    def send_json_response(self, data):
        json_data = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', len(json_data))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json_data)

class SimpleDashboardApp:

    def __init__(self):
        self.canvas_api = None
        self.courses = []
        self.hidden_courses = set()
        self.showing_past = False
        self.server_port = 8080
        self.server_thread = None
        self.httpd = None

        import os
        documents_path = Path.home() / "Documents"
        self.data_dir = documents_path / "CanvasData"
        self.data_dir.mkdir(exist_ok=True)

        self.data_file = self.data_dir / "canvas_courses.json"
        self.config_file = self.data_dir / "canvas_config.json"
        
        # Check if src folder exists, download if not
        self.ensure_src_folder_exists()
        
        self.load_config()
        self.load_hidden_courses()
        self.load_cached_courses()

        # Start web server first
        self.start_web_server()
        
        # Initialize UI based on available libraries
        if HAS_WEBVIEW:
            self.setup_webview()
        else:
            self.setup_tkinter_fallback()
    
    def setup_webview(self):
        """Setup embedded webview interface"""
        # Wait for server to start
        threading.Event().wait(1)
        
        # Create webview window
        self.webview_window = webview.create_window(
            'Canvas Notes',
            f'http://localhost:{self.server_port}',
            width=1200,
            height=800,
            min_size=(800, 600),
            resizable=True,
            shadow=True,
            on_top=False
        )
        
        # Set up shutdown callback
        def on_window_closed():
            self.cleanup_server()
        
        # Store the callback for cleanup (webview handles window close differently)
        self.on_close_callback = on_window_closed
    
    def setup_tkinter_fallback(self):
        """Setup fallback Tkinter interface if webview not available"""
        self.root = tk.Tk()
        self.setup_window()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(1000, self.check_for_updates_startup)
        self.root.after(2000, self.open_web_interface_external)
    
    def calculate_time_remaining(self, course: Course) -> str:
        if not course.end_at:
            return "No end date"
        
        try:
            from datetime import datetime, timezone
            
            end_date = datetime.fromisoformat(course.end_at.replace('Z', '+00:00'))
            current_date = datetime.now(timezone.utc)
            
            time_diff = end_date - current_date
            
            if time_diff.total_seconds() <= 0:
                return "Ended"
            
            days = time_diff.days
            
            if days > 365:
                years = days // 365
                return f"{years}y {days % 365}d left"
            elif days > 30:
                months = days // 30
                return f"{months}m {days % 30}d left"
            elif days > 0:
                return f"{days} days left"
            else:
                hours = int(time_diff.total_seconds() // 3600)
                if hours > 0:
                    return f"{hours}h left"
                else:
                    return "<1h left"
                    
        except Exception as e:
            return "Date error"
    
    def setup_window(self):
        self.root.title("Canvas Notes Server")
        self.root.geometry("400x300")
        self.root.minsize(400, 300)
        
        # Create simple server status window
        main_frame = tk.Frame(self.root, bg="#0f1419")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        title_label = tk.Label(main_frame, text="Canvas Notes", 
                              font=("Segoe UI", 20, "bold"),
                              fg="#4a9eff", bg="#0f1419")
        title_label.pack(pady=(0, 20))
        
        self.status_label = tk.Label(main_frame, text="Starting server...", 
                                    font=("Segoe UI", 12),
                                    fg="#ffffff", bg="#0f1419")
        self.status_label.pack(pady=10)
        
        self.url_label = tk.Label(main_frame, text="", 
                                 font=("Segoe UI", 10),
                                 fg="#8892b0", bg="#0f1419")
        self.url_label.pack(pady=5)
        
        button_frame = tk.Frame(main_frame, bg="#0f1419")
        button_frame.pack(pady=20)
        
        self.open_btn = tk.Button(button_frame, text="Open in Browser", 
                                 command=self.open_web_interface,
                                 bg="#4a9eff", fg="white",
                                 font=("Segoe UI", 10, "bold"),
                                 padx=20, pady=8, cursor="hand2")
        self.open_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.quit_btn = tk.Button(button_frame, text="Quit", 
                                 command=self.on_closing,
                                 bg="#dc3545", fg="white",
                                 font=("Segoe UI", 10, "bold"),
                                 padx=20, pady=8, cursor="hand2")
        self.quit_btn.pack(side=tk.LEFT)
        
        self.root.configure(bg="#0f1419")
    
    def start_web_server(self):
        try:
            # Find available port
            self.server_port = self.find_free_port()
            
            # Change to the directory containing src folder
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            
            # Create server with custom handler
            handler = lambda *args, **kwargs: CanvasNotesServer(*args, app_instance=self, **kwargs)
            self.httpd = socketserver.TCPServer(("", self.server_port), handler)
            
            # Start server in background thread
            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()
            
            server_url = f"http://localhost:{self.server_port}"
            print("Server running successfully!")
            print(f"Server URL: {server_url}")
            
            # Only update GUI elements if they exist (tkinter mode)
            if hasattr(self, 'status_label'):
                self.status_label.config(text="Server running successfully!")
            if hasattr(self, 'url_label'):
                self.url_label.config(text=server_url)
            
        except Exception as e:
            print(f"Failed to start server: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Failed to start server: {e}")
    
    def find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def ensure_src_folder_exists(self):
        """Check if src folder exists, download from latest release if not"""
        script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        src_dir = script_dir / "src"
        
        if src_dir.exists() and self.validate_src_folder(src_dir):
            print("src folder found and valid")
            return
        
        print("src folder missing or incomplete, downloading from latest release...")
        self.download_src_folder(script_dir)
    
    def validate_src_folder(self, src_dir):
        """Validate that src folder has required files"""
        required_files = ['index.html', 'styles.css', 'app.js', 'updater.js']
        
        for file_name in required_files:
            file_path = src_dir / file_name
            if not file_path.exists():
                print(f"Missing required file: {file_name}")
                return False
        
        return True
    
    def download_src_folder(self, script_dir):
        """Download src folder files directly from GitHub repository"""
        try:
            print("Downloading src files from GitHub repository...")
            
            # GitHub raw content base URL
            base_url = "https://raw.githubusercontent.com/Giraffe801/CanvasNotes/main/src/"
            
            # List of files to download from src folder
            src_files = {
                'index.html': 'index.html',
                'styles.css': 'styles.css', 
                'app.js': 'app.js',
                'updater.js': 'updater.js'
            }
            
            # Create src directory
            src_dir = script_dir / "src"
            src_dir.mkdir(exist_ok=True)
            
            # Download each file
            downloaded_files = 0
            for filename, url_path in src_files.items():
                try:
                    file_url = base_url + url_path
                    print(f"Downloading {filename}...")
                    
                    request = urllib.request.Request(file_url)
                    with urllib.request.urlopen(request, timeout=10) as response:
                        content = response.read()
                    
                    # Write file to src directory
                    file_path = src_dir / filename
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    downloaded_files += 1
                    print(f"✓ Downloaded {filename}")
                    
                except Exception as e:
                    print(f"✗ Failed to download {filename}: {e}")
            
            if downloaded_files >= 3:  # At least 3 core files downloaded
                print(f"Successfully downloaded {downloaded_files}/{len(src_files)} files")
                
                # Validate downloaded files
                if self.validate_src_folder(src_dir):
                    print("src folder downloaded and validated successfully!")
                    return
            
            raise Exception(f"Only {downloaded_files}/{len(src_files)} files downloaded successfully")
                
        except Exception as e:
            print(f"Failed to download src folder from GitHub: {e}")
            print("Creating minimal fallback src folder...")
            
            # Create minimal fallback files if download fails
            self.create_minimal_src_folder(script_dir)
    
    def create_minimal_src_folder(self, script_dir):
        """Create minimal src folder with basic files if download fails"""
        print("Creating minimal src folder as fallback...")
        
        src_dir = script_dir / "src"
        src_dir.mkdir(exist_ok=True)
        
        # Create minimal HTML
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canvas Notes Dashboard</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div id="loading-screen" class="loading-screen">
        <div class="loading-content">
            <h2>Canvas Notes</h2>
            <p>Minimal fallback mode - please check internet connection</p>
        </div>
    </div>
    <div id="main-app" class="main-app" style="display: none;">
        <h1>Canvas Notes</h1>
        <p>Please configure your Canvas API to get started.</p>
    </div>
    <script src="app.js"></script>
</body>
</html>"""
        
        # Create minimal CSS
        css_content = """body { 
    font-family: Arial, sans-serif; 
    margin: 0; 
    padding: 20px; 
    background: #0f1419; 
    color: white; 
}
.loading-screen { 
    text-align: center; 
    padding: 50px; 
}
.main-app { 
    padding: 20px; 
}"""
        
        # Create minimal JS
        js_content = """document.addEventListener('DOMContentLoaded', () => {
    const loadingScreen = document.getElementById('loading-screen');
    const mainApp = document.getElementById('main-app');
    
    setTimeout(() => {
        loadingScreen.style.display = 'none';
        mainApp.style.display = 'block';
    }, 1000);
});"""
        
        # Create minimal updater
        updater_content = """console.log('Canvas Notes Updater - Minimal Mode');"""
        
        # Write files
        (src_dir / "index.html").write_text(html_content, encoding='utf-8')
        (src_dir / "styles.css").write_text(css_content, encoding='utf-8')
        (src_dir / "app.js").write_text(js_content, encoding='utf-8')
        (src_dir / "updater.js").write_text(updater_content, encoding='utf-8')
        
        print("Minimal src folder created successfully")
    
    def cleanup_server(self):
        """Clean up server resources"""
        try:
            if hasattr(self, 'httpd') and self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception as e:
            print(f"Error during server cleanup: {e}")
        
        try:
            if hasattr(self, 'server_thread') and self.server_thread:
                self.server_thread.join(timeout=1.0)
        except:
            pass

    def open_web_interface(self):
        """Open web interface in external browser (fallback only)"""
        if self.server_port and not HAS_WEBVIEW:
            webbrowser.open(f"http://localhost:{self.server_port}")
    
    def open_web_interface_external(self):
        """Alias for backward compatibility"""
        self.open_web_interface()
    
    def refresh_courses_from_api(self):
        if not self.canvas_api:
            return False
        
        try:
            self.courses = self.canvas_api.get_courses()
            self.save_courses_to_cache(self.courses)
            return True
        except Exception as e:
            print(f"Failed to refresh courses: {e}")
            return False
    
    def save_api_config_from_web(self, data):
        url = data.get('canvas_url', '').strip()
        token = data.get('canvas_token', '').strip()
        
        if not url or not token:
            return False
        
        try:
            test_api = CanvasAPI(url, token)
            test_courses = test_api.get_courses()
            
            self.canvas_api = test_api
            
            config_data = {}
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
            
            config_data.update({
                'canvas_url': url,
                'canvas_token': token,
                'last_updated': datetime.now().isoformat()
            })
            
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Failed to save API config: {e}")
            return False
    
    def check_for_updates_api(self):
        try:
            version_url = "https://raw.githubusercontent.com/Giraffe801/CanvasNotes/main/version.txt"
            with urllib.request.urlopen(version_url, timeout=5) as response:
                latest_version = response.read().decode().strip()
            
            return {
                'has_update': latest_version != APP_VERSION,
                'current_version': APP_VERSION,
                'latest_version': latest_version
            }
        except Exception:
            return {
                'has_update': False,
                'current_version': APP_VERSION,
                'latest_version': APP_VERSION,
                'error': 'Failed to check for updates'
            }
    
    def get_course_files(self, course_name):
        try:
            course_notes_dir = self.data_dir / "course_notes"
            safe_course_name = "".join(c for c in course_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            course_dir = course_notes_dir / safe_course_name
            
            if not course_dir.exists():
                return {}
            
            files = {}
            for file_path in course_dir.glob("*.txt"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        files[file_path.name] = f.read()
                except:
                    files[file_path.name] = ""
            
            return files
        except Exception:
            return {}
    
    def save_course_file(self, course_name, filename, content):
        try:
            course_notes_dir = self.data_dir / "course_notes"
            course_notes_dir.mkdir(exist_ok=True)
            
            safe_course_name = "".join(c for c in course_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            course_dir = course_notes_dir / safe_course_name
            course_dir.mkdir(exist_ok=True)
            
            if not filename.endswith('.txt'):
                filename += '.txt'
            
            file_path = course_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"Failed to save file: {e}")
            return False
    
    def run(self):
        """Run the application"""
        if HAS_WEBVIEW:
            # Run webview application
            try:
                webview.start(debug=False)
            finally:
                # Cleanup when webview closes
                if hasattr(self, 'on_close_callback'):
                    self.on_close_callback()
        else:
            # Run Tkinter fallback
            if hasattr(self, 'root'):
                self.root.mainloop()

    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    if config.get('canvas_url') and config.get('canvas_token'):
                        self.canvas_api = CanvasAPI(config['canvas_url'], config['canvas_token'])
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save_courses_to_cache(self, courses: List[Course]):
        try:
            courses_data = []
            for course in courses:
                course_dict = {
                    'id': course.id,
                    'name': course.name,
                    'course_code': course.course_code,
                    'workflow_state': course.workflow_state,
                    'term': course.term,
                    'start_at': course.start_at,
                    'end_at': course.end_at
                }
                courses_data.append(course_dict)
            
            cache_data = {
                'courses': courses_data,
                'last_updated': datetime.now().isoformat(),
                'total_courses': len(courses_data)
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
        except Exception as e:
            print(f"Failed to save courses to cache: {e}")
    
    def load_cached_courses(self):
        if not self.data_file.exists():
            return
            
        try:
            with open(self.data_file, 'r') as f:
                cache_data = json.load(f)
                
            courses_data = cache_data.get('courses', [])
            self.courses = []
            
            for course_dict in courses_data:
                course = Course(
                    id=course_dict.get('id'),
                    name=course_dict.get('name', 'Unknown Course'),
                    course_code=course_dict.get('course_code', ''),
                    workflow_state=course_dict.get('workflow_state', 'available'),
                    term=course_dict.get('term'),
                    start_at=course_dict.get('start_at'),
                    end_at=course_dict.get('end_at')
                )
                self.courses.append(course)
                
        except Exception as e:
            print(f"Failed to load cached courses: {e}")

    def load_hidden_courses(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    hidden_list = config.get('hidden_courses', [])
                    self.hidden_courses = set(hidden_list)
            else:
                self.hidden_courses = set()
        except Exception as e:
            print(f"Failed to load hidden courses: {e}")
            self.hidden_courses = set()

    def save_hidden_courses(self):
        try:
            config = {}
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            
            config['hidden_courses'] = list(self.hidden_courses)
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Failed to save hidden courses: {e}")

    def on_closing(self):
        """Handle application closing"""
        self.cleanup_server()
        
        # Destroy the root window if it exists (Tkinter fallback)
        if hasattr(self, 'root'):
            self.root.destroy()

    def check_for_updates_startup(self):
        """Check for updates on startup"""
        if not self.check_internet_connection():
            return
            
        import urllib.request
        version_url = "https://raw.githubusercontent.com/Giraffe801/CanvasNotes/main/version.txt"
        
        try:
            with urllib.request.urlopen(version_url, timeout=5) as response:
                latest_version = response.read().decode().strip()
            if latest_version != APP_VERSION:
                self.show_update_notification(latest_version)
        except Exception:
            pass

    def check_internet_connection(self):
        """Check if internet connection is available"""
        try:
            import urllib.request
            with urllib.request.urlopen('http://www.google.com', timeout=3):
                return True
        except:
            return False

    def show_update_notification(self, latest_version):
        """Show update notification"""
        import tkinter.messagebox as messagebox
        result = messagebox.askyesno(
            "Update Available", 
            f"Version {latest_version} is available. Would you like to update?"
        )
        if result:
            self.start_update_process(latest_version)

    def start_update_process(self, latest_version):
        """Start the update process"""
        try:
            import urllib.request
            import sys
            import tempfile
            import os
            
            exe_url = "https://github.com/Giraffe801/CanvasNotes/releases/latest/download/canvas_dashboard.exe"
            
            tmp_dir = tempfile.gettempdir()
            new_exe_path = os.path.join(tmp_dir, "canvas_dashboard_new.exe")
            with urllib.request.urlopen(exe_url) as response, open(new_exe_path, "wb") as out_file:
                out_file.write(response.read())
            old_exe = sys.argv[0]
            bat_path = os.path.join(tmp_dir, "update_canvas_dashboard.bat")
            with open(bat_path, "w") as bat:
                bat.write(f"""
@echo off
timeout /t 2 >nul
move /y "{new_exe_path}" "{old_exe}"
start "" "{old_exe}"
del "%~f0"
""")
            os.startfile(bat_path)
            self.root.destroy()
        except Exception as e:
            import tkinter.messagebox as messagebox
            messagebox.showerror("Update Failed", f"Update failed: {e}")


def main():
    app = SimpleDashboardApp()
    app.run()

if __name__ == "__main__":
    main()

