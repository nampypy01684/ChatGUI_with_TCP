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
        self.room = "Phòng chung"
        self.connected = False
        self.receive_thread = None
        # callback để GUI cập nhật danh sách user
        self.user_list_callback = None

    def connect(self, info, callback):
        """
        Kết nối đến server
        info = {
            'username': str,
            'room': str,
            'password': str
        }
        """
        try:
            self.username = info['username']
            self.room = info.get('room', 'Phòng chung')
            password = info.get('password', "") or ""

            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))

            # Gửi gói JOIN dạng JSON
            join_packet = {
                'type': 'join',
                'username': self.username,
                'room': self.room,
                'password': password
            }
            self.client_socket.send(json.dumps(join_packet).encode('utf-8'))
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
                if not data:
                    break

                message_data = json.loads(data)

                msg_type = message_data.get('type')

                if msg_type == 'history':
                    # Hiển thị lịch sử
                    callback("[LỊCH SỬ] Đang tải lịch sử chat...\n", "system")
                    for entry in message_data['data']:
                        # entry: timestamp, username, message, room
                        ts_full = entry.get('timestamp', '')
                        # lấy phần giờ nếu có
                        if ' ' in ts_full:
                            timestamp = ts_full.split()[1]
                        else:
                            timestamp = ts_full

                        username = entry.get('username', '???')
                        msg = entry.get('message', '')
                        line = f"[{timestamp}] {username}: {msg}\n"
                        callback(line, "history")
                    callback("[LỊCH SỬ] Đã tải xong lịch sử chat\n\n", "system")

                elif msg_type == 'message':
                    # Tin nhắn public hoặc thông báo từ SERVER
                    sender = message_data.get('sender', '???')
                    message = message_data.get('message', '')
                    timestamp = message_data.get('timestamp', datetime.now().strftime("%H:%M:%S"))

                    if sender == "SERVER":
                        msg = f"[{timestamp}] 🔔 {message}\n"
                        callback(msg, "server")
                    elif sender == self.username:
                        msg = f"[{timestamp}] Bạn: {message}\n"
                        callback(msg, "self")
                    else:
                        msg = f"[{timestamp}] {sender}: {message}\n"
                        callback(msg, "other")

                elif msg_type == 'private':
                    # Tin nhắn riêng
                    sender = message_data.get('sender', '???')
                    recipient = message_data.get('recipient', '???')
                    message = message_data.get('message', '')
                    timestamp = message_data.get('timestamp', datetime.now().strftime("%H:%M:%S"))

                    if sender == self.username:
                        line = f"[{timestamp}] (PM tới {recipient}) {message}\n"
                        callback(line, "self")
                    elif recipient == self.username:
                        line = f"[{timestamp}] (PM từ {sender}) {message}\n"
                        callback(line, "other")
                    else:
                        # Trường hợp hiếm (không trùng) -> cứ hiện bình thường
                        line = f"[{timestamp}] (PM {sender} -> {recipient}) {message}\n"
                        callback(line, "other")

                elif msg_type == 'user_list':
                    # Cập nhật danh sách người dùng phòng hiện tại
                    if self.user_list_callback:
                        users = message_data.get('users', [])
                        admin = message_data.get('admin')
                        self.user_list_callback(users, admin)

                elif msg_type == 'error':
                    # Lỗi từ server (ví dụ sai mật khẩu)
                    err_msg = message_data.get('message', 'Lỗi không xác định từ server.')
                    callback(f"[LỖI] {err_msg}\n", "error")

                else:
                    # Unrecognized
                    callback(f"[SYSTEM] Nhận gói tin không xác định: {message_data}\n", "system")

            except Exception as e:
                if self.connected:
                    callback(f"[LỖI] {e}\n", "error")
                break

        self.connected = False
        callback("[DISCONNECT] Đã ngắt kết nối khỏi server\n", "error")

    def send_message(self, message):
        """Gửi tin nhắn public"""
        try:
            if self.connected and message.strip():
                self.client_socket.send(message.encode('utf-8'))
                return True
        except Exception as e:
            print(f"Lỗi gửi tin nhắn: {e}")
        return False

    def send_private_message(self, target, message):
        """Gửi tin nhắn riêng tới target trong cùng phòng"""
        try:
            if self.connected and message.strip():
                # Gửi theo cú pháp /pm target noi_dung
                payload = f"/pm {target} {message}"
                self.client_socket.send(payload.encode('utf-8'))
                return True
        except Exception as e:
            print(f"Lỗi gửi PM: {e}")
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
        self.dialog.geometry("420x360")
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
        content_frame.pack(expand=True, fill='both', padx=30, pady=20)

        info_label = tk.Label(
            content_frame,
            text="Nhập thông tin để tham gia phòng chat:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11)
        )
        info_label.pack(pady=(0, 10))

        # Username entry
        user_label = tk.Label(
            content_frame,
            text="Tên hiển thị:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 10)
        )
        user_label.pack(anchor='w')

        user_frame = tk.Frame(content_frame, bg='#2d2d2d', relief='flat')
        user_frame.pack(fill='x', pady=(0, 8))

        icon_label = tk.Label(
            user_frame,
            text="👤",
            bg='#2d2d2d',
            font=('Segoe UI', 14)
        )
        icon_label.pack(side='left', padx=(10, 5))

        self.username_entry = tk.Entry(
            user_frame,
            font=('Segoe UI', 12),
            bg='#2d2d2d',
            fg='white',
            relief='flat',
            insertbackground='white',
            border=0
        )
        self.username_entry.pack(side='left', fill='both', expand=True, padx=(5, 10), pady=8)

        # Room entry
        room_label = tk.Label(
            content_frame,
            text="Tên phòng:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 10)
        )
        room_label.pack(anchor='w', pady=(5, 0))

        self.room_entry = tk.Entry(
            content_frame,
            font=('Segoe UI', 11),
            bg='#2d2d2d',
            fg='white',
            relief='flat',
            insertbackground='white',
        )
        self.room_entry.pack(fill='x', pady=(0, 8))
        self.room_entry.insert(0, "Phòng chung")

        # Password entry
        pass_label = tk.Label(
            content_frame,
            text="Mật khẩu phòng (nếu có):",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 10)
        )
        pass_label.pack(anchor='w', pady=(5, 0))

        self.pass_entry = tk.Entry(
            content_frame,
            font=('Segoe UI', 11),
            bg='#2d2d2d',
            fg='white',
            relief='flat',
            insertbackground='white',
            show='*'
        )
        self.pass_entry.pack(fill='x', pady=(0, 8))

        hint_label = tk.Label(
            content_frame,
            text="• Người đầu tiên vào phòng sẽ là QTV và đặt được mật khẩu.\n"
                 "• Người vào sau phải nhập đúng mật khẩu (nếu đã đặt).",
            bg='#1e1e1e',
            fg='#bbbbbb',
            font=('Segoe UI', 8),
            justify='left'
        )
        hint_label.pack(anchor='w', pady=(2, 10))

        # Buttons
        btn_frame = tk.Frame(content_frame, bg='#1e1e1e')
        btn_frame.pack(pady=10)

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
            pady=8
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
            pady=8
        )
        cancel_btn.pack(side='left', padx=5)

        # Enter để submit
        self.username_entry.bind('<Return>', lambda e: self.submit())
        self.room_entry.bind('<Return>', lambda e: self.submit())
        self.pass_entry.bind('<Return>', lambda e: self.submit())

    def submit(self):
        """Xác nhận tên người dùng & phòng"""
        username = self.username_entry.get().strip()
        room = self.room_entry.get().strip() or "Phòng chung"
        password = self.pass_entry.get().strip()

        if not username:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập tên người dùng!")
            return

        self.result = {
            'username': username,
            'room': room,
            'password': password
        }
        self.dialog.destroy()

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
        self.root.geometry("900x700")
        self.root.configure(bg='#1e1e1e')

        self.client = ChatClient()
        self.setup_ui()

        # Gắn callback cập nhật user list
        self.client.user_list_callback = self.update_user_list

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
            text="💬 Chat Application (Multi-room)",
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

        # Body: Chat + User list
        body_frame = tk.Frame(self.root, bg='#1e1e1e')
        body_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        # Chat area (trái)
        left_frame = tk.Frame(body_frame, bg='#1e1e1e')
        left_frame.pack(side='left', fill='both', expand=True, padx=(10, 5))

        chat_label = tk.Label(
            left_frame,
            text="💭 Tin nhắn:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            anchor='w'
        )
        chat_label.pack(fill='x', pady=(5, 5))

        chat_frame = tk.Frame(left_frame, bg='#2d2d2d', relief='sunken', bd=2)
        chat_frame.pack(fill='both', expand=True, pady=(0, 10))

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

        # User list (phải)
        right_frame = tk.Frame(body_frame, bg='#1e1e1e')
        right_frame.pack(side='left', fill='y', padx=(5, 10))

        user_label = tk.Label(
            right_frame,
            text="👥 Người đang hoạt động:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            anchor='w'
        )
        user_label.pack(fill='x', pady=(5, 5))

        self.user_listbox = tk.Listbox(
            right_frame,
            bg='#0d1117',
            fg='white',
            font=('Segoe UI', 10),
            height=20,
            selectbackground='#32de84',
            relief='flat',
            activestyle='none'
        )
        self.user_listbox.pack(fill='y', expand=False, padx=2, pady=(0, 5))

        hint_label = tk.Label(
            right_frame,
            text="Double-click vào tên\nđể nhắn riêng 😉",
            bg='#1e1e1e',
            fg='#bbbbbb',
            font=('Segoe UI', 9),
            justify='center'
        )
        hint_label.pack(pady=(0, 5))

        self.user_listbox.bind('<Double-Button-1>', self.on_user_double_click)

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
            text="TCP Chat Client v2.0 | Multi-room + QTV + PM | Server: 127.0.0.1:5555",
            bg='#1e1e1e',
            fg='#888',
            font=('Segoe UI', 8)
        )
        footer.pack(pady=5)

    def show_login(self):
        """Hiển thị dialog đăng nhập"""
        dialog = LoginDialog(self.root)
        info = dialog.show()

        if info:
            self.connect(info)
        else:
            self.root.quit()

    def connect(self, info):
        """Kết nối đến server"""
        if self.client.connect(info, self.display_message):
            username = info['username']
            room = info.get('room', 'Phòng chung')

            self.user_label.config(text=f"👤 {username} | 🏠 Phòng: {room}")
            self.status_label.config(
                text="🟢 Đã kết nối",
                fg='#51cf66'
            )
            self.message_entry.config(state='normal')
            self.send_btn.config(state='normal')
            self.disconnect_btn.config(state='normal')
            self.display_message(f"[SYSTEM] Đã kết nối với phòng '{room}'\n", "system")

    def display_message(self, message, tag="other"):
        """Hiển thị tin nhắn trong chat"""
        self.chat_text.config(state='normal')
        self.chat_text.insert(tk.END, message, tag)
        self.chat_text.see(tk.END)
        self.chat_text.config(state='disabled')

    def update_user_list(self, users, admin):
        """Cập nhật Listbox người đang hoạt động"""
        self.user_listbox.delete(0, tk.END)
        for u in users:
            label = u
            if u == admin:
                label += " (QTV)"
            if u == self.client.username:
                label += " (bạn)"
            self.user_listbox.insert(tk.END, label)

    def extract_username_from_listbox(self, item_text):
        """Lấy username gốc từ dòng hiển thị trong listbox"""
        # ví dụ: "nam (QTV)" -> "nam"
        return item_text.split(' (')[0]

    def on_user_double_click(self, event):
        """Double-click vào user để gửi PM"""
        selection = self.user_listbox.curselection()
        if not selection:
            return

        item_text = self.user_listbox.get(selection[0])
        target = self.extract_username_from_listbox(item_text)

        # Không pm chính mình
        if target == self.client.username:
            messagebox.showinfo("Nhắn riêng", "Không cần nhắn riêng chính mình đâu 😆")
            return

        msg = simpledialog.askstring(
            "Nhắn riêng",
            f"Nhập tin nhắn gửi riêng cho {target}:",
            parent=self.root
        )
        if msg:
            if not self.client.send_private_message(target, msg):
                messagebox.showerror("Lỗi", "Không thể gửi tin nhắn riêng!")

    def send_message(self):
        """Gửi tin nhắn public"""
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
            self.update_user_list([], None)

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
