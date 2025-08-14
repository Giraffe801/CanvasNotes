import sys
import tkinter as tk
from tkinter import ttk
import tkinter.messagebox as messagebox
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
import subprocess
try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False
    import webbrowser

# Canvas Notes Dashboard
# Updated to only download new exe when applicable and HTML file with embedded CSS
# No longer downloads separate CSS, JS, or updater files

APP_VERSION = "0.0.0"
DEV_MODE = False

class DevLogger:
    """Logger class for dev mode that saves console output to a log file"""
    def __init__(self, log_file_path):
        self.log_file_path = log_file_path
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        # Create log file and directory if they don't exist
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        
        # Open log file in append mode
        self.log_file = open(log_file_path, 'a', encoding='utf-8')
        
        # Write session start marker
        self.log_file.write(f"\n{'='*50}\n")
        self.log_file.write(f"Session started: {datetime.now().isoformat()}\n")
        self.log_file.write(f"Canvas Dashboard v{APP_VERSION} - DEV MODE\n")
        self.log_file.write(f"{'='*50}\n")
        self.log_file.flush()
    
    def write(self, text):
        # Write to both console and log file
        self.original_stdout.write(text)
        self.log_file.write(text)
        self.log_file.flush()
    
    def flush(self):
        self.original_stdout.flush()
        self.log_file.flush()
    
    def close(self):
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.write(f"\nSession ended: {datetime.now().isoformat()}\n")
            self.log_file.write(f"{'='*50}\n\n")
            self.log_file.close()
        # Restore original stdout/stderr
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

class DevErrorLogger:
    """Error logger for stderr in dev mode"""
    def __init__(self, log_file, original_stderr):
        self.log_file = log_file
        self.original_stderr = original_stderr
    
    def write(self, text):
        # Write to both console and log file
        self.original_stderr.write(text)
        self.log_file.write(f"[ERROR] {text}")
        self.log_file.flush()
    
    def flush(self):
        self.original_stderr.flush()
        self.log_file.flush()

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
        # Clean up the URL and determine the API base
        self.original_url = base_url.rstrip('/')
        self.api_base = self._determine_api_base(base_url)
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def _determine_api_base(self, url: str) -> str:
        """Determine the correct API base URL"""
        url = url.rstrip('/')
        
        # If the URL already contains /api/v1, use it as-is
        if '/api/v1' in url:
            return url
        
        # If it's a basic Canvas URL, append the standard API path
        return f"{url}/api/v1"
    
    @property
    def base_url(self) -> str:
        """Return the original URL for display purposes"""
        return self.original_url
    
    def make_request(self, endpoint: str) -> Any:
        
        url = f"{self.api_base}/{endpoint}"
        
        try:
            print(f"Making Canvas API request to: {url}")
            request = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode())
                print(f"API request successful, received {len(data) if isinstance(data, list) else 'data'}")
                return data
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP {e.code} error: {e.reason}"
            if e.code == 401:
                error_msg += " - Check your access token"
            elif e.code == 403:
                error_msg += " - Access forbidden, check token permissions"
            elif e.code == 404:
                error_msg += " - API endpoint not found, check Canvas URL"
            print(f"Canvas API request failed: {error_msg}")
            print(f"Request URL: {url}")
            raise Exception(error_msg)
        except urllib.error.URLError as e:
            error_msg = f"Network error: {e.reason}"
            print(f"Canvas API request failed: {error_msg}")
            print(f"Request URL: {url}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            print(f"Canvas API request failed: {error_msg}")
            print(f"Request URL: {url}")
            raise Exception(error_msg)
    
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
        print(f"GET request for: {self.path}")
        
        if self.path == '/':
            # Serve index.html from src directory
            self.serve_src_file('index.html')
            return
        elif self.path.startswith('/api/'):
            self.handle_api_request()
            return
        elif self.path.startswith('/src/'):
            # Remove /src/ prefix and serve from src directory
            filename = self.path[5:]  # Remove '/src/' prefix
            self.serve_src_file(filename)
            return
        else:
            # For other paths, try to serve from src directory
            filename = self.path.lstrip('/')
            self.serve_src_file(filename)
            return
    
    def serve_src_file(self, filename):
        """Serve a file from the src directory"""
        try:
            if self.app_instance and hasattr(self.app_instance, 'src_dir'):
                file_path = self.app_instance.src_dir / filename
                print(f"Trying to serve: {file_path}")
                
                if file_path.exists() and file_path.is_file():
                    # Determine content type
                    content_type = 'text/html'
                    if filename.endswith('.css'):
                        content_type = 'text/css'
                    elif filename.endswith('.js'):
                        content_type = 'application/javascript'
                    elif filename.endswith('.json'):
                        content_type = 'application/json'
                    
                    # Read and serve the file
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    self.send_response(200)
                    self.send_header('Content-type', content_type)
                    self.send_header('Content-Length', len(content))
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(content)
                    print(f"Successfully served: {filename}")
                    return
                else:
                    print(f"File not found: {file_path}")
            
            # File not found
            self.send_error(404, f"File not found: {filename}")
            
        except Exception as e:
            print(f"Error serving file {filename}: {e}")
            self.send_error(500, f"Server error: {str(e)}")

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
            elif self.path == '/api/test-connection':
                self.handle_test_connection_request()
            elif self.path == '/api/save-config':
                self.handle_save_config_request()
            elif self.path == '/api/update-check':
                self.handle_update_check()
            elif self.path == '/api/src-update':
                self.handle_src_update_request()
            elif self.path == '/api/update-app':
                self.handle_app_update_request()
            elif self.path == '/api/update-complete':
                self.handle_complete_update_request()
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
            print(f"Config request - app_instance exists: {self.app_instance is not None}")
            if self.app_instance and hasattr(self.app_instance, 'canvas_api'):
                print(f"canvas_api exists: {self.app_instance.canvas_api is not None}")
                if self.app_instance.canvas_api:
                    config = {
                        'canvas_url': self.app_instance.canvas_api.base_url,
                        'canvas_token': self.app_instance.canvas_api.token,
                        'has_token': bool(self.app_instance.canvas_api.token)
                    }
                    print(f"Sending config: {{'canvas_url': '{config['canvas_url']}', 'token_length': {len(config['canvas_token'])}, 'has_token': {config['has_token']}}}")
                else:
                    print("canvas_api is None")
            else:
                print("app_instance or canvas_api attribute missing")
            self.send_json_response(config)
        
        elif self.command == 'POST':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            if self.app_instance:
                success = self.app_instance.save_api_config_from_web(data)
                self.send_json_response({'success': success})
    
    def handle_test_connection_request(self):
        """Handle API connection testing"""
        if self.command == 'POST':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                url = data.get('canvas_url', '').strip()
                token = data.get('canvas_token', '').strip()
                
                if not url or not token:
                    self.send_json_response({
                        'success': False, 
                        'error': 'Both URL and token are required'
                    })
                    return
                
                print(f"Testing Canvas connection to: {url}")
                
                # Test the connection
                test_api = CanvasAPI(url, token)
                print(f"API will connect to: {test_api.api_base}")
                
                test_courses = test_api.get_courses()  # This will raise an exception if it fails
                
                self.send_json_response({
                    'success': True, 
                    'message': f'Connection successful! Found {len(test_courses)} courses.',
                    'api_url': test_api.api_base,
                    'course_count': len(test_courses)
                })
                
            except Exception as e:
                error_msg = str(e)
                print(f"Canvas connection test failed: {error_msg}")
                
                # Provide helpful error messages
                if "401" in error_msg:
                    error_msg = "Invalid access token. Please check your Canvas API token."
                elif "403" in error_msg:
                    error_msg = "Access forbidden. Please check your token permissions."
                elif "404" in error_msg:
                    error_msg = "Canvas API not found. Please check your Canvas URL."
                elif "Network error" in error_msg or "URLError" in error_msg:
                    error_msg = f"Cannot connect to {url}. Please check the URL and your internet connection."
                
                self.send_json_response({
                    'success': False, 
                    'error': error_msg
                })
        else:
            self.send_error(405)  # Method not allowed
    
    def handle_save_config_request(self):
        """Handle saving API configuration"""
        if self.command == 'POST':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                if self.app_instance:
                    success = self.app_instance.save_api_config_from_web(data)
                    if success:
                        self.send_json_response({
                            'success': True, 
                            'message': 'Configuration saved successfully'
                        })
                    else:
                        self.send_json_response({
                            'success': False, 
                            'error': 'Failed to save configuration'
                        })
                else:
                    self.send_json_response({
                        'success': False, 
                        'error': 'App instance not available'
                    })
                    
            except Exception as e:
                self.send_json_response({
                    'success': False, 
                    'error': str(e)
                })
        else:
            self.send_error(405)  # Method not allowed
    
    def handle_update_check(self):
        if self.app_instance:
            # Get both app and src update info
            app_update_info = self.app_instance.check_for_updates_api()
            src_update_info = self.app_instance.check_src_folder_status()
            
            combined_info = {
                'app': app_update_info,
                'src': src_update_info,
                'dev_mode': DEV_MODE
            }
            self.send_json_response(combined_info)
    
    def handle_src_update_request(self):
        if self.command == 'GET':
            # Check if src folder needs updating
            if self.app_instance:
                src_status = self.app_instance.check_src_folder_status()
                self.send_json_response(src_status)
        elif self.command == 'POST':
            # Update src folder
            if self.app_instance:
                success = self.app_instance.update_src_folder()
                self.send_json_response({'success': success})
    
    def handle_app_update_request(self):
        if self.command == 'POST':
            # Trigger app update
            if self.app_instance:
                try:
                    # Get latest version first
                    update_info = self.app_instance.check_for_updates_api()
                    if update_info.get('has_update', False):
                        latest_version = update_info.get('latest_version', 'unknown')
                        
                        # Start update process in a separate thread
                        import threading
                        update_thread = threading.Thread(
                            target=self.app_instance.start_update_process, 
                            args=(latest_version,), 
                            daemon=True
                        )
                        update_thread.start()
                        
                        self.send_json_response({'success': True, 'message': 'Update started'})
                    else:
                        self.send_json_response({'success': False, 'message': 'No update available'})
                except Exception as e:
                    self.send_json_response({'success': False, 'message': str(e)})
            else:
                self.send_json_response({'success': False, 'message': 'App instance not available'})
    
    def handle_complete_update_request(self):
        if self.command == 'POST':
            # Handle complete update (both app and src)
            if self.app_instance:
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    if content_length > 0:
                        post_data = self.rfile.read(content_length)
                        data = json.loads(post_data.decode('utf-8'))
                        update_app = data.get('update_app', True)
                        update_src = data.get('update_src', True)
                    else:
                        update_app = True
                        update_src = True
                    
                    # Perform the update in a separate thread
                    import threading
                    
                    def update_thread():
                        results = self.app_instance.perform_complete_update(update_app, update_src)
                        print(f"Update results: {results}")
                    
                    thread = threading.Thread(target=update_thread, daemon=True)
                    thread.start()
                    
                    self.send_json_response({
                        'success': True, 
                        'message': 'Update process started',
                        'updating_app': update_app,
                        'updating_src': update_src
                    })
                    
                except Exception as e:
                    self.send_json_response({'success': False, 'message': str(e)})
            else:
                self.send_json_response({'success': False, 'message': 'App instance not available'})
    
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
        
        # Set src directory based on dev mode
        if DEV_MODE:
            # Use local src folder for development
            script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            self.src_dir = script_dir / "src"
            print("DEV MODE: Using local src folder")
        else:
            # Use data directory src folder for production
            self.src_dir = self.data_dir / "src"
        
        # Check if src folder exists, download if not (only in production mode)
        if not DEV_MODE:
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
        self.root.geometry("400x400")
        self.root.minsize(400, 400)
        
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
        
        # API Configuration Frame
        config_frame = tk.LabelFrame(main_frame, text="API Configuration", 
                                   font=("Segoe UI", 10, "bold"),
                                   fg="#4a9eff", bg="#0f1419", bd=1, relief="solid")
        config_frame.pack(pady=10, fill=tk.X)
        
        # Canvas URL Entry
        url_frame = tk.Frame(config_frame, bg="#0f1419")
        url_frame.pack(pady=5, fill=tk.X, padx=10)
        
        tk.Label(url_frame, text="Canvas URL:", 
                font=("Segoe UI", 9),
                fg="#ffffff", bg="#0f1419").pack(anchor=tk.W)
        
        self.url_entry = tk.Entry(url_frame, font=("Segoe UI", 9),
                                 bg="#1e2530", fg="#ffffff", insertbackground="#ffffff")
        self.url_entry.pack(fill=tk.X, pady=(2, 0))
        
        # Token Entry
        token_frame = tk.Frame(config_frame, bg="#0f1419")
        token_frame.pack(pady=5, fill=tk.X, padx=10)
        
        tk.Label(token_frame, text="Access Token:", 
                font=("Segoe UI", 9),
                fg="#ffffff", bg="#0f1419").pack(anchor=tk.W)
        
        self.token_entry = tk.Entry(token_frame, font=("Segoe UI", 9), show="*",
                                   bg="#1e2530", fg="#ffffff", insertbackground="#ffffff")
        self.token_entry.pack(fill=tk.X, pady=(2, 0))
        
        # Config buttons
        config_btn_frame = tk.Frame(config_frame, bg="#0f1419")
        config_btn_frame.pack(pady=10, padx=10)
        
        self.save_config_btn = tk.Button(config_btn_frame, text="Save Config", 
                                        command=self.save_api_config_gui,
                                        bg="#28a745", fg="white",
                                        font=("Segoe UI", 9, "bold"),
                                        padx=15, pady=5, cursor="hand2")
        self.save_config_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.test_config_btn = tk.Button(config_btn_frame, text="Test Connection", 
                                        command=self.test_api_connection,
                                        bg="#17a2b8", fg="white",
                                        font=("Segoe UI", 9, "bold"),
                                        padx=15, pady=5, cursor="hand2")
        self.test_config_btn.pack(side=tk.LEFT, padx=5)
        
        # Load existing config into fields
        self.load_config_into_gui()
        
        # Options dropdown menu
        options_frame = tk.Frame(main_frame, bg="#0f1419")
        options_frame.pack(pady=10, fill=tk.X)
        
        self.options_var = tk.StringVar(value="Options ▼")
        self.options_menu = tk.Menubutton(options_frame, textvariable=self.options_var,
                                         bg="#6c757d", fg="white", 
                                         font=("Segoe UI", 10, "bold"),
                                         padx=15, pady=8, cursor="hand2",
                                         relief=tk.RAISED, bd=1)
        self.options_menu.pack()
        
        # Create dropdown menu
        self.dropdown_menu = tk.Menu(self.options_menu, tearoff=0,
                                    bg="#2d3748", fg="white",
                                    activebackground="#4a9eff", activeforeground="white")
        self.options_menu.config(menu=self.dropdown_menu)
        
        # Add menu items
        self.dropdown_menu.add_command(label="Check for Updates", command=self.check_updates_manual)
        self.dropdown_menu.add_command(label="Update src Files", command=self.update_src_manual)
        self.dropdown_menu.add_separator()
        self.dropdown_menu.add_command(label="Refresh Courses", command=self.refresh_courses_manual)
        self.dropdown_menu.add_separator()
        self.dropdown_menu.add_command(label="Open Data Folder", command=self.open_data_folder)
        self.dropdown_menu.add_command(label="Clear Cache", command=self.clear_cache)
        self.dropdown_menu.add_separator()
        if DEV_MODE:
            self.dropdown_menu.add_command(label="DEV MODE: ON", state=tk.DISABLED)
        else:
            self.dropdown_menu.add_command(label="Production Mode", state=tk.DISABLED)
        
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
    
    def load_config_into_gui(self):
        """Load existing configuration into GUI fields"""
        if hasattr(self, 'canvas_api') and self.canvas_api:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, self.canvas_api.base_url)
            
            self.token_entry.delete(0, tk.END)
            self.token_entry.insert(0, self.canvas_api.token)
    
    def save_api_config_gui(self):
        """Save API configuration from GUI"""
        url = self.url_entry.get().strip()
        token = self.token_entry.get().strip()
        
        if not url or not token:
            messagebox.showerror("Error", "Please enter both Canvas URL and Access Token")
            return
        
        # Test the configuration first
        if self.test_api_connection(silent=True):
            messagebox.showinfo("Success", "API configuration saved and tested successfully!")
        else:
            result = messagebox.askyesno("Warning", 
                "API test failed. Save configuration anyway?")
            if not result:
                return
    
    def test_api_connection(self, silent=False):
        """Test API connection"""
        url = self.url_entry.get().strip()
        token = self.token_entry.get().strip()
        
        if not url or not token:
            if not silent:
                messagebox.showerror("Error", "Please enter both Canvas URL and Access Token")
            return False
        
        try:
            # Test the API connection
            test_api = CanvasAPI(url, token)
            test_courses = test_api.get_courses()
            
            # If successful, save the configuration
            self.canvas_api = test_api
            
            # Save to config file
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
            
            # Refresh courses
            self.refresh_courses_from_api()
            
            if not silent:
                messagebox.showinfo("Success", 
                    f"Connection successful! Found {len(test_courses)} courses.")
            
            return True
            
        except Exception as e:
            if not silent:
                messagebox.showerror("Connection Failed", 
                    f"Failed to connect to Canvas API:\n{str(e)}")
            return False
    
    def check_updates_manual(self):
        """Manually check for updates"""
        try:
            update_info = self.check_all_updates()
            
            app_info = update_info.get('app', {})
            src_info = update_info.get('src', {})
            
            message_parts = []
            
            # App update info
            if app_info.get('has_update', False):
                latest = app_info.get('latest_version', 'unknown')
                current = app_info.get('current_version', 'unknown')
                message_parts.append(f"App Update Available: {current} → {latest}")
            else:
                message_parts.append("App: Up to date")
            
            # Src update info
            if not DEV_MODE:
                if src_info.get('needs_update', False):
                    message_parts.append("Interface Files: Update available")
                else:
                    message_parts.append("Interface Files: Up to date")
            else:
                message_parts.append("Interface Files: Dev mode (local files)")
            
            message = "\n".join(message_parts)
            
            if update_info.get('has_any_update', False):
                result = messagebox.askyesno("Updates Available", 
                    f"{message}\n\nWould you like to update now?")
                if result:
                    self.perform_complete_update()
            else:
                messagebox.showinfo("No Updates", message)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to check for updates:\n{str(e)}")
    
    def update_src_manual(self):
        """Manually update src files"""
        if DEV_MODE:
            messagebox.showinfo("Dev Mode", "src file updates are disabled in development mode")
            return
        
        try:
            success = self.update_src_folder()
            if success:
                messagebox.showinfo("Success", "Interface files updated successfully!")
            else:
                messagebox.showerror("Error", "Failed to update interface files")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update interface files:\n{str(e)}")
    
    def refresh_courses_manual(self):
        """Manually refresh courses"""
        if not self.canvas_api:
            messagebox.showerror("Error", "Please configure Canvas API first")
            return
        
        try:
            success = self.refresh_courses_from_api()
            if success:
                course_count = len(self.courses)
                messagebox.showinfo("Success", f"Courses refreshed! Found {course_count} courses.")
            else:
                messagebox.showerror("Error", "Failed to refresh courses")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh courses:\n{str(e)}")
    
    def open_data_folder(self):
        """Open the data folder in file explorer"""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(self.data_dir))
            elif os.name == 'posix':  # macOS and Linux
                subprocess.call(['open' if sys.platform == 'darwin' else 'xdg-open', str(self.data_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open data folder:\n{str(e)}")
    
    def clear_cache(self):
        """Clear cached data"""
        result = messagebox.askyesno("Clear Cache", 
            "This will clear cached course data. Are you sure?")
        if result:
            try:
                if self.data_file.exists():
                    self.data_file.unlink()
                self.courses = []
                messagebox.showinfo("Success", "Cache cleared successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear cache:\n{str(e)}")
    
    def start_web_server(self):
        try:
            # Find available port
            self.server_port = self.find_free_port()
            
            # DON'T change working directory - serve files directly from src_dir
            print(f"Starting server on port {self.server_port}")
            print(f"Will serve src files from: {self.src_dir}")
            
            # Create server with custom handler
            handler = lambda *args, **kwargs: CanvasNotesServer(*args, app_instance=self, **kwargs)
            self.httpd = socketserver.TCPServer(("", self.server_port), handler)
            
            # Start server in background thread
            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()
            
            server_url = f"http://localhost:{self.server_port}"
            print("Server running successfully!")
            print(f"Server URL: {server_url}")
            print(f"Serving src from: {self.src_dir}")
            
            # Check if src files exist
            if self.src_dir.exists():
                src_files = list(self.src_dir.glob('*'))
                print(f"Available src files: {[f.name for f in src_files]}")
            else:
                print("WARNING: src directory does not exist!")
            
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
        """Check if src folder exists in data directory, download from latest release if not"""
        # if DEV_MODE:
        #     print("DEV MODE: Skipping src folder download check")
        #     return True
            
        print(f"Checking src folder at: {self.src_dir}")
        
        if self.src_dir.exists() and self.validate_src_folder(self.src_dir):
            print("src folder found and valid")
            return True
        
        print("src folder missing or incomplete, downloading from latest release...")
        success = self.download_src_folder()
        
        if not success:
            print("Failed to download src folder, creating minimal fallback...")
            self.create_minimal_src_folder()
            return False
        
        return True
    
    def validate_src_folder(self, src_dir):
        """Validate that src folder has required files"""
        required_files = ['index.html']  # Only HTML file needed now
        
        for file_name in required_files:
            file_path = src_dir / file_name
            if not file_path.exists():
                print(f"Missing required file: {file_name}")
                return False
            
            # Check if HTML file has minimum content
            if file_name == 'index.html':
                try:
                    content = file_path.read_text(encoding='utf-8')
                    if len(content) < 1000:  # Ensure it's not an empty or error page
                        print(f"HTML file appears to be incomplete ({len(content)} bytes)")
                        return False
                except Exception as e:
                    print(f"Error reading HTML file: {e}")
                    return False
        
        return True
    
    def download_src_folder(self):
        """Download only the HTML file from GitHub repository"""
        try:
            print("Downloading HTML file from GitHub repository...")
            
            # GitHub raw content base URL
            base_url = "https://raw.githubusercontent.com/Giraffe801/CanvasNotes/main/src/"
            
            # Only download the HTML file since CSS is embedded and no JS needed
            src_files = {
                'index.html': 'index.html'
            }
            
            # Create src directory in data folder
            self.src_dir.mkdir(exist_ok=True)
            print(f"Created src directory: {self.src_dir}")
            
            # Download the HTML file
            downloaded_files = 0
            for filename, url_path in src_files.items():
                try:
                    file_url = base_url + url_path
                    print(f"Downloading {filename} from {file_url}...")
                    
                    # Add headers to avoid GitHub rate limiting
                    request = urllib.request.Request(file_url)
                    request.add_header('User-Agent', 'CanvasNotes/1.0')
                    
                    with urllib.request.urlopen(request, timeout=30) as response:
                        content = response.read()
                        print(f"Downloaded {len(content)} bytes for {filename}")
                    
                    # Write file to src directory
                    file_path = self.src_dir / filename
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    # Verify the file was written
                    if file_path.exists():
                        file_size = file_path.stat().st_size
                        print(f"✓ Saved {filename} ({file_size} bytes)")
                        downloaded_files += 1
                    else:
                        print(f"✗ Failed to save {filename}")
                    
                except Exception as e:
                    print(f"✗ Failed to download {filename}: {e}")
            
            print(f"Download complete: {downloaded_files}/{len(src_files)} files")
            
            if downloaded_files >= 1:  # At least the HTML file downloaded
                print(f"Successfully downloaded {downloaded_files}/{len(src_files)} files")
                
                # List what we actually have
                print("Files in src directory:")
                for file_path in self.src_dir.glob('*'):
                    print(f"  - {file_path.name} ({file_path.stat().st_size} bytes)")
                
                # Validate downloaded files
                if self.validate_src_folder(self.src_dir):
                    print("src folder downloaded and validated successfully!")
                    return True
                else:
                    print("src folder validation failed")
            
            print(f"Insufficient files downloaded: {downloaded_files}/{len(src_files)}")
            return False
                
        except Exception as e:
            print(f"Failed to download src folder from GitHub: {e}")
            print("Creating minimal fallback src folder...")
            
            # Create minimal fallback files if download fails
            self.create_minimal_src_folder()
            return False
    
    def create_minimal_src_folder(self):
        """Create minimal src folder with basic HTML file if download fails"""
        print("Creating minimal src folder as fallback...")
        
        self.src_dir.mkdir(exist_ok=True)
        
        # Create minimal HTML with embedded CSS (no external dependencies)
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canvas Notes Dashboard</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 0; 
            background: linear-gradient(135deg, #0f1419 0%, #1a2332 100%); 
            color: white; 
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            text-align: center;
            padding: 50px;
            background: rgba(30, 40, 50, 0.8);
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        h1 {
            color: #4a9eff;
            margin-bottom: 20px;
            font-size: 2.5rem;
        }
        p {
            font-size: 1.2rem;
            line-height: 1.6;
            margin-bottom: 15px;
        }
        .status {
            color: #ffc107;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎓 Canvas Notes Dashboard</h1>
        <p class="status">Minimal fallback mode</p>
        <p>Please check your internet connection and try again.</p>
        <p>The application will attempt to download the latest interface files when connectivity is restored.</p>
    </div>
</body>
</html>"""
        
        # Write the minimal HTML file
        (self.src_dir / "index.html").write_text(html_content, encoding='utf-8')
        
        print("Minimal src folder created successfully with standalone HTML file")
    
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
        except Exception as e:
            return {
                'has_update': False,
                'current_version': APP_VERSION,
                'latest_version': APP_VERSION,
                'error': f'Failed to check for updates: {str(e)}'
            }
    
    def check_all_updates(self):
        """Check for both app and src updates"""
        app_update = self.check_for_updates_api()
        src_update = self.check_src_folder_status()
        
        return {
            'app': app_update,
            'src': src_update,
            'has_any_update': app_update.get('has_update', False) or src_update.get('needs_update', False),
            'dev_mode': DEV_MODE
        }
    
    def check_src_folder_status(self):
        """Check if src folder needs updating by comparing file checksums"""
        try:
            if DEV_MODE:
                return {
                    'needs_update': False,
                    'reason': 'Dev mode - using local src folder',
                    'files_checked': len(list(self.src_dir.glob('*'))) if self.src_dir.exists() else 0,
                    'dev_mode': True
                }
            
            if not self.src_dir.exists():
                return {
                    'needs_update': True,
                    'reason': 'src folder missing',
                    'files_checked': 0
                }
            
            # GitHub API to get latest commit info for src folder
            api_url = "https://api.github.com/repos/Giraffe801/CanvasNotes/commits?path=src&per_page=1"
            
            request = urllib.request.Request(api_url)
            with urllib.request.urlopen(request, timeout=10) as response:
                commits = json.loads(response.read().decode())
            
            if not commits:
                return {
                    'needs_update': False,
                    'reason': 'Unable to check remote updates',
                    'files_checked': 0
                }
            
            latest_commit_sha = commits[0]['sha']
            
            # Check if we have stored the last update commit
            stored_commit = self.get_stored_src_commit()
            
            needs_update = stored_commit != latest_commit_sha
            
            # Count local files (only HTML now)
            local_files = len(list(self.src_dir.glob('*.html')))
            
            return {
                'needs_update': needs_update,
                'reason': 'New version available' if needs_update else 'Up to date',
                'files_checked': local_files,
                'local_commit': stored_commit[:8] if stored_commit else 'unknown',
                'remote_commit': latest_commit_sha[:8]
            }
            
        except Exception as e:
            return {
                'needs_update': False,
                'reason': f'Error checking updates: {str(e)}',
                'files_checked': 0
            }
    
    def get_stored_src_commit(self):
        """Get the stored commit hash for src folder"""
        try:
            config = {}
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            return config.get('src_commit_hash', '')
        except:
            return ''
    
    def store_src_commit(self, commit_hash):
        """Store the commit hash for src folder"""
        try:
            config = {}
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            
            config['src_commit_hash'] = commit_hash
            config['src_last_updated'] = datetime.now().isoformat()
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Failed to store src commit hash: {e}")
    
    def update_src_folder(self):
        """Update the src folder with latest HTML file from GitHub"""
        try:
            if DEV_MODE:
                print("DEV MODE: Skipping src folder update - using local files")
                return False
                
            print("Updating HTML file...")
            
            # Get latest commit hash first
            api_url = "https://api.github.com/repos/Giraffe801/CanvasNotes/commits?path=src&per_page=1"
            request = urllib.request.Request(api_url)
            with urllib.request.urlopen(request, timeout=10) as response:
                commits = json.loads(response.read().decode())
            
            if commits:
                latest_commit_sha = commits[0]['sha']
            else:
                latest_commit_sha = 'unknown'
            
            # Download the updated HTML file
            self.download_src_folder()
            
            # Store the commit hash
            self.store_src_commit(latest_commit_sha)
            
            print("HTML file updated successfully!")
            return True
            
        except Exception as e:
            print(f"Failed to update HTML file: {e}")
            return False
    
    def perform_complete_update(self, update_app=True, update_src=True):
        """Perform a complete update of both app and src if requested"""
        results = {
            'app_updated': False,
            'src_updated': False,
            'errors': []
        }
        
        try:
            # Update src folder first if requested and not in dev mode
            if update_src and not DEV_MODE:
                print("Updating src folder...")
                src_success = self.update_src_folder()
                results['src_updated'] = src_success
                if not src_success:
                    results['errors'].append("Failed to update src folder")
            
            # Update app if requested
            if update_app:
                print("Checking for app updates...")
                app_update_info = self.check_for_updates_api()
                if app_update_info.get('has_update', False):
                    latest_version = app_update_info.get('latest_version')
                    print(f"Starting app update to version {latest_version}...")
                    self.start_update_process(latest_version)
                    results['app_updated'] = True
                else:
                    results['errors'].append("No app update available")
            
            return results
            
        except Exception as e:
            results['errors'].append(f"Update process failed: {str(e)}")
            return results
    
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
                    print(f"Loaded config from file: {config}")
                    if config.get('canvas_url') and config.get('canvas_token'):
                        print(f"Creating CanvasAPI with URL: {config['canvas_url']}")
                        self.canvas_api = CanvasAPI(config['canvas_url'], config['canvas_token'])
                        print("CanvasAPI created successfully")
                    else:
                        print("Config missing canvas_url or canvas_token")
            except Exception as e:
                print(f"Failed to load config: {e}")
        else:
            print(f"Config file does not exist: {self.config_file}")

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
        
        try:
            # Get comprehensive update info
            update_info = self.check_all_updates()
            
            # Handle app updates
            app_info = update_info.get('app', {})
            if app_info.get('has_update', False):
                latest_version = app_info.get('latest_version', 'unknown')
                self.show_update_notification(latest_version)
            
            # Handle src updates (only in production mode)
            if not DEV_MODE:
                src_info = update_info.get('src', {})
                if src_info.get('needs_update', False):
                    self.show_src_update_notification()
                    
        except Exception as e:
            print(f"Error checking for updates: {e}")

    def check_internet_connection(self):
        """Check if internet connection is available"""
        try:
            with urllib.request.urlopen('http://www.google.com', timeout=3):
                return True
        except:
            return False

    def show_update_notification(self, latest_version):
        """Show update notification"""
        if hasattr(self, 'root') and self.root:
            # Tkinter mode
            result = messagebox.askyesno(
                "Update Available", 
                f"Version {latest_version} is available. Would you like to update?"
            )
            if result:
                self.start_update_process(latest_version)
        else:
            # Webview mode or no GUI - just print for now
            print(f"Update Available: Version {latest_version} is available")
            print("Update can be triggered via web interface")
    
    def show_src_update_notification(self):
        """Show src folder update notification"""
        if hasattr(self, 'root') and self.root:
            # Tkinter mode
            result = messagebox.askyesno(
                "Interface Update Available", 
                "New web interface files are available. Would you like to update them?"
            )
            if result:
                success = self.update_src_folder()
                if success:
                    messagebox.showinfo("Update Complete", "Web interface files updated successfully!")
                else:
                    messagebox.showerror("Update Failed", "Failed to update web interface files.")
        else:
            # Webview mode or no GUI - just print for now
            print("Interface Update Available: New web interface files are available")
            print("Update can be triggered via web interface")

    def start_update_process(self, latest_version):
        """Start the update process - downloads new exe and HTML if applicable"""
        try:
            # First update the HTML file if not in dev mode
            if not DEV_MODE:
                print("Updating HTML file before application update...")
                try:
                    self.update_src_folder()
                    print("HTML file updated successfully")
                except Exception as e:
                    print(f"Failed to update HTML file: {e}")
            
            # Download new executable
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
            if hasattr(self, 'root') and self.root:
                self.root.destroy()
        except Exception as e:
            if hasattr(self, 'root'):
                messagebox.showerror("Update Failed", f"Update failed: {e}")
            else:
                print(f"Update failed: {e}")


def main():
    dev_logger = None
    error_logger = None
    
    # Initialize dev mode logging if enabled
    if DEV_MODE:
        try:
            script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            src_dir = script_dir / "src"
            src_dir.mkdir(exist_ok=True)
            log_file_path = src_dir / "canvas_dashboard.log"
            
            dev_logger = DevLogger(log_file_path)
            error_logger = DevErrorLogger(dev_logger.log_file, sys.stderr)
            
            sys.stdout = dev_logger
            sys.stderr = error_logger
            
            print(f"DEV MODE: Logging enabled to {log_file_path}")
            
        except Exception as e:
            print(f"Failed to initialize dev logging: {e}")
    
    try:
        app = SimpleDashboardApp()
        app.run()
    finally:
        # Clean up logger
        if dev_logger:
            dev_logger.close()

if __name__ == "__main__":
    main()

