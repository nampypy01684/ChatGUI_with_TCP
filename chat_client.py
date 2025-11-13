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

        # callbacks cho GUI
        self.user_list_callback = None
        self.room_list_callback = None
        self.room_joined_callback = None

    def connect(self, username, callback):
        try:
            self.username = username
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))

            # gửi username plain text
            self.client_socket.send(username.encode('utf-8'))
            self.connected = True

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
        """Nhận NDJSON: mỗi gói 1 dòng JSON"""
        buffer = ""
        while self.connected:
            try:
                chunk = self.client_socket.recv(4096).decode('utf-8')
                if not chunk:
                    break
                buffer += chunk

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        message_data = json.loads(line)
                    except json.JSONDecodeError as e:
                        callback(f"[LỖI] JSON lỗi: {e}\n", "error")
                        continue

                    msg_type = message_data.get('type')

                    if msg_type == 'history':
                        room = message_data.get('room', 'Phòng chung')
                        callback(f"[LỊCH SỬ] Đang tải lịch sử phòng '{room}'...\n", "system")
                        for entry in message_data.get('data', []):
                            ts_full = entry.get('timestamp', '')
                            if ' ' in ts_full:
                                timestamp = ts_full.split()[1]
                            else:
                                timestamp = ts_full
                            username = entry.get('username', '???')
                            msg = entry.get('message', '')
                            line2 = f"[{timestamp}] {username}: {msg}\n"
                            callback(line2, "history")
                        callback("[LỊCH SỬ] Đã tải xong lịch sử\n\n", "system")

                    elif msg_type == 'message':
                        sender = message_data.get('sender', '???')
                        message = message_data.get('message', '')
                        timestamp = message_data.get(
                            'timestamp',
                            datetime.now().strftime("%H:%M:%S")
                        )
                        room = message_data.get('room', 'Phòng chung')

                        if sender == "SERVER":
                            line2 = f"[{timestamp}] 🔔 ({room}) {message}\n"
                            callback(line2, "server")
                        elif sender == self.username:
                            line2 = f"[{timestamp}] ({room}) Bạn: {message}\n"
                            callback(line2, "self")
                        else:
                            line2 = f"[{timestamp}] ({room}) {sender}: {message}\n"
                            callback(line2, "other")

                    elif msg_type == 'private':
                        sender = message_data.get('sender', '???')
                        recipient = message_data.get('recipient', '???')
                        message = message_data.get('message', '')
                        timestamp = message_data.get(
                            'timestamp',
                            datetime.now().strftime("%H:%M:%S")
                        )
                        if sender == self.username:
                            line2 = f"[{timestamp}] (PM tới {recipient}) {message}\n"
                            callback(line2, "self")
                        elif recipient == self.username:
                            line2 = f"[{timestamp}] (PM từ {sender}) {message}\n"
                            callback(line2, "other")
                        else:
                            line2 = f"[{timestamp}] (PM {sender} -> {recipient}) {message}\n"
                            callback(line2, "other")

                    elif msg_type == 'user_list':
                        if self.user_list_callback:
                            users = message_data.get('users', [])
                            self.user_list_callback(users)

                    elif msg_type == 'room_list':
                        if self.room_list_callback:
                            rooms = message_data.get('rooms', [])
                            self.room_list_callback(rooms)

                    elif msg_type == 'room_joined':
                        room = message_data.get('room')
                        is_admin = message_data.get('is_admin', False)
                        if self.room_joined_callback and room:
                            self.room_joined_callback(room, is_admin)
                        callback(f"[SYSTEM] Bạn đã vào phòng '{room}'\n", "system")

                    elif msg_type == 'admin_kicked':
                        room = message_data.get('room', '')
                        msg = message_data.get('message', '')
                        line2 = f"[SYSTEM] ({room}) {msg}\n"
                        callback(line2, "system")

                    elif msg_type == 'error':
                        err_msg = message_data.get('message', 'Lỗi không xác định từ server.')
                        callback(f"[LỖI] {err_msg}\n", "error")
                        messagebox.showerror("Lỗi", err_msg)

                    else:
                        callback(f"[SYSTEM] Nhận gói tin không xác định: {message_data}\n",
                                 "system")

            except Exception as e:
                if self.connected:
                    callback(f"[LỖI] {e}\n", "error")
                break

        self.connected = False
        callback("[DISCONNECT] Đã ngắt kết nối khỏi server\n", "error")

    # ---- GỬI ----
    def send_packet(self, data):
        try:
            if self.connected:
                payload = json.dumps(data) + "\n"
                self.client_socket.send(payload.encode('utf-8'))
                return True
        except Exception as e:
            print(f"Lỗi gửi packet: {e}")
        return False

    def send_message(self, message):
        if not message.strip():
            return False
        data = {'type': 'chat', 'message': message}
        return self.send_packet(data)

    def send_private_message(self, target, message):
        if not message.strip():
            return False
        data = {'type': 'private', 'to': target, 'message': message}
        return self.send_packet(data)

    def create_room(self, name, is_private=False, password=""):
        data = {
            'type': 'create_room',
            'room_name': name,
            'is_private': bool(is_private),
            'password': password or ""
        }
        return self.send_packet(data)

    def join_room(self, name, password=""):
        data = {
            'type': 'join_room',
            'room_name': name,
            'password': password or ""
        }
        return self.send_packet(data)

    def admin_kick(self, room, target):
        data = {
            'type': 'admin_kick',
            'room': room,
            'target': target
        }
        return self.send_packet(data)

    def admin_change_password(self, room, new_password):
        data = {
            'type': 'admin_change_password',
            'room': room,
            'new_password': new_password
        }
        return self.send_packet(data)

    def admin_rename_room(self, room, new_name):
        data = {
            'type': 'admin_rename_room',
            'room': room,
            'new_name': new_name
        }
        return self.send_packet(data)

    def disconnect(self):
        self.connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass


class LoginDialog:
    def __init__(self, parent):
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("🚀 Tham gia Chat")
        self.dialog.geometry("400x300")
        self.dialog.configure(bg='#1e1e1e')
        self.dialog.resizable(False, False)

        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.setup_ui()
        self.username_entry.focus()

    def setup_ui(self):
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

        content_frame = tk.Frame(self.dialog, bg='#1e1e1e')
        content_frame.pack(expand=True, fill='both', padx=30, pady=20)

        info_label = tk.Label(
            content_frame,
            text="Nhập tên hiển thị để tham gia:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11)
        )
        info_label.pack(pady=(0, 10))

        entry_frame = tk.Frame(content_frame, bg='#2d2d2d', relief='flat')
        entry_frame.pack(fill='x', pady=(0, 10))

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
        self.username_entry.pack(side='left', fill='both', expand=True,
                                 padx=(5, 10), pady=10)
        self.username_entry.bind('<Return>', lambda e: self.submit())

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
        username = self.username_entry.get().strip()
        if username:
            self.result = username
            self.dialog.destroy()
        else:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập tên người dùng!")

    def cancel(self):
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.result


class ClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("💬 TCP Chat Client")
        self.root.geometry("1000x700")
        self.root.configure(bg='#1e1e1e')

        self.client = ChatClient()
        self.current_room = "Phòng chung"
        self.is_admin_current_room = False

        self.setup_ui()

        self.client.user_list_callback = self.update_user_list
        self.client.room_list_callback = self.update_room_list
        self.client.room_joined_callback = self.on_room_joined

        self.root.after(100, self.show_login)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg='#0d7377', height=90)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame,
            text="💬 Chat Application (Lobby + Rooms + QTV)",
            bg='#0d7377',
            fg='white',
            font=('Segoe UI', 22, 'bold')
        )
        title_label.pack(expand=True)

        status_frame = tk.Frame(self.root, bg='#2d2d2d', relief='groove', bd=2)
        status_frame.pack(fill='x', padx=10, pady=10)

        self.status_label = tk.Label(
            status_frame,
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
            status_frame,
            text="👤 Chưa đăng nhập",
            bg='#2d2d2d',
            fg='#ffd43b',
            font=('Segoe UI', 10, 'bold'),
            anchor='e',
            padx=15,
            pady=8
        )
        self.user_label.pack(side='right')

        body_frame = tk.Frame(self.root, bg='#1e1e1e')
        body_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        # -------- CHAT --------
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

        self.chat_text.tag_config('self', foreground='#58a6ff')
        self.chat_text.tag_config('other', foreground='#79c0ff')
        self.chat_text.tag_config('server', foreground='#ffd43b')
        self.chat_text.tag_config('system', foreground='#8b949e')
        self.chat_text.tag_config('history', foreground='#6e7681')
        self.chat_text.tag_config('error', foreground='#ff6b6b')

        # -------- SIDEBAR --------
        right_frame = tk.Frame(body_frame, bg='#1e1e1e')
        right_frame.pack(side='right', fill='y', padx=(5, 10))

        # Online users
        user_label = tk.Label(
            right_frame,
            text="👥 Người đang online:",
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
            height=8,
            selectbackground='#32de84',
            relief='flat',
            activestyle='none'
        )
        self.user_listbox.pack(fill='x', padx=2, pady=(0, 5))

        user_hint = tk.Label(
            right_frame,
            text="Double-click để nhắn riêng 😉",
            bg='#1e1e1e',
            fg='#bbbbbb',
            font=('Segoe UI', 9),
            justify='center'
        )
        user_hint.pack(pady=(0, 5))

        self.user_listbox.bind('<Double-Button-1>', self.on_user_double_click)

        pm_btn = tk.Button(
            right_frame,
            text="✉ Nhắn riêng",
            command=self.pm_selected_user,
            bg='#456990',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=10,
            pady=5
        )
        pm_btn.pack(fill='x', pady=(0, 10))

        # Rooms
        room_label = tk.Label(
            right_frame,
            text="🏠 Phòng chat:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            anchor='w'
        )
        room_label.pack(fill='x', pady=(5, 5))

        self.room_listbox = tk.Listbox(
            right_frame,
            bg='#0d1117',
            fg='white',
            font=('Segoe UI', 10),
            height=8,
            selectbackground='#ffb703',
            relief='flat',
            activestyle='none'
        )
        self.room_listbox.pack(fill='x', padx=2, pady=(0, 5))

        room_hint = tk.Label(
            right_frame,
            text="Double-click phòng để tham gia.\nPhòng 🔒 là private.",
            bg='#1e1e1e',
            fg='#bbbbbb',
            font=('Segoe UI', 9),
            justify='center'
        )
        room_hint.pack(pady=(0, 5))

        self.room_listbox.bind('<Double-Button-1>', self.on_room_double_click)

        btn_room_frame = tk.Frame(right_frame, bg='#1e1e1e')
        btn_room_frame.pack(fill='x', pady=(5, 5))

        create_room_btn = tk.Button(
            btn_room_frame,
            text="➕ Tạo phòng",
            command=self.create_room_dialog,
            bg='#32de84',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=10,
            pady=5
        )
        create_room_btn.pack(fill='x', pady=(0, 5))

        join_room_btn = tk.Button(
            btn_room_frame,
            text="➡ Tham gia phòng",
            command=self.join_selected_room,
            bg='#fca311',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=10,
            pady=5
        )
        join_room_btn.pack(fill='x', pady=(0, 5))

        # QTV controls
        admin_label = tk.Label(
            right_frame,
            text="⭐ Quyền QTV (phòng hiện tại):",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            anchor='w'
        )
        admin_label.pack(fill='x', pady=(10, 5))

        self.admin_btn_kick = tk.Button(
            right_frame,
            text="👢 Kick khỏi phòng",
            command=self.admin_kick_selected_user,
            bg='#e63946',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=10,
            pady=5,
            state='disabled'
        )
        self.admin_btn_kick.pack(fill='x', pady=(0, 3))

        self.admin_btn_rename = tk.Button(
            right_frame,
            text="✏ Đổi tên phòng",
            command=self.admin_rename_room,
            bg='#457b9d',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=10,
            pady=5,
            state='disabled'
        )
        self.admin_btn_rename.pack(fill='x', pady=(0, 3))

        self.admin_btn_pass = tk.Button(
            right_frame,
            text="🔐 Đổi mật khẩu",
            command=self.admin_change_password,
            bg='#1d3557',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
            relief='flat',
            padx=10,
            pady=5,
            state='disabled'
        )
        self.admin_btn_pass.pack(fill='x', pady=(0, 3))

        # Input message
        input_frame = tk.Frame(self.root, bg='#1e1e1e')
        input_frame.pack(fill='x', padx=20, pady=(0, 15))

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

        footer = tk.Label(
            self.root,
            text="TCP Chat Client | Online list + Rooms (Public/Private) + PM + QTV | Server: 127.0.0.1:5555",
            bg='#1e1e1e',
            fg='#888',
            font=('Segoe UI', 8)
        )
        footer.pack(pady=5)

    # -------- LOGIN & CONNECT --------
    def show_login(self):
        dialog = LoginDialog(self.root)
        username = dialog.show()
        if username:
            self.connect(username)
        else:
            self.root.quit()

    def connect(self, username):
        if self.client.connect(username, self.display_message):
            self.current_room = "Phòng chung"
            self.is_admin_current_room = False
            self.update_admin_buttons_state()

            self.user_label.config(
                text=f"👤 {username} | 🏠 Phòng: {self.current_room}"
            )
            self.status_label.config(
                text="🟢 Đã kết nối",
                fg='#51cf66'
            )
            self.message_entry.config(state='normal')
            self.send_btn.config(state='normal')
            self.disconnect_btn.config(state='normal')
            self.display_message(
                f"[SYSTEM] Đã kết nối, bạn đang ở phòng '{self.current_room}'\n",
                "system"
            )

    # -------- UI HELPERS --------
    def display_message(self, message, tag="other"):
        self.chat_text.config(state='normal')
        self.chat_text.insert(tk.END, message, tag)
        self.chat_text.see(tk.END)
        self.chat_text.config(state='disabled')

    def update_user_list(self, users):
        self.user_listbox.delete(0, tk.END)
        for u in users:
            label = u
            if u == self.client.username:
                label += " (bạn)"
            self.user_listbox.insert(tk.END, label)

    def update_room_list(self, rooms):
        self.room_listbox.delete(0, tk.END)
        for r in rooms:
            name = r.get('name', '???')
            is_private = r.get('is_private', False)
            members_count = r.get('members_count', 0)
            label = name
            if is_private:
                label += " 🔒"
            label += f" ({members_count})"
            self.room_listbox.insert(tk.END, label)

    def extract_username_from_listbox(self, text):
        return text.split(' (')[0]

    def extract_room_name_from_listbox(self, text):
        if " 🔒" in text:
            text = text.split(" 🔒")[0]
        if " (" in text:
            text = text.split(" (")[0]
        return text

    def on_user_double_click(self, event):
        self.pm_selected_user()

    def pm_selected_user(self):
        selection = self.user_listbox.curselection()
        if not selection:
            messagebox.showinfo("Nhắn riêng", "Hãy chọn 1 người trong danh sách online.")
            return
        item = self.user_listbox.get(selection[0])
        target = self.extract_username_from_listbox(item)
        if target == self.client.username:
            messagebox.showinfo("Nhắn riêng", "Không cần nhắn riêng chính mình 😆")
            return

        msg = simpledialog.askstring(
            "Nhắn riêng",
            f"Nhập tin nhắn gửi riêng cho {target}:",
            parent=self.root
        )
        if msg:
            if not self.client.send_private_message(target, msg):
                messagebox.showerror("Lỗi", "Không thể gửi tin nhắn riêng!")

    def on_room_double_click(self, event):
        self.join_selected_room()

    def join_selected_room(self):
        selection = self.room_listbox.curselection()
        if not selection:
            messagebox.showinfo("Tham gia phòng", "Hãy chọn 1 phòng trong danh sách.")
            return
        item = self.room_listbox.get(selection[0])
        room_name = self.extract_room_name_from_listbox(item)

        password = ""
        if "🔒" in item:
            password = simpledialog.askstring(
                "Mật khẩu phòng",
                f"Nhập mật khẩu để vào phòng '{room_name}':",
                parent=self.root,
                show='*'
            )
            if password is None:
                return

        if not self.client.join_room(room_name, password):
            messagebox.showerror("Lỗi", "Không thể gửi yêu cầu tham gia phòng.")

    def create_room_dialog(self):
        room_name = simpledialog.askstring(
            "Tạo phòng chat",
            "Nhập tên phòng:",
            parent=self.root
        )
        if not room_name:
            return

        result = messagebox.askyesno(
            "Loại phòng",
            "Bạn muốn tạo phòng PRIVATE (có mật khẩu)?\n"
            "Yes: Private\nNo: Public"
        )
        is_private = result
        password = ""
        if is_private:
            password = simpledialog.askstring(
                "Mật khẩu phòng",
                f"Đặt mật khẩu cho phòng '{room_name}':",
                parent=self.root,
                show='*'
            )
            if password is None:
                return

        if not self.client.create_room(room_name, is_private, password):
            messagebox.showerror("Lỗi", "Không thể tạo phòng!")

    def on_room_joined(self, room_name, is_admin):
        self.current_room = room_name
        self.is_admin_current_room = bool(is_admin) and (room_name != "Phòng chung")
        self.update_admin_buttons_state()
        self.user_label.config(
            text=f"👤 {self.client.username} | 🏠 Phòng: {self.current_room}"
        )

    def update_admin_buttons_state(self):
        state = 'normal' if self.is_admin_current_room else 'disabled'
        self.admin_btn_kick.config(state=state)
        self.admin_btn_rename.config(state=state)
        self.admin_btn_pass.config(state=state)

    # -------- QTV ACTIONS --------
    def admin_kick_selected_user(self):
        if not self.is_admin_current_room:
            messagebox.showwarning("QTV", "Bạn không phải QTV phòng hiện tại.")
            return
        selection = self.user_listbox.curselection()
        if not selection:
            messagebox.showinfo("Kick user", "Hãy chọn 1 người trong danh sách online.")
            return
        item = self.user_listbox.get(selection[0])
        target = self.extract_username_from_listbox(item)
        if target == self.client.username:
            messagebox.showinfo("Kick user", "Không thể tự kick chính mình.")
            return

        if not messagebox.askyesno(
            "Xác nhận kick",
            f"Bạn chắc chắn muốn kick {target} khỏi phòng '{self.current_room}'?"
        ):
            return

        if not self.client.admin_kick(self.current_room, target):
            messagebox.showerror("Lỗi", "Không thể gửi lệnh kick.")

    def admin_rename_room(self):
        if not self.is_admin_current_room:
            messagebox.showwarning("QTV", "Bạn không phải QTV phòng hiện tại.")
            return
        new_name = simpledialog.askstring(
            "Đổi tên phòng",
            f"Tên mới cho phòng '{self.current_room}':",
            parent=self.root
        )
        if not new_name:
            return
        if not self.client.admin_rename_room(self.current_room, new_name):
            messagebox.showerror("Lỗi", "Không thể gửi lệnh đổi tên phòng.")

    def admin_change_password(self):
        if not self.is_admin_current_room:
            messagebox.showwarning("QTV", "Bạn không phải QTV phòng hiện tại.")
            return
        new_pass = simpledialog.askstring(
            "Đổi mật khẩu phòng",
            "Nhập mật khẩu mới (để trống = gỡ mật khẩu):",
            parent=self.root,
            show='*'
        )
        if new_pass is None:
            return
        if not self.client.admin_change_password(self.current_room, new_pass):
            messagebox.showerror("Lỗi", "Không thể gửi lệnh đổi mật khẩu.")

    # -------- SEND / DISCONNECT --------
    def send_message(self):
        message = self.message_entry.get().strip()
        if message:
            if self.client.send_message(message):
                self.message_entry.delete(0, tk.END)
            else:
                messagebox.showerror("Lỗi", "Không thể gửi tin nhắn!")

    def disconnect(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn ngắt kết nối?"):
            self.client.disconnect()
            self.message_entry.config(state='disabled')
            self.send_btn.config(state='disabled')
            self.disconnect_btn.config(state='disabled')
            self.status_label.config(
                text="⚫ Đã ngắt kết nối",
                fg='#ff6b6b'
            )
            self.update_user_list([])
            self.update_room_list([])
            self.is_admin_current_room = False
            self.update_admin_buttons_state()

    def on_closing(self):
        if self.client.connected:
            if messagebox.askokcancel("Thoát", "Bạn có chắc muốn thoát?"):
                self.client.disconnect()
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ClientGUI()
    app.run()
