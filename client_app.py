import socket
import threading
import json
import base64
from datetime import datetime
from io import BytesIO

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, filedialog

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from login_ui import LoginDialog


# ======================= LỚP CHATCLIENT (KẾT NỐI TCP) =======================

class ChatClient:
    """
    Chịu trách nhiệm kết nối server, gửi/nhận gói JSON (NDJSON).
    Không dính Tkinter để dễ tách code.
    """

    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.client_socket = None
        self.username = None
        self.connected = False
        self.receive_thread = None

        # callback để GUI gán vào
        self.message_callback = None    # log text
        self.user_list_callback = None
        self.room_list_callback = None
        self.room_joined_callback = None
        self.image_callback = None      # nhận ảnh

        self.current_avatar = None

    # ------------- HÀM TIỆN ÍCH -------------
    def send_packet(self, data: dict) -> bool:
        if not self.connected or not self.client_socket:
            return False
        try:
            payload = json.dumps(data) + "\n"
            self.client_socket.sendall(payload.encode('utf-8'))
            return True
        except Exception as e:
            print("Lỗi send_packet:", e)
            return False

    # ------------- KẾT NỐI / NGẮT KẾT NỐI -------------
    def connect(self, username, password, action, callback) -> bool:
        """
        action: 'login' hoặc 'register'
        callback: hàm GUI dùng để log message hệ thống.
        """
        try:
            self.username = username
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))

            # Gửi gói auth đầu tiên
            auth_packet = {
                "type": "auth",
                "action": action,
                "username": username,
                "password": password
            }
            payload = json.dumps(auth_packet) + "\n"
            self.client_socket.sendall(payload.encode('utf-8'))

            # Chờ phản hồi auth
            resp = self.client_socket.recv(4096).decode('utf-8').strip()
            data = json.loads(resp)

            if data.get("type") == "error":
                callback(f"[LỖI] {data.get('message')}\n", "error")
                self.client_socket.close()
                self.client_socket = None
                return False

            if data.get("type") != "auth_ok":
                callback("[LỖI] Phản hồi đăng nhập không hợp lệ từ server.\n", "error")
                self.client_socket.close()
                self.client_socket = None
                return False

            self.current_avatar = data.get("avatar")
            self.connected = True

            # Bắt đầu thread nhận tin
            self.receive_thread = threading.Thread(
                target=self.receive_loop,
                daemon=True
            )
            self.receive_thread.start()

            return True

        except Exception as e:
            callback(f"[LỖI] Không thể kết nối server: {e}\n", "error")
            return False

    def disconnect(self):
        self.connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        self.client_socket = None

    # ------------- NHẬN TIN -------------
    def receive_loop(self):
        buffer = ""
        while self.connected:
            try:
                chunk = self.client_socket.recv(4096).decode('utf-8')
                if not chunk:
                    # server đóng
                    if self.message_callback:
                        self.message_callback("[SYSTEM] Mất kết nối tới server.\n",
                                              "error")
                    self.connected = False
                    break
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self.handle_packet(data)
            except Exception as e:
                print("receive_loop error:", e)
                if self.connected and self.message_callback:
                    self.message_callback("[SYSTEM] Lỗi kết nối tới server.\n",
                                          "error")
                self.connected = False
                break

    def handle_packet(self, data: dict):
        msg_type = data.get("type")

        # text log chung
        def log(txt, tag="system"):
            if self.message_callback:
                self.message_callback(txt, tag)

        if msg_type == "chat":
            sender = data.get("sender", "???")
            room = data.get("room", "Phòng chung")
            message = data.get("message", "")
            timestamp = data.get("timestamp") or datetime.now().strftime("%H:%M:%S")

            if sender == "SERVER":
                line = f"[{timestamp}] 🔔 ({room}) {message}\n"
                log(line, "server")
            elif sender == self.username:
                line = f"[{timestamp}] ({room}) Bạn: {message}\n"
                log(line, "self")
            else:
                line = f"[{timestamp}] ({room}) {sender}: {message}\n"
                log(line, "other")

        elif msg_type == "private":
            sender = data.get("sender", "???")
            recipient = data.get("recipient", "???")
            message = data.get("message", "")
            timestamp = data.get("timestamp") or datetime.now().strftime("%H:%M:%S")

            if sender == self.username:
                line = f"[{timestamp}] [PM tới {recipient}] {message}\n"
                log(line, "self")
            else:
                line = f"[{timestamp}] [PM từ {sender}] {message}\n"
                log(line, "pm")

        elif msg_type == "user_list":
            users = data.get("users", [])
            if self.user_list_callback:
                self.user_list_callback(users)

        elif msg_type == "room_list":
            rooms = data.get("rooms", [])
            if self.room_list_callback:
                self.room_list_callback(rooms)

        elif msg_type == "room_joined":
            room = data.get("room")
            creator = data.get("creator")
            is_admin = data.get("is_admin", False)
            if self.room_joined_callback:
                self.room_joined_callback(room, creator, is_admin)

        elif msg_type == "error":
            msg = data.get("message", "Lỗi không xác định.")
            log(f"[LỖI] {msg}\n", "error")

        elif msg_type == "history":
            room = data.get("room", "Phòng chung")
            entries = data.get("history", [])
            log(f"===== Lịch sử phòng {room} =====\n", "system")
            for e in entries:
                ts = e.get("timestamp", "")
                u = e.get("username", "")
                m = e.get("message", "")
                log(f"[{ts}] {u}: {m}\n", "history")
            log("===== Hết lịch sử =====\n", "system")

        elif msg_type == "avatar_updated":
            msg = data.get("message", "Avatar đã cập nhật.")
            log(f"[SYSTEM] {msg}\n", "system")

        elif msg_type == "image":
            # tin nhắn ảnh
            if self.message_callback:
                sender = data.get("sender", "???")
                room = data.get("room", "Phòng chung")
                filename = data.get("filename", "image")
                caption = data.get("caption", "")
                timestamp = data.get("timestamp") or datetime.now().strftime(
                    "%H:%M:%S")

                base_line = f"[{timestamp}] ({room}) "
                if sender == self.username:
                    base_line += f"Bạn gửi ảnh: {filename}"
                    tag = "self"
                else:
                    base_line += f"{sender} gửi ảnh: {filename}"
                    tag = "other"

                if caption:
                    base_line += f" - {caption}"
                base_line += "\n"
                self.message_callback(base_line, tag)

            if self.image_callback:
                self.image_callback(data)

    # ------------- GỬI TIN NHẮN -------------
    def send_chat(self, message: str, room: str = None):
        data = {
            "type": "chat",
            "message": message
        }
        if room:
            data["room"] = room
        return self.send_packet(data)

    def send_private(self, target: str, message: str):
        data = {
            "type": "private",
            "to": target,
            "message": message
        }
        return self.send_packet(data)

    def request_history(self, room: str):
        data = {
            "type": "get_history",
            "room": room
        }
        return self.send_packet(data)

    # phòng + QTV giữ lại từ server cũ (nếu bạn muốn dùng)
    def create_room(self, room_name: str, password: str = ""):
        data = {
            "type": "create_room",
            "room": room_name,
            "password": password
        }
        return self.send_packet(data)

    def join_room(self, room_name: str, password: str = ""):
        data = {
            "type": "join_room",
            "room": room_name,
            "password": password
        }
        return self.send_packet(data)

    def admin_kick(self, room: str, target: str):
        data = {
            "type": "admin_kick",
            "room": room,
            "target": target
        }
        return self.send_packet(data)

    def admin_ban(self, room: str, target: str):
        data = {
            "type": "admin_ban",
            "room": room,
            "target": target
        }
        return self.send_packet(data)

    def admin_unban(self, room: str, target: str):
        data = {
            "type": "admin_unban",
            "room": room,
            "target": target
        }
        return self.send_packet(data)

    def admin_change_password(self, room: str, new_password: str):
        data = {
            "type": "admin_change_password",
            "room": room,
            "new_password": new_password
        }
        return self.send_packet(data)

    # ------------- AVATAR + ẢNH -------------
    def update_avatar(self, image_b64: str):
        data = {
            "type": "update_avatar",
            "image_data": image_b64
        }
        return self.send_packet(data)

    def send_image(self, image_b64: str, filename: str,
                   caption: str = "", room: str = None):
        data = {
            "type": "image",
            "image_data": image_b64,
            "filename": filename,
            "caption": caption
        }
        if room:
            data["room"] = room
        return self.send_packet(data)


# ======================= CỬA SỔ PM RIÊNG =======================

class PrivateChatWindow:
    def __init__(self, parent_gui, target_username):
        self.parent_gui = parent_gui
        self.target = target_username

        self.win = tk.Toplevel(parent_gui.root)
        self.win.title(f"Chat với {target_username}")

        self.win.geometry("450x500")
        self.win.configure(bg="#f5f5f5")

        top = tk.Frame(self.win, bg="#6c5ce7", height=60)
        top.pack(fill="x")
        top.pack_propagate(False)

        lbl = tk.Label(
            top,
            text=f"💬 Đoạn chat với {target_username}",
            bg="#6c5ce7",
            fg="white",
            font=("Segoe UI", 12, "bold")
        )
        lbl.pack(side="left", padx=10, pady=10)

        close_btn = tk.Button(
            top,
            text="✕",
            command=self.on_close,
            bg="#6c5ce7",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2"
        )
        close_btn.pack(side="right", padx=10, pady=10)

        self.text = scrolledtext.ScrolledText(
            self.win,
            wrap="word",
            bg="white",
            fg="#2d3436",
            font=("Segoe UI", 10)
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(5, 5))
        self.text.config(state="disabled")

        bottom = tk.Frame(self.win, bg="#f5f5f5")
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.entry = tk.Entry(
            bottom,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self.send())

        send_btn = tk.Button(
            bottom,
            text="Gửi",
            command=self.send,
            bg="#6c5ce7",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=16,
            cursor="hand2"
        )
        send_btn.pack(side="right")

        self.win.protocol("WM_DELETE_WINDOW", self.on_close)

    def append(self, text: str):
        self.text.config(state="normal")
        self.text.insert("end", text)
        self.text.see("end")
        self.text.config(state="disabled")

    def send(self):
        msg = self.entry.get().strip()
        if not msg:
            return
        if self.parent_gui.client.send_private(self.target, msg):
            ts = datetime.now().strftime("%H:%M:%S")
            self.append(f"[{ts}] Bạn: {msg}\n")
            self.entry.delete(0, "end")

    def on_close(self):
        self.parent_gui.pm_windows.pop(self.target, None)
        self.win.destroy()


# ======================= GIAO DIỆN CHÍNH CLIENT =======================

class ClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🐱 Chat Client")
        self.root.geometry("1000x650")
        self.root.configure(bg="#f1f2f6")

        self.client = ChatClient()
        self.client.message_callback = self.display_message
        self.client.user_list_callback = self.update_user_list
        self.client.room_list_callback = self.update_room_list
        self.client.room_joined_callback = self.on_room_joined
        self.client.image_callback = self.on_image_received

        self.current_room = "Phòng chung"
        self.is_admin_current_room = False

        self.pm_windows = {}  # username -> PrivateChatWindow

        self._avatar_img = None

        self.setup_ui()

        # sau khi dựng UI thì mở login
        self.root.after(200, self.show_login)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------- UI CHÍNH -------------
    def setup_ui(self):
        # top bar
        top = tk.Frame(self.root, bg="#6c5ce7", height=60)
        top.pack(fill="x")
        top.pack_propagate(False)

        self.lbl_user = tk.Label(
            top,
            text="Chưa đăng nhập",
            bg="#6c5ce7",
            fg="white",
            font=("Segoe UI", 11, "bold")
        )
        self.lbl_user.pack(side="left", padx=10)

        self.lbl_status = tk.Label(
            top,
            text="🔴 Offline",
            bg="#6c5ce7",
            fg="#ffeaa7",
            font=("Segoe UI", 10)
        )
        self.lbl_status.pack(side="left", padx=10)

        self.avatar_label = tk.Label(top, bg="#6c5ce7")
        self.avatar_label.pack(side="right", padx=10, pady=5)

        avatar_btn = tk.Button(
            top,
            text="🖼 Avatar",
            command=self.change_avatar,
            bg="#8e44ad",
            fg="white",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        )
        avatar_btn.pack(side="right", padx=5)

        # main body: left = user/room list, right = chat
        body = tk.Frame(self.root, bg="#f1f2f6")
        body.pack(fill="both", expand=True)

        # left panel
        left = tk.Frame(body, bg="#dfe6e9", width=220)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tab_control = ttk.Notebook(left)
        tab_control.pack(fill="both", expand=True, padx=5, pady=5)

        self.user_tab = tk.Frame(tab_control, bg="#dfe6e9")
        self.room_tab = tk.Frame(tab_control, bg="#dfe6e9")
        tab_control.add(self.user_tab, text="Bạn bè")
        tab_control.add(self.room_tab, text="Phòng")

        # user list
        self.user_listbox = tk.Listbox(
            self.user_tab,
            bg="white",
            fg="#2d3436",
            font=("Segoe UI", 10),
            activestyle="none"
        )
        self.user_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.user_listbox.bind("<Double-Button-1>", self.open_private_chat)

        # room list
        self.room_listbox = tk.Listbox(
            self.room_tab,
            bg="white",
            fg="#2d3436",
            font=("Segoe UI", 10),
            activestyle="none"
        )
        self.room_listbox.pack(fill="both", expand=True, padx=5, pady=(5, 0))
        self.room_listbox.bind("<Double-Button-1>", self.join_selected_room)

        room_btns = tk.Frame(self.room_tab, bg="#dfe6e9")
        room_btns.pack(fill="x", padx=5, pady=5)

        tk.Button(
            room_btns,
            text="Tạo phòng",
            command=self.create_room_dialog,
            bg="#6c5ce7",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2"
        ).pack(side="left", padx=2)

        tk.Button(
            room_btns,
            text="Vào phòng",
            command=self.join_selected_room,
            bg="#00cec9",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2"
        ).pack(side="left", padx=2)

        # right panel = chat area
        right = tk.Frame(body, bg="#f1f2f6")
        right.pack(side="left", fill="both", expand=True)

        # chat header
        header = tk.Frame(right, bg="#f1f2f6", height=40)
        header.pack(fill="x")
        header.pack_propagate(False)

        self.room_label = tk.Label(
            header,
            text="Phòng: Phòng chung",
            bg="#f1f2f6",
            fg="#2d3436",
            font=("Segoe UI", 11, "bold")
        )
        self.room_label.pack(side="left", padx=10, pady=10)

        self.admin_label = tk.Label(
            header,
            text="",
            bg="#f1f2f6",
            fg="#e74c3c",
            font=("Segoe UI", 10, "bold")
        )
        self.admin_label.pack(side="right", padx=10)

        # chat display
        self.chat_display = scrolledtext.ScrolledText(
            right,
            wrap="word",
            bg="white",
            fg="#2d3436",
            font=("Segoe UI", 10)
        )
        self.chat_display.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.chat_display.config(state="disabled")

        # bottom input
        bottom = tk.Frame(right, bg="#f1f2f6")
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.message_entry = tk.Entry(
            bottom,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1
        )
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 5),
                                pady=2)
        self.message_entry.bind("<Return>", lambda e: self.send_message())

        send_btn = tk.Button(
            bottom,
            text="Gửi",
            command=self.send_message,
            bg="#6c5ce7",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=18,
            cursor="hand2"
        )
        send_btn.pack(side="right", padx=(5, 0))

        img_btn = tk.Button(
            bottom,
            text="📷",
            command=self.send_image,
            bg="#00cec9",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=10,
            cursor="hand2"
        )
        img_btn.pack(side="right", padx=(5, 0))

        hist_btn = tk.Button(
            bottom,
            text="Lịch sử",
            command=self.request_history,
            bg="#b2bec3",
            fg="#2d3436",
            font=("Segoe UI", 9),
            relief="flat",
            padx=10,
            cursor="hand2"
        )
        hist_btn.pack(side="right", padx=(5, 0))

    # ------------- LOGIN -------------
    def show_login(self):
        dlg = LoginDialog(self.root)
        info = dlg.show()
        if not info:
            self.root.destroy()
            return

        username = info["username"]
        password = info["password"]
        action = info["action"]

        ok = self.client.connect(username, password, action, self.display_message)
        if not ok:
            # nếu fail thì mở lại login
            self.root.after(200, self.show_login)
            return

        self.lbl_user.config(text=f"{username}")
        self.lbl_status.config(text="🟢 Online", fg="#2ecc71")
        self.current_room = "Phòng chung"
        self.room_label.config(text="Phòng: Phòng chung")

        if self.client.current_avatar:
            self.set_avatar_from_b64(self.client.current_avatar)

        self.display_message(
            f"[SYSTEM] Đã đăng nhập thành công, vào Phòng chung.\n",
            "system"
        )

    # ------------- AVATAR -------------
    def set_avatar_from_b64(self, avatar_b64: str):
        if not PIL_AVAILABLE or not avatar_b64:
            return
        try:
            raw = base64.b64decode(avatar_b64)
            img = Image.open(BytesIO(raw))
            img = img.resize((48, 48))
            tk_img = ImageTk.PhotoImage(img)
            self._avatar_img = tk_img
            self.avatar_label.config(image=tk_img)
        except Exception as e:
            print("set_avatar_from_b64 error:", e)

    def change_avatar(self):
        if not PIL_AVAILABLE:
            messagebox.showerror("Thiếu thư viện", "Cần cài pillow: pip install pillow")
            return
        if not self.client.connected:
            messagebox.showwarning("Avatar", "Bạn chưa đăng nhập.")
            return

        file_path = filedialog.askopenfilename(
            title="Chọn ảnh đại diện",
            filetypes=[("Ảnh", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"),
                       ("Tất cả", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {e}")
            return

        if self.client.update_avatar(b64):
            self.set_avatar_from_b64(b64)
            messagebox.showinfo("Avatar", "Đã gửi avatar lên server.")

    # ------------- GỬI / NHẬN TIN -------------
    def display_message(self, text: str, tag: str = "system"):
        self.chat_display.config(state="normal")
        self.chat_display.insert("end", text)
        self.chat_display.see("end")
        self.chat_display.config(state="disabled")

    def send_message(self):
        msg = self.message_entry.get().strip()
        if not msg:
            return
        if not self.client.connected:
            messagebox.showwarning("Chat", "Bạn chưa đăng nhập.")
            return

        if self.client.send_chat(msg, self.current_room):
            self.message_entry.delete(0, "end")

    def send_image(self):
        if not PIL_AVAILABLE:
            messagebox.showerror("Thiếu thư viện", "Cần cài pillow: pip install pillow")
            return
        if not self.client.connected:
            messagebox.showwarning("Chat", "Bạn chưa đăng nhập.")
            return

        file_path = filedialog.askopenfilename(
            title="Chọn ảnh để gửi",
            filetypes=[("Ảnh", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"),
                       ("Tất cả", "*.*")]
        )
        if not file_path:
            return

        caption = simpledialog.askstring(
            "Chú thích",
            "Nhập chú thích (không bắt buộc):",
            parent=self.root
        ) or ""

        try:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {e}")
            return

        filename = file_path.split("/")[-1]
        if not self.client.send_image(b64, filename, caption, self.current_room):
            messagebox.showerror("Lỗi", "Không thể gửi ảnh.")

    def on_image_received(self, data: dict):
        if not PIL_AVAILABLE:
            return

        img_b64 = data.get("image_data")
        filename = data.get("filename", "image")
        sender = data.get("sender", "???")

        try:
            raw = base64.b64decode(img_b64)
            img = Image.open(BytesIO(raw))
        except Exception as e:
            print("on_image_received decode error:", e)
            return

        # thu nhỏ nếu quá to
        max_size = (800, 600)
        img.thumbnail(max_size)

        tk_img = ImageTk.PhotoImage(img)

        # giữ tham chiếu
        if not hasattr(self, "_img_cache"):
            self._img_cache = []
        self._img_cache.append(tk_img)

        win = tk.Toplevel(self.root)
        win.title(f"Ảnh từ {sender}: {filename}")
        lbl = tk.Label(win, image=tk_img, bg="black")
        lbl.pack(fill="both", expand=True)

        win.geometry("600x400")

    # ------------- USER / ROOM LIST -------------
    def update_user_list(self, users):
        self.user_listbox.delete(0, "end")
        for u in users:
            self.user_listbox.insert("end", u)

    def update_room_list(self, rooms):
        self.room_listbox.delete(0, "end")
        for r in rooms:
            self.room_listbox.insert("end", r)

    def on_room_joined(self, room, creator, is_admin):
        self.current_room = room
        self.room_label.config(text=f"Phòng: {room}")
        self.is_admin_current_room = is_admin
        if is_admin:
            self.admin_label.config(text="QTV")
        else:
            self.admin_label.config(text="")

        self.display_message(f"[SYSTEM] Đã vào phòng {room}.\n", "system")

    def open_private_chat(self, event=None):
        selection = self.user_listbox.curselection()
        if not selection:
            return
        target = self.user_listbox.get(selection[0])
        if target == self.client.username:
            return

        win = self.pm_windows.get(target)
        if not win:
            win = PrivateChatWindow(self, target)
            self.pm_windows[target] = win
        win.win.deiconify()
        win.win.lift()

    def join_selected_room(self, event=None):
        selection = self.room_listbox.curselection()
        if not selection:
            return
        room = self.room_listbox.get(selection[0])
        if room == self.current_room:
            return
        password = simpledialog.askstring(
            "Mật khẩu",
            "Nhập mật khẩu phòng (nếu có):",
            show="*"
        )
        if password is None:
            password = ""
        self.client.join_room(room, password)

    def create_room_dialog(self):
        name = simpledialog.askstring("Tạo phòng", "Tên phòng:", parent=self.root)
        if not name:
            return
        password = simpledialog.askstring(
            "Mật khẩu",
            "Đặt mật khẩu (trống nếu phòng công khai):",
            parent=self.root,
            show="*"
        )
        if password is None:
            password = ""
        self.client.create_room(name, password)

    def request_history(self):
        if not self.client.connected:
            return
        self.client.request_history(self.current_room)

    # ------------- ĐÓNG APP -------------
    def on_close(self):
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
