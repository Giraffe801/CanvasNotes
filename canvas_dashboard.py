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
import webbrowser
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re
import tempfile

APP_VERSION = "1.1.0"

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

class SimpleDashboardApp:

    def __init__(self):
        self.root = tk.Tk()
        self.canvas_api = None
        self.courses = []
        self.hidden_courses = set()
        self.showing_past = False

        import os
        documents_path = Path.home() / "Documents"
        self.data_dir = documents_path / "CanvasData"
        self.data_dir.mkdir(exist_ok=True)

        self.data_file = self.data_dir / "canvas_courses.json"
        self.config_file = self.data_dir / "canvas_config.json"
        
        self.setup_window()
        self.setup_styles()
        self.create_widgets()
        self.load_config()
        self.load_hidden_courses()
        self.load_cached_courses()

        self.notifications = []
        self.notification_frame = None
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
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
        self.root.title("My Courses")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
    
    def setup_styles(self):
        style = ttk.Style()
        
        self.bg_color = "#0f1419"
        self.card_color = "#1e2832"
        self.text_color = "#ffffff"
        self.accent_color = "#4a9eff"
        self.secondary_color = "#8892b0"
        self.success_color = "#28a745"
        self.warning_color = "#ffc107"
        self.error_color = "#dc3545"
        
        style.theme_use('clam')
        style.configure('TFrame', background=self.bg_color)
        style.configure('TLabel', background=self.bg_color, foreground=self.text_color)
        style.configure('TButton', background=self.accent_color, foreground='white', padding=(10, 5))
        style.configure('Card.TFrame', background=self.card_color, relief='solid', borderwidth=1)
        style.configure('TLabelFrame', background=self.bg_color, foreground=self.text_color)
        style.configure('TNotebook', background=self.bg_color)
        style.configure('TNotebook.Tab', background=self.bg_color, foreground=self.text_color)
        
        self.root.configure(bg=self.bg_color)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="My Courses", 
                               font=("Segoe UI", 24, "bold"))
        title_label.pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(header_frame, text="", 
                                     font=("Segoe UI", 9), foreground="#7f8c8d")
        self.status_label.pack(side=tk.LEFT, padx=(20, 0))
        
        self.update_status_label()
        
        button_frame = ttk.Frame(header_frame)
        button_frame.pack(side=tk.RIGHT)
        
        view_menu_btn = tk.Menubutton(button_frame, text="View Options ▼", 
                                     bg=self.accent_color, fg="white", 
                                     font=("Segoe UI", 10, "bold"), 
                                     bd=0, padx=15, pady=6, cursor="hand2",
                                     relief="flat", activebackground=self.secondary_color)
        view_menu_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        view_menu = tk.Menu(view_menu_btn, tearoff=0, bg=self.card_color, fg=self.text_color,
                           activebackground=self.accent_color, activeforeground="white",
                           bd=1, relief="solid", font=("Segoe UI", 9))
        view_menu_btn.config(menu=view_menu)
        
        view_menu.add_command(label="Show All Courses", command=self.show_all_courses)
        view_menu.add_command(label="Show Hidden Courses", command=self.show_hidden_courses)
        view_menu.add_command(label="Hide Hidden Courses", command=self.hide_hidden_courses)
        view_menu.add_separator()
        view_menu.add_command(label="View Past Courses", command=self.view_past_courses)
        view_menu.add_separator()
        view_menu.add_command(label="Check for Updates", command=self.check_for_updates_button)
        
        ttk.Button(button_frame, text="Configure API", command=self.configure_api).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Refresh", command=self.refresh_courses).pack(side=tk.LEFT)

        self.create_scrollable_frame(main_frame)
        
        self.create_notification_area()
    
    def create_scrollable_frame(self, parent):
        container = tk.Frame(parent, bg=self.bg_color)
        container.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(container, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=self.bg_color)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.update_scroll_region()
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        
        self.canvas = canvas
        self.scrollbar = scrollbar
        
        def _on_mousewheel(event):
            try:
                if self.canvas.winfo_exists():
                    self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except:
                pass
        
        self._mousewheel_handler = _on_mousewheel
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def update_scroll_region(self):
        if not hasattr(self, 'canvas') or not hasattr(self, 'scrollbar'):
            return
            
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        canvas_height = self.canvas.winfo_height()
        content_height = self.scrollable_frame.winfo_reqheight()
        
        if content_height > canvas_height:
            if not self.scrollbar.winfo_viewable():
                self.scrollbar.pack(side="right", fill="y")
        else:
            if self.scrollbar.winfo_viewable():
                self.scrollbar.pack_forget()
    
    def create_course_card(self, course: Course, row: int, col: int):
        card_frame = tk.Frame(self.scrollable_frame, bg=self.card_color, 
                             relief='solid', bd=1, padx=20, pady=15)
        card_frame.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        
        self.scrollable_frame.grid_columnconfigure(col, weight=1)
        
        controls_frame = tk.Frame(card_frame, bg=self.card_color)
        controls_frame.pack(fill=tk.X, pady=(0, 8))
        
        time_remaining = self.calculate_time_remaining(course)
        time_indicator = tk.Label(controls_frame, text="⏰", fg=self.accent_color, 
                                 bg=self.card_color, font=("Segoe UI", 10))
        time_indicator.pack(side=tk.LEFT)
        
        time_label = tk.Label(controls_frame, text=time_remaining, 
                             fg=self.accent_color, bg=self.card_color,
                             font=("Segoe UI", 9), anchor="w")
        time_label.pack(side=tk.LEFT, padx=(5, 0))
        
        hide_btn = tk.Label(controls_frame, text="⨯", fg=self.secondary_color, 
                           bg=self.card_color, font=("Segoe UI", 12, "bold"), 
                           cursor="hand2")
        hide_btn.pack(side=tk.RIGHT)
        hide_btn.bind("<Button-1>", lambda e: self.hide_course(course))
        
        course_name = course.name.replace(course.course_code, "").strip()
        if not course_name:
            course_name = course.name
        
        name_label = tk.Label(card_frame, text=course_name, 
                             fg=self.text_color, bg=self.card_color,
                             font=("Segoe UI", 16, "bold"), anchor="w")
        name_label.pack(fill=tk.X, pady=(0, 8))
        
        if course.course_code:
            code_label = tk.Label(card_frame, text=course.course_code, 
                                 fg=self.secondary_color, bg=self.card_color,
                                 font=("Segoe UI", 12), anchor="w")
            code_label.pack(fill=tk.X, pady=(0, 5))
        
        id_label = tk.Label(card_frame, text=f"Course ID: {course.id}", 
                           fg=self.secondary_color, bg=self.card_color,
                           font=("Segoe UI", 10), anchor="w")
        id_label.pack(fill=tk.X, pady=(0, 10))
        
        def on_card_click(event):
            self.open_course_details(course)
        
        clickable_widgets = [card_frame, name_label, id_label]
        if course.course_code:
            clickable_widgets.append(code_label)
        
        for widget in clickable_widgets:
            widget.bind("<Button-1>", on_card_click)
    
    def create_notification_area(self):
        if hasattr(self, 'notification_frame') and self.notification_frame:
            try:
                self.notification_frame.destroy()
            except:
                pass
        
        if not hasattr(self, 'notifications'):
            self.notifications = []
        
        self.notification_frame = tk.Frame(self.root, bg=self.bg_color)
        self.notification_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=20)
        
        self.notification_frame.lift()
    
    def show_notification(self, message: str, notification_type: str = "info", duration: int = 3000):
        if not self.notification_frame or not self.notification_frame.winfo_exists():
            self.create_notification_area()
        
        colors = {
            "info": (self.accent_color, "white"),
            "success": (self.success_color, "white"),
            "warning": (self.warning_color, "black"),
            "error": (self.error_color, "white")
        }
        
        bg_color, text_color = colors.get(notification_type, colors["info"])
        
        notification = tk.Frame(self.notification_frame, bg=bg_color, 
                               relief="solid", bd=1, padx=15, pady=10)
        notification.pack(fill=tk.X, pady=(0, 10))
        
        label = tk.Label(notification, text=message, bg=bg_color, fg=text_color,
                        font=("Segoe UI", 10), wraplength=300)
        label.pack(side=tk.LEFT)
        
        close_btn = tk.Label(notification, text="✕", bg=bg_color, fg=text_color,
                            font=("Segoe UI", 12, "bold"), cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=(10, 0))
        close_btn.bind("<Button-1>", lambda e: self.hide_notification(notification))
        
        self.notifications.append(notification)
        
        if self.notification_frame and self.notification_frame.winfo_exists():
            self.notification_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=20)
            self.notification_frame.lift()
        
        if duration > 0:
            self.root.after(duration, lambda: self.hide_notification(notification))
        
        return notification
    
    def hide_notification(self, notification):
        try:
            if hasattr(self, 'notifications') and notification in self.notifications:
                self.notifications.remove(notification)
            if notification and notification.winfo_exists():
                notification.destroy()
            
            if hasattr(self, 'notifications') and hasattr(self, 'notification_frame'):
                if len(self.notifications) == 0:
                    if self.notification_frame and self.notification_frame.winfo_exists():
                        self.notification_frame.place_forget()
                else:
                    for i, remaining_notification in enumerate(self.notifications):
                        if remaining_notification and remaining_notification.winfo_exists():
                            remaining_notification.pack_forget()
                            remaining_notification.pack(fill=tk.X, pady=(0, 10))
                
        except Exception as e:
            pass
    
    def clear_notifications(self):
        for notification in self.notifications[:]:
            self.hide_notification(notification)
        
        if hasattr(self, 'notification_frame') and self.notification_frame:
            try:
                self.notification_frame.place_forget()
            except:
                pass
    
    def refresh_courses(self):
        if not self.canvas_api:
            self.show_notification("Please configure Canvas API first", "warning")
            self.configure_api()
            return
        
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        loading_label = ttk.Label(self.scrollable_frame, text="Loading courses...", 
                                 font=("Segoe UI", 12))
        loading_label.pack(pady=20)
        
        def load_courses():
            try:
                self.courses = self.canvas_api.get_courses()
                self.save_courses_to_cache(self.courses)
                self.root.after(0, self.display_courses)
                self.root.after(0, self.update_status_label)
                self.root.after(0, lambda: self.show_notification("Courses refreshed successfully", "success"))
            except Exception as e:
                self.root.after(0, lambda: self.show_notification(f"Failed to load courses: {str(e)}", "error"))
                self.root.after(0, lambda: loading_label.configure(text="Failed to load courses. Using cached data if available."))
                self.root.after(0, self.display_courses)
        
        threading.Thread(target=load_courses, daemon=True).start()
    
    def display_courses(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if not self.courses:
            no_courses_label = ttk.Label(self.scrollable_frame, 
                                        text="No courses found. Check your Canvas configuration.",
                                        font=("Segoe UI", 12))
            no_courses_label.pack(pady=20)
            return
        
        columns = 3
        visible_course_count = 0
        
        for course in self.courses:
            if course.id not in self.hidden_courses:
                row = visible_course_count // columns
                col = visible_course_count % columns
                self.create_course_card(course, row, col)
                visible_course_count += 1
        
        self.root.update_idletasks()
        self.update_scroll_region()
    
    def hide_course(self, course: Course):
        self.hidden_courses.add(course.id)
        self.save_hidden_courses()
        self.display_courses()
        self.show_notification(f"Course '{course.name}' has been hidden", "info")
    
    def show_all_courses(self):
        self.showing_hidden = False
        self.showing_past = False
        self.display_courses()
        self.show_notification("Showing only active courses", "info")
    
    def show_hidden_courses(self):
        self.showing_hidden = True
        self.showing_past = False
        self.display_all_courses()
        self.show_notification("Now showing hidden courses alongside active courses", "info")
    
    def hide_hidden_courses(self):
        self.showing_hidden = False
        self.showing_past = False
        self.display_courses()
        self.show_notification("Hidden courses are now hidden from view", "info")
    
    def view_past_courses(self):
        self.showing_past = True
        self.display_past_courses()
        self.show_notification("Showing past courses with saved data", "info")
    
    def display_all_courses(self):

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if not self.courses:
            no_courses_label = ttk.Label(self.scrollable_frame, 
                                        text="No courses found. Check your Canvas configuration.",
                                        font=("Segoe UI", 12))
            no_courses_label.pack(pady=20)
            return

        columns = 3
        row_counter = 0

        for i, course in enumerate(self.courses):
            if course.id not in self.hidden_courses:
                row = row_counter // columns
                col = row_counter % columns
                self.create_course_card(course, row, col)
                row_counter += 1

        for i, course in enumerate(self.courses):
            if course.id in self.hidden_courses:
                row = row_counter // columns
                col = row_counter % columns
                self.create_hidden_course_card(course, row, col)
                row_counter += 1

        self.root.update_idletasks()
        self.update_scroll_region()
    
    def display_past_courses(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        course_notes_dir = self.data_dir / "course_notes"
        if not course_notes_dir.exists():
            no_courses_label = ttk.Label(self.scrollable_frame, 
                                        text="No past course data found.",
                                        font=("Segoe UI", 12))
            no_courses_label.pack(pady=20)
            return
        
        current_course_names = set()
        if self.courses:
            for course in self.courses:
                safe_name = "".join(c for c in course.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                current_course_names.add(safe_name)
        
        past_course_dirs = []
        for course_dir in course_notes_dir.iterdir():
            if course_dir.is_dir() and course_dir.name not in current_course_names:
                txt_files = list(course_dir.glob("*.txt"))
                if txt_files:
                    past_course_dirs.append(course_dir)
        
        if not past_course_dirs:
            no_courses_label = ttk.Label(self.scrollable_frame, 
                                        text="No past courses with saved data found.",
                                        font=("Segoe UI", 12))
            no_courses_label.pack(pady=20)
            return
        
        columns = 3
        for i, course_dir in enumerate(sorted(past_course_dirs)):
            row = i // columns
            col = i % columns
            self.create_past_course_card(course_dir.name, row, col)
        
        self.root.update_idletasks()
        self.update_scroll_region()
    
    def create_hidden_course_card(self, course: Course, row: int, col: int):

        card_frame = tk.Frame(self.scrollable_frame, bg="#1a1f26", 
                             relief='solid', bd=1, padx=20, pady=15)
        card_frame.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")

        self.scrollable_frame.grid_columnconfigure(col, weight=1)

        controls_frame = tk.Frame(card_frame, bg="#1a1f26")
        controls_frame.pack(fill=tk.X, pady=(0, 8))

        hidden_indicator = tk.Label(controls_frame, text="👁️‍🗨️", fg=self.secondary_color, 
                                   bg="#1a1f26", font=("Segoe UI", 10))
        hidden_indicator.pack(side=tk.LEFT)

        unhide_btn = tk.Label(controls_frame, text="↶", fg=self.secondary_color, 
                             bg="#1a1f26", font=("Segoe UI", 14, "bold"), 
                             cursor="hand2")
        unhide_btn.pack(side=tk.RIGHT)
        unhide_btn.bind("<Button-1>", lambda e: self.unhide_course(course))

        course_name = course.name.replace(course.course_code, "").strip()
        if not course_name:
            course_name = course.name
        
        name_label = tk.Label(card_frame, text=f"{course_name} (Hidden)", 
                             fg="#5a6670", bg="#1a1f26",
                             font=("Segoe UI", 16, "bold"), anchor="w")
        name_label.pack(fill=tk.X, pady=(0, 8))

        if course.course_code:
            code_label = tk.Label(card_frame, text=course.course_code, 
                                 fg="#4a5560", bg="#1a1f26",
                                 font=("Segoe UI", 12), anchor="w")
            code_label.pack(fill=tk.X, pady=(0, 5))

        if course.term:
            term_label = tk.Label(card_frame, text=f"Term: {course.term}", 
                                 fg="#4a5560", bg="#1a1f26",
                                 font=("Segoe UI", 10), anchor="w")
            term_label.pack(fill=tk.X, pady=(0, 10))
    
    def create_past_course_card(self, course_name: str, row: int, col: int):
        card_frame = tk.Frame(self.scrollable_frame, bg="#2d1b3d", 
                             relief='solid', bd=1, padx=20, pady=15)
        card_frame.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        
        self.scrollable_frame.grid_columnconfigure(col, weight=1)
        
        controls_frame = tk.Frame(card_frame, bg="#2d1b3d")
        controls_frame.pack(fill=tk.X, pady=(0, 8))
        
        past_indicator = tk.Label(controls_frame, text="📚", fg=self.secondary_color, 
                                 bg="#2d1b3d", font=("Segoe UI", 10))
        past_indicator.pack(side=tk.LEFT)
        
        course_notes_dir = self.data_dir / "course_notes" / course_name
        txt_files = list(course_notes_dir.glob("*.txt")) if course_notes_dir.exists() else []
        file_count = len(txt_files)
        
        file_count_label = tk.Label(controls_frame, text=f"{file_count} notes", 
                                   fg=self.secondary_color, bg="#2d1b3d", 
                                   font=("Segoe UI", 9))
        file_count_label.pack(side=tk.RIGHT)
        
        name_label = tk.Label(card_frame, text=f"{course_name} (Past Course)", 
                             fg="#b19cd9", bg="#2d1b3d",
                             font=("Segoe UI", 16, "bold"), anchor="w")
        name_label.pack(fill=tk.X, pady=(0, 8))
        
        status_label = tk.Label(card_frame, text="Course no longer active", 
                               fg="#8a7ca8", bg="#2d1b3d",
                               font=("Segoe UI", 10, "italic"), anchor="w")
        status_label.pack(fill=tk.X, pady=(0, 10))
        
        def on_past_card_click(event):
            self.open_past_course_details(course_name)
        
        clickable_widgets = [card_frame, name_label, status_label]
        for widget in clickable_widgets:
            widget.bind("<Button-1>", on_past_card_click)
    
    def unhide_course(self, course: Course):
        
        if course.id in self.hidden_courses:
            self.hidden_courses.remove(course.id)
            self.save_hidden_courses()
            if hasattr(self, 'showing_hidden') and self.showing_hidden:
                self.display_all_courses()
            else:
                self.display_courses()
            self.show_notification(f"Course '{course.name}' has been unhidden", "success")
    
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
    
    def open_course_details(self, course: Course):

        self.current_course = course

        self.course_notes_dir = self.data_dir / "course_notes"
        self.course_notes_dir.mkdir(exist_ok=True)

        safe_course_name = "".join(c for c in course.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        self.current_course_dir = self.course_notes_dir / safe_course_name
        self.current_course_dir.mkdir(exist_ok=True)

        self.show_course_editor(course)
    
    def open_past_course_details(self, course_name: str):

        past_course = Course(
            id=0,
            name=course_name,
            course_code="",
            workflow_state="completed",
            term="Past Course"
        )
        
        self.current_course = past_course
        self.course_notes_dir = self.data_dir / "course_notes"
        self.current_course_dir = self.course_notes_dir / course_name
        
        self.show_past_course_editor(past_course)
    
    def show_course_editor(self, course: Course):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
        main_frame.configure(style='TFrame')
        
        header_frame = tk.Frame(main_frame, bg=self.bg_color, height=80)
        header_frame.pack(fill=tk.X, pady=(0, 25))
        header_frame.pack_propagate(False)

        back_btn = tk.Button(header_frame, text="← Back to Courses", 
                            command=self.return_to_courses,
                            bg=self.accent_color, fg="white",
                            font=("Segoe UI", 11, "bold"),
                            bd=0, padx=20, pady=8,
                            cursor="hand2")
        back_btn.pack(side=tk.LEFT, pady=15)

        title_label = tk.Label(header_frame, text=course.name, 
                              font=("Segoe UI", 24, "bold"),
                              fg=self.text_color, bg=self.bg_color)
        title_label.pack(side=tk.LEFT, padx=(30, 0), pady=15)

        info_text = f"{course.course_code}"
        if course.term:
            info_text += f" • {course.term}"
        info_label = tk.Label(header_frame, text=info_text, 
                             font=("Segoe UI", 13), fg=self.accent_color, bg=self.bg_color)
        info_label.pack(side=tk.LEFT, padx=(20, 0), pady=15)

        content_frame = tk.Frame(main_frame, bg=self.bg_color)
        content_frame.pack(fill=tk.BOTH, expand=True)

        file_frame = tk.Frame(content_frame, bg=self.card_color, relief="solid", bd=1, padx=20, pady=20)
        file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 15))
        file_frame.configure(width=380)

        file_header = tk.Label(file_frame, text="📁 Course Notes", 
                              font=("Segoe UI", 16, "bold"),
                              fg=self.text_color, bg=self.card_color)
        file_header.pack(anchor="w", pady=(0, 20))

        file_buttons_frame = tk.Frame(file_frame, bg=self.card_color)
        file_buttons_frame.pack(fill=tk.X, pady=(0, 20))

        new_btn = tk.Button(file_buttons_frame, text="✚ New Note", 
                           command=lambda: self.create_new_note(course),
                           bg=self.success_color, fg="white",
                           font=("Segoe UI", 10, "bold"),
                           bd=0, padx=15, pady=6, cursor="hand2")
        new_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        delete_btn = tk.Button(file_buttons_frame, text="🗑 Delete", 
                              command=self.delete_selected_note,
                              bg=self.error_color, fg="white",
                              font=("Segoe UI", 10, "bold"),
                              bd=0, padx=15, pady=6, cursor="hand2")
        delete_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        refresh_btn = tk.Button(file_buttons_frame, text="🔄 Refresh", 
                               command=self.refresh_file_list,
                               bg=self.secondary_color, fg="white",
                               font=("Segoe UI", 10, "bold"),
                               bd=0, padx=15, pady=6, cursor="hand2")
        refresh_btn.pack(side=tk.LEFT)

        list_frame = tk.Frame(file_frame, bg=self.card_color)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_listbox = tk.Listbox(list_frame, font=("Segoe UI", 12), 
                                      bg="#2a3441", fg=self.text_color,
                                      selectbackground=self.accent_color,
                                      selectforeground="white",
                                      bd=0, highlightthickness=1,
                                      highlightcolor=self.accent_color,
                                      activestyle="none")
        file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=file_scrollbar.set)
        
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        editor_frame = tk.Frame(content_frame, bg=self.card_color, relief="solid", bd=1, padx=25, pady=20)
        editor_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(15, 0))

        editor_header_frame = tk.Frame(editor_frame, bg=self.card_color)
        editor_header_frame.pack(fill=tk.X, pady=(0, 20))
        
        editor_title = tk.Label(editor_header_frame, text="📝 Note Editor", 
                               font=("Segoe UI", 16, "bold"),
                               fg=self.text_color, bg=self.card_color)
        editor_title.pack(side=tk.LEFT)

        self.current_file_label = tk.Label(editor_header_frame, text="No file selected", 
                                          font=("Segoe UI", 11, "italic"),
                                          fg=self.secondary_color, bg=self.card_color)
        self.current_file_label.pack(side=tk.LEFT, padx=(20, 0))

        save_frame = tk.Frame(editor_header_frame, bg=self.card_color)
        save_frame.pack(side=tk.RIGHT)
        
        save_btn = tk.Button(save_frame, text="💾 Save", 
                            command=self.save_current_note,
                            bg=self.accent_color, fg="white",
                            font=("Segoe UI", 10, "bold"),
                            bd=0, padx=15, pady=6, cursor="hand2")
        save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        save_as_btn = tk.Button(save_frame, text="💾 Save As...", 
                               command=self.save_note_as,
                               bg=self.secondary_color, fg="white",
                               font=("Segoe UI", 10, "bold"),
                               bd=0, padx=15, pady=6, cursor="hand2")
        save_as_btn.pack(side=tk.LEFT)

        editor_container = tk.Frame(editor_frame, bg=self.card_color)
        editor_container.pack(fill=tk.BOTH, expand=True)
        
        self.text_editor = tk.Text(editor_container, font=("Fira Code", 12), 
                                  wrap=tk.WORD, undo=True, maxundo=50,
                                  bg="#1a2028", fg=self.text_color,
                                  selectbackground=self.accent_color,
                                  selectforeground="white",
                                  insertbackground="#ffffff",
                                  bd=0, padx=15, pady=15,
                                  spacing1=2, spacing2=1, spacing3=2)
        editor_scrollbar = ttk.Scrollbar(editor_container, orient=tk.VERTICAL, command=self.text_editor.yview)
        self.text_editor.configure(yscrollcommand=editor_scrollbar.set)
        
        self.text_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        editor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.configure_text_editor_tags()

        self.current_file_path = None
        self.refresh_file_list()

        self.create_notification_area()
    
    def show_past_course_editor(self, course: Course):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
        main_frame.configure(style='TFrame')
        
        header_frame = tk.Frame(main_frame, bg=self.bg_color, height=80)
        header_frame.pack(fill=tk.X, pady=(0, 25))
        header_frame.pack_propagate(False)

        back_btn = tk.Button(header_frame, text="← Back to Courses", 
                            command=self.return_to_courses,
                            bg=self.accent_color, fg="white",
                            font=("Segoe UI", 11, "bold"),
                            bd=0, padx=20, pady=8,
                            cursor="hand2")
        back_btn.pack(side=tk.LEFT, pady=15)

        title_label = tk.Label(header_frame, text=f"{course.name} 📚", 
                              font=("Segoe UI", 24, "bold"),
                              fg=self.text_color, bg=self.bg_color)
        title_label.pack(side=tk.LEFT, padx=(30, 0), pady=15)

        info_label = tk.Label(header_frame, text="Past Course • Read-Only Mode", 
                             font=("Segoe UI", 13), fg="#b19cd9", bg=self.bg_color)
        info_label.pack(side=tk.LEFT, padx=(20, 0), pady=15)

        content_frame = tk.Frame(main_frame, bg=self.bg_color)
        content_frame.pack(fill=tk.BOTH, expand=True)

        file_frame = tk.Frame(content_frame, bg="#2d1b3d", relief="solid", bd=1, padx=20, pady=20)
        file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 15))
        file_frame.configure(width=380)

        file_header = tk.Label(file_frame, text="📁 Course Notes (Past)", 
                              font=("Segoe UI", 16, "bold"),
                              fg="#b19cd9", bg="#2d1b3d")
        file_header.pack(anchor="w", pady=(0, 20))

        file_buttons_frame = tk.Frame(file_frame, bg="#2d1b3d")
        file_buttons_frame.pack(fill=tk.X, pady=(0, 20))

        new_btn = tk.Button(file_buttons_frame, text="✚ New Note", 
                           command=lambda: self.create_new_note(course),
                           bg=self.success_color, fg="white",
                           font=("Segoe UI", 10, "bold"),
                           bd=0, padx=15, pady=6, cursor="hand2")
        new_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        delete_btn = tk.Button(file_buttons_frame, text="🗑 Delete", 
                              command=self.delete_selected_note,
                              bg=self.error_color, fg="white",
                              font=("Segoe UI", 10, "bold"),
                              bd=0, padx=15, pady=6, cursor="hand2")
        delete_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        refresh_btn = tk.Button(file_buttons_frame, text="🔄 Refresh", 
                               command=self.refresh_file_list,
                               bg=self.secondary_color, fg="white",
                               font=("Segoe UI", 10, "bold"),
                               bd=0, padx=15, pady=6, cursor="hand2")
        refresh_btn.pack(side=tk.LEFT)

        list_frame = tk.Frame(file_frame, bg="#2d1b3d")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_listbox = tk.Listbox(list_frame, font=("Segoe UI", 12), 
                                      bg="#1a0f26", fg="#b19cd9",
                                      selectbackground="#4a2d5d",
                                      selectforeground="white",
                                      bd=0, highlightthickness=1,
                                      highlightcolor="#b19cd9",
                                      activestyle="none")
        file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=file_scrollbar.set)
        
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        editor_frame = tk.Frame(content_frame, bg=self.card_color, relief="solid", bd=1, padx=25, pady=20)
        editor_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(15, 0))

        editor_header_frame = tk.Frame(editor_frame, bg=self.card_color)
        editor_header_frame.pack(fill=tk.X, pady=(0, 20))
        
        editor_title = tk.Label(editor_header_frame, text="📝 Note Viewer/Editor", 
                               font=("Segoe UI", 16, "bold"),
                               fg=self.text_color, bg=self.card_color)
        editor_title.pack(side=tk.LEFT)

        self.current_file_label = tk.Label(editor_header_frame, text="No file selected", 
                                          font=("Segoe UI", 11, "italic"),
                                          fg=self.secondary_color, bg=self.card_color)
        self.current_file_label.pack(side=tk.LEFT, padx=(20, 0))

        save_frame = tk.Frame(editor_header_frame, bg=self.card_color)
        save_frame.pack(side=tk.RIGHT)
        
        save_btn = tk.Button(save_frame, text="💾 Save", 
                            command=self.save_current_note,
                            bg=self.accent_color, fg="white",
                            font=("Segoe UI", 10, "bold"),
                            bd=0, padx=15, pady=6, cursor="hand2")
        save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        save_as_btn = tk.Button(save_frame, text="💾 Save As...", 
                               command=self.save_note_as,
                               bg=self.secondary_color, fg="white",
                               font=("Segoe UI", 10, "bold"),
                               bd=0, padx=15, pady=6, cursor="hand2")
        save_as_btn.pack(side=tk.LEFT)

        editor_container = tk.Frame(editor_frame, bg=self.card_color)
        editor_container.pack(fill=tk.BOTH, expand=True)
        
        self.text_editor = tk.Text(editor_container, font=("Fira Code", 12), 
                                  wrap=tk.WORD, undo=True, maxundo=50,
                                  bg="#1a2028", fg=self.text_color,
                                  selectbackground=self.accent_color,
                                  selectforeground="white",
                                  insertbackground="#ffffff",
                                  bd=0, padx=15, pady=15,
                                  spacing1=2, spacing2=1, spacing3=2)
        editor_scrollbar = ttk.Scrollbar(editor_container, orient=tk.VERTICAL, command=self.text_editor.yview)
        self.text_editor.configure(yscrollcommand=editor_scrollbar.set)
        
        self.text_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        editor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.configure_text_editor_tags()

        self.current_file_path = None
        self.refresh_file_list()

        self.create_notification_area()
    
    def configure_text_editor_tags(self):
        
        if hasattr(self, 'text_editor'):

            self.text_editor.tag_configure("header1", font=("Fira Code", 16, "bold"), foreground=self.accent_color)
            self.text_editor.tag_configure("header2", font=("Fira Code", 14, "bold"), foreground="#6bb6ff")
            self.text_editor.tag_configure("header3", font=("Fira Code", 12, "bold"), foreground="#89c4ff")

            self.text_editor.tag_configure("code", font=("Fira Code", 11), 
                                          background="#151b23", foreground="#a7d2ff")

            self.text_editor.tag_configure("bold", font=("Fira Code", 12, "bold"))
            self.text_editor.tag_configure("italic", font=("Fira Code", 12, "italic"))

            self.text_editor.tag_configure("link", foreground=self.accent_color, underline=True)
            self.text_editor.tag_configure("comment", foreground=self.secondary_color, font=("Fira Code", 12, "italic"))
    
    def return_to_courses(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.setup_styles()
        self.create_widgets()
        self.display_courses()
        self.update_status_label()
    
    def create_new_note(self, course):
        self.show_input_panel("Create New Note", "Enter note filename (without .txt):", 
                              lambda filename: self.handle_new_note_creation(course, filename))
    
    def handle_new_note_creation(self, course, filename):
        if filename:
            if not filename.endswith('.txt'):
                filename += '.txt'
            
            file_path = self.current_course_dir / filename

            if not file_path.exists():
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {course.name} - {filename}\n\n")
            
            self.refresh_file_list()

            for i, item in enumerate(self.file_listbox.get(0, tk.END)):
                if item == filename:
                    self.file_listbox.selection_clear(0, tk.END)
                    self.file_listbox.selection_set(i)
                    self.on_file_select(None)
                    break
    
    def refresh_file_list(self):
        
        self.file_listbox.delete(0, tk.END)
        
        if hasattr(self, 'current_course_dir') and self.current_course_dir.exists():
            txt_files = list(self.current_course_dir.glob("*.txt"))
            for file_path in sorted(txt_files):
                self.file_listbox.insert(tk.END, file_path.name)
    
    def on_file_select(self, event):
        
        selection = self.file_listbox.curselection()
        if selection:
            filename = self.file_listbox.get(selection[0])
            file_path = self.current_course_dir / filename
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                self.text_editor.delete(1.0, tk.END)
                self.text_editor.insert(1.0, content)

                self.current_file_path = file_path
                self.current_file_label.configure(text=f"Editing: {filename}")

                self.text_editor.edit_modified(False)
                
            except Exception as e:
                self.show_notification(f"Failed to open file: {str(e)}", "error")
    
    def save_current_note(self):
        
        if not self.current_file_path:
            self.save_note_as()
            return
        
        try:
            content = self.text_editor.get(1.0, tk.END)
            with open(self.current_file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            self.text_editor.edit_modified(False)
            self.show_notification(f"Note saved to {self.current_file_path.name}", "success")
            
        except Exception as e:
            self.show_notification(f"Failed to save file: {str(e)}", "error")
    
    def save_note_as(self):
        
        if not hasattr(self, 'current_course_dir'):
            return
            
        self.show_input_panel("Save Note As", "Enter filename (without .txt):", 
                              self.handle_save_note_as)
    
    def handle_save_note_as(self, filename):
        if filename:
            if not filename.endswith('.txt'):
                filename += '.txt'
            
            file_path = self.current_course_dir / filename
            
            try:
                content = self.text_editor.get(1.0, tk.END)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.current_file_path = file_path
                self.current_file_label.configure(text=f"Editing: {filename}")
                self.text_editor.edit_modified(False)
                
                self.refresh_file_list()
                self.show_notification(f"Note saved as {filename}", "success")
                
            except Exception as e:
                self.show_notification(f"Failed to save file: {str(e)}", "error")
    
    def delete_selected_note(self):
        
        selection = self.file_listbox.curselection()
        if not selection:
            self.show_notification("Please select a file to delete", "warning")
            return
        
        filename = self.file_listbox.get(selection[0])
        file_path = self.current_course_dir / filename

        self.show_confirmation_dialog(
            f"Are you sure you want to delete '{filename}'?",
            lambda: self.confirm_delete_file(file_path, filename)
        )
    
    def confirm_delete_file(self, file_path, filename):
        
        try:
            file_path.unlink()

            if self.current_file_path == file_path:
                self.text_editor.delete(1.0, tk.END)
                self.current_file_path = None
                self.current_file_label.configure(text="No file selected")
            
            self.refresh_file_list()
            self.show_notification(f"File '{filename}' has been deleted", "success")
            
        except Exception as e:
            self.show_notification(f"Failed to delete file: {str(e)}", "error")
    
    def show_confirmation_dialog(self, message: str, confirm_callback):

        self.show_confirmation_panel(message, confirm_callback)
    
    def configure_api(self):

        for widget in self.root.winfo_children():
            widget.destroy()
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 30))
        
        back_btn = tk.Button(header_frame, text="← Back to Dashboard", 
                            command=self.return_to_dashboard,
                            bg=self.accent_color, fg="white",
                            font=("Segoe UI", 11, "bold"),
                            bd=0, padx=20, pady=8,
                            cursor="hand2")
        back_btn.pack(side=tk.LEFT)
        
        title_label = ttk.Label(header_frame, text="Canvas API Configuration", 
                               font=("Segoe UI", 24, "bold"))
        title_label.pack(side=tk.LEFT, padx=(30, 0))
        
        config_card = tk.Frame(main_frame, bg=self.card_color, 
                              relief='solid', bd=1, padx=40, pady=30)
        config_card.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        
        instruction_label = tk.Label(config_card, 
                                    text="Configure your Canvas API credentials to access your courses",
                                    fg=self.text_color, bg=self.card_color,
                                    font=("Segoe UI", 14), anchor="w")
        instruction_label.pack(fill=tk.X, pady=(0, 10))
        
        help_label = tk.Label(config_card, 
                             text="Get your API token from Canvas Account Settings > Approved Integrations",
                             fg=self.secondary_color, bg=self.card_color,
                             font=("Segoe UI", 11), anchor="w", wraplength=600)
        help_label.pack(fill=tk.X, pady=(0, 30))
        
        url_section = tk.Frame(config_card, bg=self.card_color)
        url_section.pack(fill=tk.X, pady=(0, 20))
        
        url_label = tk.Label(url_section, text="Canvas Base URL:", 
                           fg=self.text_color, bg=self.card_color,
                           font=("Segoe UI", 12, "bold"), anchor="w")
        url_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.url_var = tk.StringVar()

        if hasattr(self, 'canvas_api') and self.canvas_api:
            self.url_var.set(self.canvas_api.base_url)
        else:
            self.url_var.set("https://canvas.instructure.com")
            
        url_entry = tk.Entry(url_section, textvariable=self.url_var, 
                           font=("Segoe UI", 11), bg="#2a3441", fg=self.text_color,
                           insertbackground=self.text_color, bd=0, 
                           highlightthickness=2, highlightcolor=self.accent_color,
                           relief="solid", highlightbackground="#3a4451")
        url_entry.pack(fill=tk.X, ipady=10, pady=(0, 5))
        
        url_help = tk.Label(url_section, text="Example: https://yourschool.instructure.com", 
                          fg=self.secondary_color, bg=self.card_color,
                          font=("Segoe UI", 9), anchor="w")
        url_help.pack(anchor=tk.W)
        

        token_section = tk.Frame(config_card, bg=self.card_color)
        token_section.pack(fill=tk.X, pady=(20, 30))
        
        token_label = tk.Label(token_section, text="API Token:", 
                             fg=self.text_color, bg=self.card_color,
                             font=("Segoe UI", 12, "bold"), anchor="w")
        token_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.token_var = tk.StringVar()
        token_entry = tk.Entry(token_section, textvariable=self.token_var, 
                             font=("Segoe UI", 11), bg="#2a3441", fg=self.text_color,
                             insertbackground=self.text_color, bd=0, show="*",
                             highlightthickness=2, highlightcolor=self.accent_color,
                             relief="solid", highlightbackground="#3a4451")
        token_entry.pack(fill=tk.X, ipady=10, pady=(0, 5))
        
        token_help = tk.Label(token_section, text="Your personal Canvas API access token", 
                            fg=self.secondary_color, bg=self.card_color,
                            font=("Segoe UI", 9), anchor="w")
        token_help.pack(anchor=tk.W)
        
        button_section = tk.Frame(config_card, bg=self.card_color)
        button_section.pack(fill=tk.X, pady=(10, 0))
        
        test_btn = tk.Button(button_section, text="🔍 Test Connection", 
                           command=self.test_api_connection,
                           bg=self.secondary_color, fg="white",
                           font=("Segoe UI", 11, "bold"),
                           bd=0, padx=20, pady=10, cursor="hand2")
        test_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        save_btn = tk.Button(button_section, text="💾 Save & Apply", 
                           command=self.save_api_config,
                           bg=self.success_color, fg="white",
                           font=("Segoe UI", 11, "bold"),
                           bd=0, padx=20, pady=10, cursor="hand2")
        save_btn.pack(side=tk.LEFT)
        
        self.config_status_label = tk.Label(config_card, text="", 
                                          fg=self.secondary_color, bg=self.card_color,
                                          font=("Segoe UI", 10), anchor="w")
        self.config_status_label.pack(fill=tk.X, pady=(20, 0))
        
        self.create_notification_area()
    
    def test_api_connection(self):
        url = self.url_var.get().strip()
        token = self.token_var.get().strip()
        
        if not url or not token:
            self.show_notification("Please enter both URL and token", "warning")
            return
        
        self.config_status_label.configure(text="Testing connection...", fg=self.warning_color)
        self.root.update()
        
        try:
            test_api = CanvasAPI(url, token)
            test_courses = test_api.get_courses()
            
            course_count = len(test_courses) if test_courses else 0
            self.config_status_label.configure(
                text=f"✅ Connection successful! Found {course_count} courses.",
                fg=self.success_color
            )
            self.show_notification("API connection test successful!", "success")
        except Exception as e:
            self.config_status_label.configure(
                text=f"❌ Connection failed: {str(e)}",
                fg=self.error_color
            )
            self.show_notification(f"Connection test failed: {str(e)}", "error")
    
    def save_api_config(self):
        url = self.url_var.get().strip()
        token = self.token_var.get().strip()
        
        if not url or not token:
            self.show_notification("Please enter both URL and token", "warning")
            return
        
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
            
            self.show_notification("Canvas API configured successfully!", "success")
            
            self.root.after(1500, self.return_to_dashboard_and_refresh)
            
        except Exception as e:
            self.show_notification(f"Failed to save configuration: {str(e)}", "error")
    
    def return_to_dashboard(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.setup_styles()
        self.create_widgets()
        self.display_courses()
        self.update_status_label()
    
    def return_to_dashboard_and_refresh(self):
        self.return_to_dashboard()
        if self.canvas_api:
            self.refresh_courses()
    
    def show_input_panel(self, title, prompt, callback):
        if not hasattr(self, '_panel_restore_state'):
            self._panel_restore_state = []
        
        main_content = None
        for widget in self.root.winfo_children():
            if widget.winfo_class() != 'Toplevel':
                widget.pack_forget()
                main_content = widget
                break
        
        self._panel_restore_state.append(main_content)
        
        panel_frame = tk.Frame(self.root, bg=self.bg_color)
        panel_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        header_frame = tk.Frame(panel_frame, bg=self.bg_color)
        header_frame.pack(fill=tk.X, pady=(0, 30))
        
        title_label = tk.Label(header_frame, text=title, 
                              font=("Segoe UI", 24, "bold"),
                              fg=self.text_color, bg=self.bg_color)
        title_label.pack()
        
        input_card = tk.Frame(panel_frame, bg=self.card_color, 
                             relief='solid', bd=1, padx=40, pady=30)
        input_card.pack(expand=True, pady=20)
        
        prompt_label = tk.Label(input_card, text=prompt, 
                               fg=self.text_color, bg=self.card_color,
                               font=("Segoe UI", 14), anchor="w")
        prompt_label.pack(fill=tk.X, pady=(0, 20))
        
        input_var = tk.StringVar()
        input_entry = tk.Entry(input_card, textvariable=input_var, 
                              font=("Segoe UI", 12), bg="#2a3441", fg=self.text_color,
                              insertbackground=self.text_color, bd=0, 
                              highlightthickness=2, highlightcolor=self.accent_color,
                              relief="solid", highlightbackground="#3a4451")
        input_entry.pack(fill=tk.X, ipady=12, pady=(0, 30))
        input_entry.focus_set()
        
        button_frame = tk.Frame(input_card, bg=self.card_color)
        button_frame.pack(fill=tk.X)
        
        def on_confirm():
            value = input_var.get().strip()
            self.hide_input_panel(panel_frame)
            if value:
                callback(value)
        
        def on_cancel():
            self.hide_input_panel(panel_frame)
        
        confirm_btn = tk.Button(button_frame, text="✓ Confirm", 
                               command=on_confirm,
                               bg=self.success_color, fg="white",
                               font=("Segoe UI", 11, "bold"),
                               bd=0, padx=20, pady=10, cursor="hand2")
        confirm_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        cancel_btn = tk.Button(button_frame, text="✗ Cancel", 
                              command=on_cancel,
                              bg=self.secondary_color, fg="white",
                              font=("Segoe UI", 11, "bold"),
                              bd=0, padx=20, pady=10, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT)
        
        input_entry.bind('<Return>', lambda e: on_confirm())
        input_entry.bind('<Escape>', lambda e: on_cancel())
    
    def hide_input_panel(self, panel_frame):
        panel_frame.destroy()
        
        if hasattr(self, '_panel_restore_state') and self._panel_restore_state:
            content = self._panel_restore_state.pop()
            if content and content.winfo_exists():
                content.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
    
    def show_confirmation_panel(self, message, confirm_callback):
        if not hasattr(self, '_panel_restore_state'):
            self._panel_restore_state = []
        
        main_content = None
        for widget in self.root.winfo_children():
            if widget.winfo_class() != 'Toplevel':
                widget.pack_forget()
                main_content = widget
                break
        
        self._panel_restore_state.append(main_content)
        
        panel_frame = tk.Frame(self.root, bg=self.bg_color)
        panel_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        header_frame = tk.Frame(panel_frame, bg=self.bg_color)
        header_frame.pack(fill=tk.X, pady=(0, 30))
        
        title_label = tk.Label(header_frame, text="Confirm Action", 
                              font=("Segoe UI", 24, "bold"),
                              fg=self.text_color, bg=self.bg_color)
        title_label.pack()
        
        confirm_card = tk.Frame(panel_frame, bg=self.card_color, 
                               relief='solid', bd=1, padx=40, pady=30)
        confirm_card.pack(expand=True, pady=20)
        
        message_frame = tk.Frame(confirm_card, bg=self.card_color)
        message_frame.pack(fill=tk.X, pady=(0, 30))
        
        warning_label = tk.Label(message_frame, text="⚠️", 
                                fg=self.warning_color, bg=self.card_color,
                                font=("Segoe UI", 24))
        warning_label.pack(pady=(0, 10))
        
        message_label = tk.Label(message_frame, text=message, 
                                fg=self.text_color, bg=self.card_color,
                                font=("Segoe UI", 14), anchor="center",
                                wraplength=400, justify="center")
        message_label.pack(fill=tk.X)
        
        button_frame = tk.Frame(confirm_card, bg=self.card_color)
        button_frame.pack()
        
        def on_confirm():
            self.hide_confirmation_panel(panel_frame)
            confirm_callback()
        
        def on_cancel():
            self.hide_confirmation_panel(panel_frame)
        
        yes_btn = tk.Button(button_frame, text="✓ Yes", 
                           command=on_confirm,
                           bg=self.error_color, fg="white",
                           font=("Segoe UI", 11, "bold"),
                           bd=0, padx=25, pady=10, cursor="hand2")
        yes_btn.pack(side=tk.LEFT, padx=(0, 20))
        
        cancel_btn = tk.Button(button_frame, text="✗ Cancel", 
                              command=on_cancel,
                              bg=self.secondary_color, fg="white",
                              font=("Segoe UI", 11, "bold"),
                              bd=0, padx=25, pady=10, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT)
    
    def hide_confirmation_panel(self, panel_frame):
        panel_frame.destroy()
        
        if hasattr(self, '_panel_restore_state') and self._panel_restore_state:
            content = self._panel_restore_state.pop()
            if content and content.winfo_exists():
                content.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
    
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

            if self.courses:
                self.root.after(100, self.display_courses)
                
        except Exception as e:
            print(f"Failed to load cached courses: {e}")
    
    def get_cache_info(self):
        
        if not self.data_file.exists():
            return "No cached data"
            
        try:
            with open(self.data_file, 'r') as f:
                cache_data = json.load(f)
                
            last_updated = cache_data.get('last_updated', 'Unknown')
            total_courses = cache_data.get('total_courses', 0)
            
            if last_updated != 'Unknown':
                try:
                    updated_dt = datetime.fromisoformat(last_updated)
                    updated_str = updated_dt.strftime("%Y-%m-%d %H:%M")
                except:
                    updated_str = last_updated
            else:
                updated_str = 'Unknown'
                
            return f"Cached: {total_courses} courses (Updated: {updated_str})"
            
        except Exception as e:
            return f"Cache error: {e}"
    
    def run(self):
        
        self.root.mainloop()
    
    def update_status_label(self):
        
        cache_info = self.get_cache_info()
        self.status_label.configure(text=cache_info)
    
    def on_closing(self):
        try:
            if hasattr(self, '_mousewheel_handler') and hasattr(self, 'canvas'):
                self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        self.root.destroy()

    def check_for_updates_button(self):
        import urllib.request
        import tkinter.messagebox

        version_url = "https://raw.githubusercontent.com/Giraffe801/CanvasNotes/main/version.txt"
        exe_url = "https://github.com/Giraffe801/CanvasNotes/releases/latest/download/canvas_dashboard.exe"

        try:
            with urllib.request.urlopen(version_url, timeout=5) as response:
                latest_version = response.read().decode().strip()
            if latest_version != APP_VERSION:
                answer = tkinter.messagebox.askyesno(
                    "Update Available",
                    f"Version {latest_version} is available. Download and restart to update?"
                )
                if answer:
                    import sys
                    import tempfile
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
            else:
                self.show_notification("You are running the latest version.", "success")
        except Exception as e:
            self.show_notification(f"Update check failed: {e}", "error")


def main():
    app = SimpleDashboardApp()
    app.run()

if __name__ == "__main__":
    main()

