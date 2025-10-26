
import socket
import threading
import json
import os
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path

class ChatServer:
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 5555
        self.server_socket = None
        self.clients = {}  # {socket: username}
        self.running = False
        self.history_file = 'chat_history.json'
        self.chat_history = self.load_history()
        
    def load_history(self):
        """Tải lịch sử chat từ file"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_history(self):
        """Lưu lịch sử chat vào file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.chat_history[-1000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Lỗi khi lưu lịch sử: {e}")
    
    def add_to_history(self, username, message):
        """Thêm tin nhắn vào lịch sử"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            'timestamp': timestamp,
            'username': username,
            'message': message
        }
        self.chat_history.append(entry)
        self.save_history()
    
    def start_server(self, callback):
        """Khởi động server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            callback(f"[SERVER] Đang chạy trên {self.host}:{self.port}\n")
            
            # Thread để chấp nhận kết nối
            accept_thread = threading.Thread(target=self.accept_connections, args=(callback,), daemon=True)
            accept_thread.start()
            
            return True
        except Exception as e:
            callback(f"[LỖI] Không thể khởi động server: {e}\n")
            return False
    
    def accept_connections(self, callback):
        """Chấp nhận kết nối từ client"""
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                callback(f"[CONNECT] Kết nối mới từ {address}\n")
                
                # Thread xử lý client
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, address, callback),
                    daemon=True
                )
                client_thread.start()
            except:
                break
    
    def handle_client(self, client_socket, address, callback):
        """Xử lý client"""
        username = None
        try:
            # Nhận tên người dùng
            username = client_socket.recv(1024).decode('utf-8')
            self.clients[client_socket] = username
            
            # Gửi lịch sử chat cho client mới
            history_msg = json.dumps({
                'type': 'history',
                'data': self.chat_history[-50:]  # 50 tin nhắn gần nhất
            })
            client_socket.send(history_msg.encode('utf-8'))
            
            # Thông báo user join
            join_msg = f"{username} đã tham gia chat!"
            callback(f"[JOIN] {username} từ {address}\n")
            self.broadcast(join_msg, "SERVER")
            self.add_to_history("SERVER", join_msg)
            
            # Nhận và broadcast tin nhắn
            while self.running:
                message = client_socket.recv(1024).decode('utf-8')
                if message:
                    callback(f"[{username}] {message}\n")
                    self.broadcast(message, username)
                    self.add_to_history(username, message)
                else:
                    break
                    
        except Exception as e:
            callback(f"[LỖI] {address}: {e}\n")
        finally:
            if client_socket in self.clients:
                username = self.clients[client_socket]
                del self.clients[client_socket]
                
                # Thông báo user leave
                leave_msg = f"{username} đã rời khỏi chat!"
                callback(f"[LEAVE] {username}\n")
                self.broadcast(leave_msg, "SERVER")
                self.add_to_history("SERVER", leave_msg)
                
            client_socket.close()
    
    def broadcast(self, message, sender):
        """Gửi tin nhắn đến tất cả client"""
        data = json.dumps({
            'type': 'message',
            'sender': sender,
            'message': message,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        })
        
        disconnected = []
        for client_socket in self.clients:
            try:
                client_socket.send(data.encode('utf-8'))
            except:
                disconnected.append(client_socket)
        
        # Xóa client bị disconnect
        for client_socket in disconnected:
            if client_socket in self.clients:
                del self.clients[client_socket]
    
    def stop_server(self):
        """Dừng server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        for client_socket in list(self.clients.keys()):
            client_socket.close()
        self.clients.clear()


class ServerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🖥️ TCP Chat Server")
        self.root.geometry("700x600")
        self.root.configure(bg='#1e1e1e')
        
        self.server = ChatServer()
        self.setup_ui()
        
        # Xử lý đóng cửa sổ
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """Thiết lập giao diện"""
        # Style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Segoe UI', 10), padding=10)
        style.configure('TLabel', background='#1e1e1e', foreground='white', font=('Segoe UI', 10))
        
        # Header
        header_frame = tk.Frame(self.root, bg='#0d7377', height=80)
        header_frame.pack(fill='x', pady=(0, 10))
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame, 
            text="🖥️ Chat Server Dashboard", 
            bg='#0d7377', 
            fg='white',
            font=('Segoe UI', 20, 'bold')
        )
        title_label.pack(expand=True)
        
        # Control Panel
        control_frame = tk.Frame(self.root, bg='#1e1e1e')
        control_frame.pack(pady=10)
        
        self.start_btn = tk.Button(
            control_frame,
            text="▶ Khởi động Server",
            command=self.start_server,
            bg='#32de84',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=20,
            pady=10
        )
        self.start_btn.pack(side='left', padx=5)
        
        self.stop_btn = tk.Button(
            control_frame,
            text="⬛ Dừng Server",
            command=self.stop_server,
            bg='#f45b69',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=20,
            pady=10,
            state='disabled'
        )
        self.stop_btn.pack(side='left', padx=5)
        
        self.clear_btn = tk.Button(
            control_frame,
            text="🗑️ Xóa Logs",
            command=self.clear_logs,
            bg='#456990',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=20,
            pady=10
        )
        self.clear_btn.pack(side='left', padx=5)
        
        # Status
        status_frame = tk.Frame(self.root, bg='#2d2d2d', relief='groove', bd=2)
        status_frame.pack(fill='x', padx=20, pady=5)
        
        self.status_label = tk.Label(
            status_frame,
            text="⚫ Trạng thái: Chưa khởi động",
            bg='#2d2d2d',
            fg='#ff6b6b',
            font=('Segoe UI', 10, 'bold'),
            anchor='w',
            padx=10,
            pady=8
        )
        self.status_label.pack(fill='x')
        
        # Logs
        log_label = tk.Label(
            self.root,
            text="📋 Server Logs:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            anchor='w'
        )
        log_label.pack(fill='x', padx=20, pady=(10, 5))
        
        log_frame = tk.Frame(self.root, bg='#2d2d2d', relief='sunken', bd=2)
        log_frame.pack(fill='both', expand=True, padx=20, pady=(0, 20))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            bg='#0d1117',
            fg='#58a6ff',
            font=('Consolas', 10),
            relief='flat',
            padx=10,
            pady=10
        )
        self.log_text.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Footer
        footer = tk.Label(
            self.root,
            text="TCP Chat Server v1.0 | Port: 5555",
            bg='#1e1e1e',
            fg='#888',
            font=('Segoe UI', 8)
        )
        footer.pack(pady=5)
    
    def log(self, message):
        """Thêm log vào text widget"""
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
    
    def start_server(self):
        """Khởi động server"""
        if self.server.start_server(self.log):
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.status_label.config(
                text="🟢 Trạng thái: Đang chạy",
                fg='#51cf66'
            )
    
    def stop_server(self):
        """Dừng server"""
        self.server.stop_server()
        self.log("[SERVER] Đã dừng server\n")
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(
            text="⚫ Trạng thái: Đã dừng",
            fg='#ff6b6b'
        )
    
    def clear_logs(self):
        """Xóa logs"""
        self.log_text.delete(1.0, tk.END)
    
    def on_closing(self):
        """Xử lý khi đóng cửa sổ"""
        if messagebox.askokcancel("Thoát", "Bạn có chắc muốn thoát?"):
            self.server.stop_server()
            self.root.destroy()
    
    def run(self):
        """Chạy GUI"""
        self.root.mainloop()


if __name__ == "__main__":
    app = ServerGUI()
    app.run()