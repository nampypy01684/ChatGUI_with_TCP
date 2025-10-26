import socket
import threading
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from datetime import datetime

class ChatClient:
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 5555
        self.client_socket = None
        self.username = None
        self.connected = False
        self.receive_thread = None
        
    def connect(self, username, callback):
        """Kết nối đến server"""
        try:
            self.username = username
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            
            # Gửi username
            self.client_socket.send(username.encode('utf-8'))
            self.connected = True
            
            # Thread nhận tin nhắn
            self.receive_thread = threading.Thread(
                target=self.receive_messages, 
                args=(callback,),
                daemon=True
            )
            self.receive_thread.start()
            
            return True
        except Exception as e:
            callback(f"[LỖI] Không thể kết nối: {e}\n", "error")
            return False
    
    def receive_messages(self, callback):
        """Nhận tin nhắn từ server"""
        while self.connected:
            try:
                data = self.client_socket.recv(4096).decode('utf-8')
                if data:
                    message_data = json.loads(data)
                    
                    if message_data['type'] == 'history':
                        # Hiển thị lịch sử
                        callback("[LỊCH SỬ] Đang tải lịch sử chat...\n", "system")
                        for entry in message_data['data']:
                            timestamp = entry['timestamp'].split()[1]  # Chỉ lấy giờ
                            msg = f"[{timestamp}] {entry['username']}: {entry['message']}\n"
                            callback(msg, "history")
                        callback("[LỊCH SỬ] Đã tải xong lịch sử chat\n\n", "system")
                        
                    elif message_data['type'] == 'message':
                        # Hiển thị tin nhắn mới
                        sender = message_data['sender']
                        message = message_data['message']
                        timestamp = message_data['timestamp']
                        
                        if sender == "SERVER":
                            msg = f"[{timestamp}] 🔔 {message}\n"
                            callback(msg, "server")
                        elif sender == self.username:
                            msg = f"[{timestamp}] Bạn: {message}\n"
                            callback(msg, "self")
                        else:
                            msg = f"[{timestamp}] {sender}: {message}\n"
                            callback(msg, "other")
                else:
                    break
            except Exception as e:
                if self.connected:
                    callback(f"[LỖI] {e}\n", "error")
                break
        
        self.connected = False
        callback("[DISCONNECT] Đã ngắt kết nối khỏi server\n", "error")
    
    def send_message(self, message):
        """Gửi tin nhắn"""
        try:
            if self.connected and message.strip():
                self.client_socket.send(message.encode('utf-8'))
                return True
        except Exception as e:
            print(f"Lỗi gửi tin nhắn: {e}")
        return False
    
    def disconnect(self):
        """Ngắt kết nối"""
        self.connected = False
        if self.client_socket:
            self.client_socket.close()


class LoginDialog:
    def __init__(self, parent):
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("🚀 Tham gia Chat")
        self.dialog.geometry("400x300")
        self.dialog.configure(bg='#1e1e1e')
        self.dialog.resizable(False, False)
        
        # Center window
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_ui()
        
        # Focus vào entry
        self.username_entry.focus()
        
    def setup_ui(self):
        """Thiết lập giao diện đăng nhập"""
        # Header
        header_frame = tk.Frame(self.dialog, bg='#0d7377', height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        title = tk.Label(
            header_frame,
            text="💬 Chào mừng đến Chat!",
            bg='#0d7377',
            fg='white',
            font=('Segoe UI', 18, 'bold')
        )
        title.pack(expand=True)
        
        # Content
        content_frame = tk.Frame(self.dialog, bg='#1e1e1e')
        content_frame.pack(expand=True, fill='both', padx=30, pady=30)
        
        info_label = tk.Label(
            content_frame,
            text="Vui lòng nhập tên của bạn để bắt đầu:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11)
        )
        info_label.pack(pady=(0, 15))
        
        # Username entry với icon
        entry_frame = tk.Frame(content_frame, bg='#2d2d2d', relief='flat')
        entry_frame.pack(fill='x', pady=10)
        
        icon_label = tk.Label(
            entry_frame,
            text="👤",
            bg='#2d2d2d',
            font=('Segoe UI', 16)
        )
        icon_label.pack(side='left', padx=(10, 5))
        
        self.username_entry = tk.Entry(
            entry_frame,
            font=('Segoe UI', 12),
            bg='#2d2d2d',
            fg='white',
            relief='flat',
            insertbackground='white',
            border=0
        )
        self.username_entry.pack(side='left', fill='both', expand=True, padx=(5, 10), pady=10)
        self.username_entry.bind('<Return>', lambda e: self.submit())
        
        # Buttons
        btn_frame = tk.Frame(content_frame, bg='#1e1e1e')
        btn_frame.pack(pady=20)
        
        join_btn = tk.Button(
            btn_frame,
            text="🚀 Tham gia",
            command=self.submit,
            bg='#32de84',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=30,
            pady=10
        )
        join_btn.pack(side='left', padx=5)
        
        cancel_btn = tk.Button(
            btn_frame,
            text="❌ Hủy",
            command=self.cancel,
            bg='#f45b69',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=30,
            pady=10
        )
        cancel_btn.pack(side='left', padx=5)
        
    def submit(self):
        """Xác nhận tên người dùng"""
        username = self.username_entry.get().strip()
        if username:
            self.result = username
            self.dialog.destroy()
        else:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập tên người dùng!")
    
    def cancel(self):
        """Hủy"""
        self.dialog.destroy()
    
    def show(self):
        """Hiển thị dialog và trả về kết quả"""
        self.dialog.wait_window()
        return self.result


class ClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("💬 TCP Chat Client")
        self.root.geometry("800x700")
        self.root.configure(bg='#1e1e1e')
        
        self.client = ChatClient()
        self.setup_ui()
        
        # Hiển thị dialog đăng nhập
        self.root.after(100, self.show_login)
        
        # Xử lý đóng cửa sổ
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_ui(self):
        """Thiết lập giao diện"""
        # Header
        header_frame = tk.Frame(self.root, bg='#0d7377', height=90)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="💬 Chat Application",
            bg='#0d7377',
            fg='white',
            font=('Segoe UI', 22, 'bold')
        )
        title_label.pack(expand=True)
        
        # Status bar
        self.status_frame = tk.Frame(self.root, bg='#2d2d2d', relief='groove', bd=2)
        self.status_frame.pack(fill='x', padx=10, pady=10)
        
        self.status_label = tk.Label(
            self.status_frame,
            text="⚫ Chưa kết nối",
            bg='#2d2d2d',
            fg='#ff6b6b',
            font=('Segoe UI', 10, 'bold'),
            anchor='w',
            padx=15,
            pady=8
        )
        self.status_label.pack(side='left', fill='x', expand=True)
        
        self.user_label = tk.Label(
            self.status_frame,
            text="👤 Chưa đăng nhập",
            bg='#2d2d2d',
            fg='#ffd43b',
            font=('Segoe UI', 10, 'bold'),
            anchor='e',
            padx=15,
            pady=8
        )
        self.user_label.pack(side='right')
        
        # Chat area
        chat_label = tk.Label(
            self.root,
            text="💭 Tin nhắn:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            anchor='w'
        )
        chat_label.pack(fill='x', padx=20, pady=(5, 5))
        
        chat_frame = tk.Frame(self.root, bg='#2d2d2d', relief='sunken', bd=2)
        chat_frame.pack(fill='both', expand=True, padx=20, pady=(0, 10))
        
        self.chat_text = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg='#0d1117',
            fg='white',
            font=('Segoe UI', 10),
            relief='flat',
            padx=15,
            pady=15,
            state='disabled'
        )
        self.chat_text.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Cấu hình tags cho màu sắc
        self.chat_text.tag_config('self', foreground='#58a6ff')
        self.chat_text.tag_config('other', foreground='#79c0ff')
        self.chat_text.tag_config('server', foreground='#ffd43b')
        self.chat_text.tag_config('system', foreground='#8b949e')
        self.chat_text.tag_config('history', foreground='#6e7681')
        self.chat_text.tag_config('error', foreground='#ff6b6b')
        
        # Input area
        input_frame = tk.Frame(self.root, bg='#1e1e1e')
        input_frame.pack(fill='x', padx=20, pady=(0, 15))
        
        # Entry frame với border
        entry_container = tk.Frame(input_frame, bg='#2d2d2d', relief='flat', bd=2)
        entry_container.pack(side='left', fill='both', expand=True, padx=(0, 10))
        
        self.message_entry = tk.Entry(
            entry_container,
            font=('Segoe UI', 11),
            bg='#0d1117',
            fg='white',
            relief='flat',
            insertbackground='white'
        )
        self.message_entry.pack(fill='both', expand=True, padx=10, pady=8)
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        self.message_entry.config(state='disabled')
        
        # Buttons
        self.send_btn = tk.Button(
            input_frame,
            text="📤 Gửi",
            command=self.send_message,
            bg='#32de84',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=25,
            pady=8,
            state='disabled'
        )
        self.send_btn.pack(side='left', padx=2)
        
        self.disconnect_btn = tk.Button(
            input_frame,
            text="🔌 Ngắt kết nối",
            command=self.disconnect,
            bg='#f45b69',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=15,
            pady=8,
            state='disabled'
        )
        self.disconnect_btn.pack(side='left', padx=2)
        
        # Footer
        footer = tk.Label(
            self.root,
            text="TCP Chat Client v1.0 | Server: 127.0.0.1:5555",
            bg='#1e1e1e',
            fg='#888',
            font=('Segoe UI', 8)
        )
        footer.pack(pady=5)
    
    def show_login(self):
        """Hiển thị dialog đăng nhập"""
        dialog = LoginDialog(self.root)
        username = dialog.show()
        
        if username:
            self.connect(username)
        else:
            self.root.quit()
    
    def connect(self, username):
        """Kết nối đến server"""
        if self.client.connect(username, self.display_message):
            self.user_label.config(text=f"👤 {username}")
            self.status_label.config(
                text="🟢 Đã kết nối",
                fg='#51cf66'
            )
            self.message_entry.config(state='normal')
            self.send_btn.config(state='normal')
            self.disconnect_btn.config(state='normal')
            self.display_message(f"[SYSTEM] Đã kết nối với server!\n", "system")
    
    def display_message(self, message, tag="other"):
        """Hiển thị tin nhắn trong chat"""
        self.chat_text.config(state='normal')
        self.chat_text.insert(tk.END, message, tag)
        self.chat_text.see(tk.END)
        self.chat_text.config(state='disabled')
    
    def send_message(self):
        """Gửi tin nhắn"""
        message = self.message_entry.get().strip()
        if message:
            if self.client.send_message(message):
                self.message_entry.delete(0, tk.END)
            else:
                messagebox.showerror("Lỗi", "Không thể gửi tin nhắn!")
    
    def disconnect(self):
        """Ngắt kết nối"""
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn ngắt kết nối?"):
            self.client.disconnect()
            self.message_entry.config(state='disabled')
            self.send_btn.config(state='disabled')
            self.disconnect_btn.config(state='disabled')
            self.status_label.config(
                text="⚫ Đã ngắt kết nối",
                fg='#ff6b6b'
            )
    
    def on_closing(self):
        """Xử lý khi đóng cửa sổ"""
        if self.client.connected:
            if messagebox.askokcancel("Thoát", "Bạn có chắc muốn thoát?"):
                self.client.disconnect()
                self.root.destroy()
        else:
            self.root.destroy()
    
    def run(self):
        """Chạy GUI"""
        self.root.mainloop()


if __name__ == "__main__":
    app = ClientGUI()
    app.run()