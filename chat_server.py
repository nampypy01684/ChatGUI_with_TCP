import socket
import threading
import json
import os
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox


class ChatServer:
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 5555
        self.server_socket = None
        # {socket: {'username': str, 'current_room': str}}
        self.clients = {}
        # {room_name: {'is_private': bool, 'password': str, 'creator': str, 'members': set[socket]}}
        self.rooms = {}
        self.running = False
        self.history_file = 'chat_history.json'
        self.chat_history = self.load_history()

    # ----------------- LỊCH SỬ CHAT -----------------
    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.chat_history[-1000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Lỗi khi lưu lịch sử: {e}")

    def add_to_history(self, username, message, room="Phòng chung"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            'timestamp': timestamp,
            'username': username,
            'message': message,
            'room': room
        }
        self.chat_history.append(entry)
        self.save_history()

    # ----------------- HỖ TRỢ GỬI -----------------
    def send_json(self, client_socket, data):
        """Gửi 1 gói JSON, kết thúc bằng \\n để client tách được."""
        try:
            payload = json.dumps(data) + "\n"
            client_socket.send(payload.encode('utf-8'))
        except Exception:
            pass

    def broadcast_user_list(self):
        """Gửi danh sách người online tới tất cả client"""
        users = []
        for info in self.clients.values():
            username = info.get('username')
            if username and username not in users:
                users.append(username)

        data = {'type': 'user_list', 'users': users}
        payload = json.dumps(data) + "\n"

        disconnected = []
        for sock in list(self.clients.keys()):
            try:
                sock.send(payload.encode('utf-8'))
            except Exception:
                disconnected.append(sock)

        for sock in disconnected:
            self.remove_client(sock)

    def broadcast_room_list(self):
        """Gửi danh sách phòng tới tất cả client"""
        rooms_info = []
        for name, info in self.rooms.items():
            rooms_info.append({
                'name': name,
                'is_private': info.get('is_private', False),
                'members_count': len(info.get('members', [])),
                'creator': info.get('creator', '???')
            })

        data = {'type': 'room_list', 'rooms': rooms_info}
        payload = json.dumps(data) + "\n"

        disconnected = []
        for sock in list(self.clients.keys()):
            try:
                sock.send(payload.encode('utf-8'))
            except Exception:
                disconnected.append(sock)

        for sock in disconnected:
            self.remove_client(sock)

    def broadcast_room_message(self, room_name, sender, message, msg_type='message'):
        """Broadcast tin nhắn trong 1 phòng"""
        if room_name not in self.rooms:
            return

        data = {
            'type': msg_type,
            'sender': sender,
            'message': message,
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'room': room_name
        }
        payload = json.dumps(data) + "\n"

        disconnected = []
        for sock in list(self.rooms[room_name]['members']):
            try:
                sock.send(payload.encode('utf-8'))
            except Exception:
                disconnected.append(sock)

        for sock in disconnected:
            self.remove_client(sock)

    # ----------------- QUẢN LÝ CLIENT & PHÒNG -----------------
    def ensure_default_room(self):
        """Tạo phòng chung nếu chưa có"""
        if "Phòng chung" not in self.rooms:
            self.rooms["Phòng chung"] = {
                'is_private': False,
                'password': "",
                'creator': "SERVER",
                'members': set()
            }

    def add_client_to_room(self, client_socket, room_name):
        """Chuyển client vào 1 phòng"""
        self.ensure_default_room()
        info = self.clients.get(client_socket)
        if not info:
            return

        # Rời phòng cũ nếu có
        old_room = info.get('current_room')
        if old_room and old_room in self.rooms:
            self.rooms[old_room]['members'].discard(client_socket)

        # Tạo phòng mới nếu chưa có
        if room_name not in self.rooms:
            self.rooms[room_name] = {
                'is_private': False,
                'password': "",
                'creator': info['username'],
                'members': set()
            }

        self.rooms[room_name]['members'].add(client_socket)
        info['current_room'] = room_name

        # Gửi lịch sử phòng đó cho client
        room_history = [
            entry for entry in self.chat_history
            if entry.get('room', 'Phòng chung') == room_name
        ][-50:]
        history_msg = {
            'type': 'history',
            'room': room_name,
            'data': room_history
        }
        self.send_json(client_socket, history_msg)

        # Thông báo join phòng
        join_msg = f"{info['username']} đã tham gia phòng {room_name}!"
        self.broadcast_room_message(room_name, "SERVER", join_msg)
        self.add_to_history("SERVER", join_msg, room_name)

        self.broadcast_room_list()

    def remove_client(self, client_socket):
        """Xóa client khỏi server & phòng"""
        info = self.clients.pop(client_socket, None)
        if not info:
            try:
                client_socket.close()
            except Exception:
                pass
            return

        username = info.get('username', '???')
        room_name = info.get('current_room')

        if room_name and room_name in self.rooms:
            self.rooms[room_name]['members'].discard(client_socket)
            leave_msg = f"{username} đã rời khỏi phòng {room_name}!"
            self.broadcast_room_message(room_name, "SERVER", leave_msg)
            self.add_to_history("SERVER", leave_msg, room_name)

        for rn, rinfo in self.rooms.items():
            if client_socket in rinfo['members']:
                rinfo['members'].discard(client_socket)

        try:
            client_socket.close()
        except Exception:
            pass

        self.broadcast_user_list()
        self.broadcast_room_list()

    # ----------------- SERVER CORE -----------------
    def start_server(self, callback):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            callback(f"[SERVER] Đang chạy trên {self.host}:{self.port}\n")

            self.ensure_default_room()
            self.broadcast_room_list()

            accept_thread = threading.Thread(
                target=self.accept_connections,
                args=(callback,),
                daemon=True
            )
            accept_thread.start()
            return True
        except Exception as e:
            callback(f"[LỖI] Không thể khởi động server: {e}\n")
            return False

    def accept_connections(self, callback):
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                callback(f"[CONNECT] Kết nối mới từ {address}\n")
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address, callback),
                    daemon=True
                )
                client_thread.start()
            except Exception:
                break

    def handle_client(self, client_socket, address, callback):
        username = None
        try:
            # Bước 1: nhận username (plain text)
            username = client_socket.recv(1024).decode('utf-8').strip()
            if not username:
                username = f"user-{address[1]}"

            self.clients[client_socket] = {
                'username': username,
                'current_room': None
            }
            callback(f"[JOIN] {username} từ {address}\n")

            self.broadcast_user_list()
            self.broadcast_room_list()

            # Cho vào Phòng chung mặc định
            self.add_client_to_room(client_socket, "Phòng chung")

            # Bước 2: nhận JSON dạng NDJSON (mỗi gói 1 dòng)
            buffer = ""
            while self.running:
                chunk = client_socket.recv(4096).decode('utf-8')
                if not chunk:
                    break
                buffer += chunk

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        msg_type = data.get('type', 'chat')
                    except json.JSONDecodeError:
                        # fallback: xem như tin nhắn chat
                        data = {'message': line}
                        msg_type = 'chat'

                    info = self.clients.get(client_socket)
                    if not info:
                        break
                    username = info['username']
                    current_room = info.get('current_room') or "Phòng chung"

                    # --------- PHÂN LOẠI XỬ LÝ ---------
                    if msg_type == 'chat':
                        message = data.get('message', '')
                        if not message:
                            continue
                        callback(f"[{username} @ {current_room}] {message}\n")
                        self.broadcast_room_message(current_room, username, message)
                        self.add_to_history(username, message, current_room)

                    elif msg_type == 'private':
                        target_name = data.get('to')
                        pm_text = data.get('message', '')
                        if not target_name or not pm_text:
                            continue

                        target_socket = None
                        for sock, info2 in self.clients.items():
                            if info2.get('username') == target_name:
                                target_socket = sock
                                break

                        if not target_socket:
                            err = {'type': 'error',
                                   'message': f"Không tìm thấy người dùng '{target_name}'."}
                            self.send_json(client_socket, err)
                            continue

                        timestamp = datetime.now().strftime("%H:%M:%S")
                        payload = {
                            'type': 'private',
                            'sender': username,
                            'recipient': target_name,
                            'message': pm_text,
                            'timestamp': timestamp
                        }
                        self.send_json(client_socket, payload)
                        self.send_json(target_socket, payload)
                        callback(f"[PM] {username} -> {target_name}: {pm_text}\n")

                    elif msg_type == 'create_room':
                        room_name = data.get('room_name', '').strip()
                        is_private = bool(data.get('is_private', False))
                        password = data.get('password', '') or ""

                        if not room_name:
                            err = {'type': 'error', 'message': 'Tên phòng không được để trống.'}
                            self.send_json(client_socket, err)
                            continue

                        if room_name in self.rooms:
                            err = {'type': 'error',
                                   'message': 'Phòng đã tồn tại, vui lòng chọn tên khác.'}
                            self.send_json(client_socket, err)
                            continue

                        self.rooms[room_name] = {
                            'is_private': is_private,
                            'password': password,
                            'creator': username,
                            'members': set()
                        }
                        callback(f"[ROOM] {username} tạo phòng '{room_name}' (private={is_private})\n")

                        self.add_client_to_room(client_socket, room_name)
                        rinfo = self.rooms[room_name]
                        ok = {
                            'type': 'room_joined',
                            'room': room_name,
                            'creator': rinfo['creator'],
                            'is_admin': (username == rinfo['creator'])
                        }
                        self.send_json(client_socket, ok)

                    elif msg_type == 'join_room':
                        room_name = data.get('room_name', '').strip()
                        password = data.get('password', '') or ""

                        if room_name not in self.rooms:
                            err = {'type': 'error', 'message': 'Phòng không tồn tại.'}
                            self.send_json(client_socket, err)
                            continue

                        rinfo = self.rooms[room_name]
                        if rinfo.get('is_private') and rinfo.get('password'):
                            if password != rinfo['password']:
                                err = {'type': 'error', 'message': 'Sai mật khẩu phòng.'}
                                self.send_json(client_socket, err)
                                continue

                        self.add_client_to_room(client_socket, room_name)
                        ok = {
                            'type': 'room_joined',
                            'room': room_name,
                            'creator': rinfo['creator'],
                            'is_admin': (username == rinfo['creator'])
                        }
                        self.send_json(client_socket, ok)

                    # ---------- QTV: KICK ----------
                    elif msg_type == 'admin_kick':
                        room_name = data.get('room') or current_room
                        target_name = data.get('target')
                        if not target_name:
                            continue
                        if room_name not in self.rooms:
                            err = {'type': 'error', 'message': 'Phòng không tồn tại.'}
                            self.send_json(client_socket, err)
                            continue
                        rinfo = self.rooms[room_name]
                        if rinfo.get('creator') != username:
                            err = {'type': 'error',
                                   'message': 'Bạn không phải QTV của phòng này.'}
                            self.send_json(client_socket, err)
                            continue

                        target_socket = None
                        for sock, info2 in self.clients.items():
                            if info2.get('username') == target_name:
                                target_socket = sock
                                break
                        if not target_socket or target_socket not in rinfo['members']:
                            err = {'type': 'error',
                                   'message': f"{target_name} không ở trong phòng này."}
                            self.send_json(client_socket, err)
                            continue

                        # Gửi thông báo cho người bị kick
                        msg = (f"Bạn đã bị QTV {username} kick khỏi phòng {room_name}. "
                               f"Bạn sẽ quay về Phòng chung.")
                        notice = {
                            'type': 'admin_kicked',
                            'room': room_name,
                            'message': msg
                        }
                        self.send_json(target_socket, notice)

                        rinfo['members'].discard(target_socket)
                        self.clients[target_socket]['current_room'] = None

                        sys_msg = f"{username} (QTV) đã kick {target_name} khỏi phòng."
                        self.broadcast_room_message(room_name, "SERVER", sys_msg)
                        self.add_to_history("SERVER", sys_msg, room_name)

                        # Đưa về Phòng chung
                        self.add_client_to_room(target_socket, "Phòng chung")
                        rinfo_after = self.rooms["Phòng chung"]
                        ok2 = {
                            'type': 'room_joined',
                            'room': "Phòng chung",
                            'creator': rinfo_after['creator'],
                            'is_admin': False
                        }
                        self.send_json(target_socket, ok2)

                    # ---------- QTV: ĐỔI MẬT KHẨU ----------
                    elif msg_type == 'admin_change_password':
                        room_name = data.get('room') or current_room
                        new_password = data.get('new_password', '')
                        if room_name not in self.rooms:
                            err = {'type': 'error', 'message': 'Phòng không tồn tại.'}
                            self.send_json(client_socket, err)
                            continue
                        rinfo = self.rooms[room_name]
                        if rinfo.get('creator') != username:
                            err = {'type': 'error',
                                   'message': 'Bạn không phải QTV của phòng này.'}
                            self.send_json(client_socket, err)
                            continue

                        rinfo['password'] = new_password
                        rinfo['is_private'] = bool(new_password)
                        if new_password:
                            msg = f"{username} (QTV) đã cập nhật mật khẩu phòng."
                        else:
                            msg = f"{username} (QTV) đã gỡ mật khẩu phòng."
                        self.broadcast_room_message(room_name, "SERVER", msg)
                        self.add_to_history("SERVER", msg, room_name)
                        self.broadcast_room_list()

                    # ---------- QTV: ĐỔI TÊN PHÒNG ----------
                    elif msg_type == 'admin_rename_room':
                        old_name = data.get('room') or current_room
                        new_name = data.get('new_name', '').strip()
                        if not new_name:
                            err = {'type': 'error', 'message': 'Tên phòng mới không được để trống.'}
                            self.send_json(client_socket, err)
                            continue
                        if old_name == "Phòng chung":
                            err = {'type': 'error', 'message': 'Không thể đổi tên phòng chung.'}
                            self.send_json(client_socket, err)
                            continue
                        if old_name not in self.rooms:
                            err = {'type': 'error', 'message': 'Phòng không tồn tại.'}
                            self.send_json(client_socket, err)
                            continue
                        if new_name in self.rooms:
                            err = {'type': 'error',
                                   'message': 'Đã có phòng trùng tên, hãy chọn tên khác.'}
                            self.send_json(client_socket, err)
                            continue

                        rinfo = self.rooms[old_name]
                        if rinfo.get('creator') != username:
                            err = {'type': 'error',
                                   'message': 'Bạn không phải QTV của phòng này.'}
                            self.send_json(client_socket, err)
                            continue

                        # Đổi tên key phòng
                        self.rooms.pop(old_name)
                        self.rooms[new_name] = rinfo

                        # Cập nhật current_room cho các client trong phòng
                        for sock in rinfo['members']:
                            if sock in self.clients:
                                if self.clients[sock].get('current_room') == old_name:
                                    self.clients[sock]['current_room'] = new_name
                                    ok = {
                                        'type': 'room_joined',
                                        'room': new_name,
                                        'creator': rinfo['creator'],
                                        'is_admin': (self.clients[sock]['username'] ==
                                                     rinfo['creator'])
                                    }
                                    self.send_json(sock, ok)

                        sys_msg = (f"Phòng '{old_name}' đã được QTV {username} "
                                   f"đổi tên thành '{new_name}'.")
                        self.broadcast_room_message(new_name, "SERVER", sys_msg)
                        self.add_to_history("SERVER", sys_msg, new_name)
                        self.broadcast_room_list()

                    else:
                        err = {'type': 'error',
                               'message': f'Loại gói tin không hỗ trợ: {msg_type}'}
                        self.send_json(client_socket, err)

        except Exception as e:
            callback(f"[LỖI] {address}: {e}\n")
        finally:
            self.remove_client(client_socket)

    def stop_server(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

        for sock in list(self.clients.keys()):
            self.remove_client(sock)

        self.clients.clear()


# ----------------- GIAO DIỆN SERVER -----------------
class ServerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🖥️ TCP Chat Server")
        self.root.geometry("700x600")
        self.root.configure(bg='#1e1e1e')

        self.server = ChatServer()
        self.setup_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Segoe UI', 10), padding=10)
        style.configure('TLabel', background='#1e1e1e',
                        foreground='white', font=('Segoe UI', 10))

        header_frame = tk.Frame(self.root, bg='#0d7377', height=80)
        header_frame.pack(fill='x', pady=(0, 10))
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame,
            text="🖥️ Chat Server Dashboard (Rooms + PM + QTV)",
            bg='#0d7377',
            fg='white',
            font=('Segoe UI', 20, 'bold')
        )
        title_label.pack(expand=True)

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

        footer = tk.Label(
            self.root,
            text="TCP Chat Server | Lobby + Rooms (Public/Private) + PM + QTV | Port: 5555",
            bg='#1e1e1e',
            fg='#888',
            font=('Segoe UI', 8)
        )
        footer.pack(pady=5)

    def log(self, message):
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)

    def start_server(self):
        if self.server.start_server(self.log):
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.status_label.config(
                text="🟢 Trạng thái: Đang chạy",
                fg='#51cf66'
            )

    def stop_server(self):
        self.server.stop_server()
        self.log("[SERVER] Đã dừng server\n")
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(
            text="⚫ Trạng thái: Đã dừng",
            fg='#ff6b6b'
        )

    def clear_logs(self):
        self.log_text.delete(1.0, tk.END)

    def on_closing(self):
        if messagebox.askokcancel("Thoát", "Bạn có chắc muốn thoát?"):
            self.server.stop_server()
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ServerGUI()
    app.run()
