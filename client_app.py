import socket
import threading
import json
from datetime import datetime
import base64
import os

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext

from login_ui import LoginDialog
# ================== BACKEND CLIENT ==================
class ChatClient:
    """
    Client TCP nói chuyện với server bằng JSON (NDJSON).
    Không phụ thuộc Tkinter, chỉ gọi callback cho GUI.
    """

    def __init__(self, host="127.0.0.1", port=5555):
        self.host = host
        self.port = port

        self.client_socket = None
        self.username = None
        self.connected = False
        self.receive_thread = None

        # callback cho GUI gán vào
        self.message_callback = None        # (text, tag)
        self.user_list_callback = None      # (users)
        self.room_list_callback = None      # (rooms)
        self.room_joined_callback = None    # (room, creator, is_admin)
        self.image_callback = None          # (data)
        self.chat_event_callback = None     # (kind, name, preview, is_outgoing)
        self.history_callback = None        # (room, entries)


    # ---------- tiện ích ----------
    def send_packet(self, data: dict) -> bool:
        if not self.connected or not self.client_socket:
            return False
        try:
            payload = json.dumps(data) + "\n"
            self.client_socket.sendall(payload.encode("utf-8"))
            return True
        except Exception as e:
            print("send_packet error:", e)
            return False

    # ---------- kết nối / đăng nhập ----------
    def connect(self, username: str, password: str, action: str, log_cb) -> bool:
        """
        action: 'login' hoặc 'register'
        log_cb: hàm hiển thị log (GUI dùng display_message)
        """
        try:
            self.username = username
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))

            auth_packet = {
                "type": "auth",
                "action": action,
                "username": username,
                "password": password,
            }
            payload = json.dumps(auth_packet) + "\n"
            self.client_socket.sendall(payload.encode("utf-8"))

            # đọc 1 dòng đầu tiên (auth_ok hoặc error)
            buffer = ""
            while True:
                chunk = self.client_socket.recv(4096).decode("utf-8")
                if not chunk:
                    log_cb("[LỖI] Mất kết nối khi chờ phản hồi đăng nhập.\n", "error")
                    self.client_socket.close()
                    self.client_socket = None
                    return False
                buffer += chunk
                if "\n" in buffer:
                    line, rest = buffer.split("\n", 1)
                    line = line.strip()
                    break

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                log_cb(f"[LỖI] Phản hồi đăng nhập không hợp lệ: {e}\n", "error")
                self.client_socket.close()
                self.client_socket = None
                return False

            if data.get("type") == "error":
                log_cb(f"[LỖI] {data.get('message')}\n", "error")
                self.client_socket.close()
                self.client_socket = None
                return False

            if data.get("type") != "auth_ok":
                log_cb("[LỖI] Phản hồi đăng nhập không hợp lệ từ server.\n", "error")
                self.client_socket.close()
                self.client_socket = None
                return False

            # ok
            self.connected = True

            self.receive_thread = threading.Thread(
                target=self.receive_loop,
                args=(rest,),
                daemon=True,
            )
            self.receive_thread.start()
            return True

        except Exception as e:
            log_cb(f"[LỖI] Không thể kết nối server: {e}\n", "error")
            if self.client_socket:
                try:
                    self.client_socket.close()
                except Exception:
                    pass
            self.client_socket = None
            return False

    def disconnect(self):
        self.connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        self.client_socket = None

    # ---------- nhận dữ liệu ----------
    def receive_loop(self, initial_buffer: str = ""):
        buffer = initial_buffer or ""
        while self.connected:
            try:
                # xử lý các dòng đã có trong buffer
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

                # đọc thêm
                chunk = self.client_socket.recv(4096).decode("utf-8")
                if not chunk:
                    if self.message_callback:
                        self.message_callback(
                            "[SYSTEM] Mất kết nối tới server.\n", "error"
                        )
                    self.connected = False
                    break
                buffer += chunk

            except Exception as e:
                print("receive_loop error:", e)
                if self.connected and self.message_callback:
                    self.message_callback(
                        "[SYSTEM] Lỗi kết nối tới server.\n", "error"
                    )
                self.connected = False
                break

    def handle_packet(self, data: dict):
        msg_type = data.get("type")

        def log(txt, tag="system"):
            if self.message_callback:
                self.message_callback(txt, tag)

        # --- chat phòng ---
        if msg_type == "chat":
            sender = data.get("sender", "???")
            room = data.get("room", "Phòng chung")
            message = data.get("message", "")
            timestamp = data.get("timestamp") or datetime.now().strftime("%H:%M:%S")

            if sender == "SERVER":
                line = f"[{timestamp}] 🔔 ({room}) {message}\n"
                tag = "server"
            elif sender == self.username:
                line = f"[{timestamp}] ({room}) Bạn: {message}\n"
                tag = "self"
            else:
                line = f"[{timestamp}] ({room}) {sender}: {message}\n"
                tag = "other"
            log(line, tag)

            if self.chat_event_callback:
                self.chat_event_callback("room", room, message, sender == self.username)

        # --- PM ---
        elif msg_type == "private":
            sender = data.get("sender", "???")
            recipient = data.get("recipient", "???")
            message = data.get("message", "")
            timestamp = data.get("timestamp") or datetime.now().strftime("%H:%M:%S")

            if sender == self.username:
                line = f"[{timestamp}] [PM tới {recipient}] {message}\n"
                tag = "self"
                partner = recipient
                is_outgoing = True
            else:
                line = f"[{timestamp}] [PM từ {sender}] {message}\n"
                tag = "pm"
                partner = sender
                is_outgoing = False
            log(line, tag)

            if self.chat_event_callback:
                self.chat_event_callback("pm", partner, message, is_outgoing)

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

        elif msg_type == "admin_kicked":
            msg = data.get("message", "")
            log(f"[SYSTEM] {msg}\n", "error")
            messagebox.showwarning("Bị kick khỏi phòng", msg)

        elif msg_type == "error":
            msg = data.get("message", "Lỗi không xác định.")
            log(f"[LỖI] {msg}\n", "error")

        elif msg_type == "history":
            room = data.get("room", "Phòng chung")
            entries = data.get("history") or data.get("data") or []
            # nếu GUI có đăng ký history_callback thì giao cho GUI vẽ lại
            if self.history_callback:
                self.history_callback(room, entries)
            else:
                # fallback cũ – chỉ in text thô
                log(f"===== Lịch sử phòng {room} =====\n", "system")
                for e in entries:
                    ts = e.get("timestamp", "")
                    u = e.get("username", "")
                    m = e.get("message", "")
                    log(f"[{ts}] {u}: {m}\n", "history")
                log("===== Hết lịch sử =====\n", "system")


        elif msg_type == "image":
            sender = data.get("sender", "???")
            room = data.get("room", "Phòng chung")
            filename = data.get("filename", "image")
            caption = data.get("caption", "")
            timestamp = data.get("timestamp") or datetime.now().strftime("%H:%M:%S")

            base_line = f"[{timestamp}] ({room}) "
            if sender == self.username:
                base_line += f"Bạn gửi ảnh: {filename}"
                tag = "self"
                is_outgoing = True
            else:
                base_line += f"{sender} gửi ảnh: {filename}"
                tag = "other"
                is_outgoing = False
            if caption:
                base_line += f" - {caption}"
            base_line += "\n"
            log(base_line, tag)

            if self.chat_event_callback:
                preview = f"[Ảnh] {filename}"
                if caption:
                    preview += f" - {caption}"
                self.chat_event_callback("room", room, preview, is_outgoing)

            if self.image_callback:
                self.image_callback(data)

    # ---------- gửi tiện lợi ----------
    def send_chat(self, message: str, room: str = None):
        # server chỉ dùng room hiện tại trong session,
        # nhưng ta vẫn gửi thêm room cho rõ ràng
        data = {"type": "chat", "message": message}
        if room:
            data["room"] = room
        return self.send_packet(data)

    def send_private(self, target: str, message: str):
        data = {"type": "private", "to": target, "message": message}
        return self.send_packet(data)

    def request_history(self, room: str):
        data = {"type": "get_history", "room": room}
        return self.send_packet(data)

    def create_room(self, room_name: str, password: str = ""):
        # ĐÃ SỬA: gửi đúng key "room" để server nhận
        data = {
            "type": "create_room",
            "room": room_name,
            "password": password or "",
        }
        return self.send_packet(data)

    def join_room(self, room_name: str, password: str = ""):
        # ĐÃ SỬA: gửi đúng key "room"
        data = {
            "type": "join_room",
            "room": room_name,
            "password": password or "",
        }
        return self.send_packet(data)

    # --- QTV helper ---
    def admin_kick(self, room: str, target: str):
        data = {"type": "admin_kick", "room": room, "target": target}
        return self.send_packet(data)

    def admin_change_password(self, room: str, new_password: str):
        data = {
            "type": "admin_change_password",
            "room": room,
            "new_password": new_password,
        }
        return self.send_packet(data)

    def admin_rename_room(self, room: str, new_name: str):
        data = {"type": "admin_rename_room", "room": room, "new_name": new_name}
        return self.send_packet(data)


# ================== MESSENGER STYLE UI ==================
class ClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cute Chat")
        self.root.geometry("1100x650")
        self.root.configure(bg="#dfe3ee")

        self.client = ChatClient()

        # state hiện tại
        self.current_room = "Phòng chung"
        self.current_room_creator = None
        self.current_is_admin = False

        self.build_layout()
        self.do_login()

    # ---------- UI ----------
    def build_layout(self):
        # Layout 3 cột: sidebar trái, khu chat giữa, info phải
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_columnconfigure(2, weight=0)

        # ========== LEFT: ROOM & USER ==========
        left = tk.Frame(self.root, bg="#f0f2f5", width=260, bd=0, highlightthickness=0)
        left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False)

        top_bar = tk.Frame(left, bg="#ffffff", height=50)
        top_bar.pack(fill="x")
        tk.Label(
            top_bar,
            text="  ✉ Chat App",
            bg="#ffffff",
            fg="#111",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=10, pady=10)

        create_btn = tk.Button(
            left,
            text="+ Tạo phòng",
            command=self.create_room_dialog,
            bg="#9b59b6",
            fg="white",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=4,
        )
        create_btn.pack(fill="x", padx=12, pady=(8, 6))

        # danh sách phòng
        room_lbl = tk.Label(
            left,
            text="Phòng chat",
            bg="#f0f2f5",
            fg="#555",
            font=("Segoe UI", 9, "bold"),
        )
        room_lbl.pack(anchor="w", padx=14, pady=(4, 2))

        self.room_list = tk.Listbox(
            left,
            bg="#ffffff",
            fg="#111",
            bd=0,
            highlightthickness=0,
            activestyle="dotbox",
            font=("Segoe UI", 9),
            height=8,
        )
        self.room_list.pack(fill="x", padx=12)
        self.room_list.bind("<<ListboxSelect>>", self.on_room_click)

        # danh sách user
        user_lbl = tk.Label(
            left,
            text="Người online",
            bg="#f0f2f5",
            fg="#555",
            font=("Segoe UI", 9, "bold"),
        )
        user_lbl.pack(anchor="w", padx=14, pady=(8, 2))

        self.user_list = tk.Listbox(
            left,
            bg="#ffffff",
            fg="#111",
            bd=0,
            highlightthickness=0,
            activestyle="dotbox",
            font=("Segoe UI", 9),
        )
        self.user_list.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.user_list.bind("<Double-Button-1>", self.start_private_chat)

        # ========== CENTER: CHAT AREA ==========
        center = tk.Frame(self.root, bg="#dfe3ee")
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # header
        header = tk.Frame(center, bg="#ffffff", height=52)
        header.grid(row=0, column=0, sticky="new")
        header.grid_propagate(False)

        self.username_label = tk.Label(
            header,
            text="Chưa đăng nhập",
            bg="#ffffff",
            fg="#111",
            font=("Segoe UI", 11, "bold"),
        )
        self.username_label.pack(side="left", padx=12)

        self.roomname_label = tk.Label(
            header,
            text="Phòng: Phòng chung",
            bg="#ffffff",
            fg="#555",
            font=("Segoe UI", 9),
        )
        self.roomname_label.pack(side="left", padx=10)

        self.admin_label = tk.Label(
            header,
            text="",
            bg="#ffffff",
            fg="#e67e22",
            font=("Segoe UI", 9, "bold"),
        )
        self.admin_label.pack(side="left", padx=4)

        self.manage_btn = tk.Button(
            header,
            text="⚙ QTV",
            command=self.open_room_admin_menu,
            bg="#ecf0f1",
            fg="#111",
            relief="flat",
            font=("Segoe UI", 8),
        )
        self.manage_btn.pack(side="right", padx=8)
        self.manage_btn.config(state="disabled")

        # khung chat (dạng text + bubble màu)
        chat_frame = tk.Frame(center, bg="#dfe3ee")
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_text = scrolledtext.ScrolledText(
            chat_frame,
            wrap="word",
            bg="#dfe3ee",
            fg="#111",
            insertbackground="#111",
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=0,
        )
        self.chat_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.chat_text.config(state="disabled")

        # style "bubble"
        self.chat_text.tag_config("self", foreground="#ffffff", background="#9b59b6",
                                  spacing1=4, spacing3=4, lmargin1=200, lmargin2=200,
                                  rmargin=8, justify="right")
        self.chat_text.tag_config("other", foreground="#111", background="#ffffff",
                                  spacing1=4, spacing3=4, lmargin1=8, lmargin2=8,
                                  rmargin=200, justify="left")
        self.chat_text.tag_config("server", foreground="#2c3e50", background="#f9e79f",
                                  spacing1=4, spacing3=4, lmargin1=60, lmargin2=60,
                                  rmargin=60, justify="center")
        self.chat_text.tag_config("pm", foreground="#ffffff", background="#e84393",
                                  spacing1=4, spacing3=4, lmargin1=120, lmargin2=120,
                                  rmargin=120, justify="center")
        self.chat_text.tag_config("error", foreground="#c0392b")
        self.chat_text.tag_config("system", foreground="#7f8c8d")
        self.chat_text.tag_config("history", foreground="#2980b9")

        # input
        input_frame = tk.Frame(center, bg="#ffffff", height=70)
        input_frame.grid(row=2, column=0, sticky="sew")
        input_frame.grid_propagate(False)
        input_frame.grid_columnconfigure(0, weight=1)

        self.message_entry = tk.Entry(
            input_frame,
            bg="#f0f2f5",
            fg="#111",
            font=("Segoe UI", 11),
            relief="flat",
            insertbackground="#111",
        )
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=14)
        self.message_entry.bind("<Return>", self.send_message)

        send_btn = tk.Button(
            input_frame,
            text="Gửi",
            command=self.send_message,
            bg="#9b59b6",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=14,
        )
        send_btn.grid(row=0, column=1, padx=(0, 4), pady=14)

        img_btn = tk.Button(
            input_frame,
            text="📎",
            command=self.send_image,
            bg="#ecf0f1",
            fg="#111",
            relief="flat",
            font=("Segoe UI", 11),
            width=3,
        )
        img_btn.grid(row=0, column=2, padx=(0, 10), pady=14)

        # ========== RIGHT: INFO PANEL (avatar + welcome) ==========
        right = tk.Frame(self.root, bg="#f0f2f5", width=220)
        right.grid(row=0, column=2, sticky="nse")
        right.grid_propagate(False)

        # avatar tròn đơn giản (dùng emoji mèo)
        avatar_frame = tk.Frame(right, bg="#f0f2f5")
        avatar_frame.pack(pady=(40, 10), fill="x")
        avatar_label = tk.Label(
            avatar_frame,
            text="😺",
            bg="#9b59b6",
            fg="white",
            font=("Segoe UI", 36, "bold"),
            width=4,
            height=2,
        )
        avatar_label.pack()

        self.welcome_label = tk.Label(
            right,
            text="Welcome!",
            bg="#f0f2f5",
            fg="#111",
            font=("Segoe UI", 11, "bold"),
        )
        self.welcome_label.pack(pady=(8, 2))

        self.status_label = tk.Label(
            right,
            text="Đang kết nối...",
            bg="#f0f2f5",
            fg="#555",
            font=("Segoe UI", 9),
        )
        self.status_label.pack()

    # ---------- LOGIN ----------
    def do_login(self):
        dialog = LoginDialog(self.root)
        res = dialog.show()
        if not res:
            self.root.destroy()
            return

        user = res["username"]
        pw = res["password"]
        action = res["action"]

        ok = self.client.connect(user, pw, action, self.display_message)
        if not ok:
            messagebox.showerror("Login Error", "Không thể đăng nhập.")
            self.root.destroy()
            return

        self.username_label.config(text=user)
        self.welcome_label.config(text=f"Welcome {user}!")
        self.status_label.config(text="Đang online")
        self.client.message_callback = self.display_message
        self.client.user_list_callback = self.update_user_list
        self.client.room_list_callback = self.update_room_list
        self.client.room_joined_callback = self.on_room_joined
        self.client.chat_event_callback = self.on_chat_event
        self.client.history_callback = self.show_history


    # ---------- CALLBACK TỪ CLIENT ----------
    def display_message(self, text, tag="other"):
        self.chat_text.config(state="normal")
        # chuyển text thành "bubble": thêm khoảng trắng để tách
        self.chat_text.insert("end", " " + text.strip() + " \n", tag)
        self.chat_text.config(state="disabled")
        self.chat_text.see("end")
    
    def show_history(self, room, entries):
        """
        Được gọi mỗi khi server gửi lịch sử 1 phòng.
        Mình clear khung chat và chỉ vẽ lại tin của phòng đó.
        """
        # cập nhật room hiện tại nếu cần
        self.current_room = room
        self.roomname_label.config(text=f"Phòng: {room}")

        # xoá hết nội dung cũ
        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", "end")

        my_name = self.username_label.cget("text")

        for e in entries:
            ts = e.get("timestamp", "")
            u = e.get("username", "")
            m = e.get("message", "")

            # nếu timestamp dạng "YYYY-MM-DD HH:MM:SS" thì lấy phần giờ
            short_ts = ts[-8:] if len(ts) >= 8 else ts

            if u == "SERVER":
                text = f"[{short_ts}] 🔔 ({room}) {m}\n"
                tag = "server"
            elif u == my_name:
                text = f"[{short_ts}] ({room}) Bạn: {m}\n"
                tag = "self"
            else:
                text = f"[{short_ts}] ({room}) {u}: {m}\n"
                tag = "other"

            self.chat_text.insert("end", " " + text.strip() + " \n", tag)

        self.chat_text.config(state="disabled")
        self.chat_text.see("end")


    def update_user_list(self, users):
        self.user_list.delete(0, "end")
        for u in users:
            self.user_list.insert("end", u)

    def update_room_list(self, rooms):
        """
        rooms: list dict {name, is_private, members, creator}
        """
        self.room_list.delete(0, "end")
        for r in rooms:
            if isinstance(r, dict):
                name = r.get("name", "")
                is_private = r.get("is_private", False)
            else:
                name = str(r)
                is_private = False
            label = f"{'🔒 ' if is_private else ''}{name}"
            self.room_list.insert("end", label)

    def on_room_joined(self, room, creator, is_admin):
        self.current_room = room
        self.current_room_creator = creator
        self.current_is_admin = bool(is_admin)

        self.roomname_label.config(text=f"Phòng: {room}")
        if self.current_is_admin:
            self.admin_label.config(text="(QTV)")
            self.manage_btn.config(state="normal")
        else:
            self.admin_label.config(text="")
            self.manage_btn.config(state="disabled")

    def on_chat_event(self, kind: str, name: str, preview: str, is_outgoing: bool):
        # Hiện tại mình dùng main chat_text cho tất cả,
        # nên event chỉ để về sau làm danh sách đoạn chat.
        pass

    # ---------- ACTIONS ----------
    def on_room_click(self, event):
        sel = self.room_list.curselection()
        if not sel:
            return
        raw = self.room_list.get(sel[0])
        # bỏ icon 🔒 nếu có
        room_name = raw.replace("🔒 ", "", 1)

        if room_name == self.current_room:
            # đã ở trong phòng -> chỉ request history
            self.client.request_history(room_name)
            return

        password = ""
        if raw.startswith("🔒"):
            password = simpledialog.askstring(
                "Mật khẩu phòng",
                f"Nhập mật khẩu cho phòng '{room_name}':",
                show="*",
                parent=self.root,
            )
            if password is None:
                return

        self.client.join_room(room_name, password or "")

    def start_private_chat(self, event=None):
        sel = self.user_list.curselection()
        if not sel:
            return
        target = self.user_list.get(sel[0])
        if target == self.username_label.cget("text"):
            return
        msg = simpledialog.askstring(
            "Gửi tin nhắn riêng",
            f"Nhập tin nhắn gửi tới {target}:",
            parent=self.root,
        )
        if not msg:
            return
        self.client.send_private(target, msg)

    # ---------- SEND ----------
    def send_message(self, event=None):
        msg = self.message_entry.get().strip()
        if not msg:
            return
        # gửi tới phòng hiện tại
        self.client.send_chat(msg, room=self.current_room)
        self.message_entry.delete(0, "end")

    def send_image(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.gif")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            filename = os.path.basename(path)
            self.client.send_packet(
                {
                    "type": "image",
                    "filename": filename,
                    "data": b64,
                    "caption": "",
                }
            )
        except Exception as e:
            messagebox.showerror("Lỗi gửi ảnh", str(e))

    # ---------- TẠO / QUẢN LÝ PHÒNG ----------
    def create_room_dialog(self):
        name = simpledialog.askstring(
            "Tạo phòng chat", "Tên phòng:", parent=self.root
        )
        if not name:
            return
        password = simpledialog.askstring(
            "Mật khẩu (tùy chọn)",
            "Nhập mật khẩu nếu muốn đặt phòng private (bỏ trống nếu không):",
            show="*",
            parent=self.root,
        )
        self.client.create_room(name.strip(), password or "")

    def open_room_admin_menu(self):
        if not self.current_is_admin:
            messagebox.showinfo(
                "Quản lý phòng", "Bạn không phải QTV của phòng hiện tại."
            )
            return

        menu = tk.Toplevel(self.root)
        menu.title("Quản lý phòng (QTV)")
        menu.configure(bg="#f0f2f5")
        menu.resizable(False, False)

        tk.Label(
            menu,
            text=f"Phòng: {self.current_room}",
            bg="#f0f2f5",
            fg="#111",
            font=("Segoe UI", 11, "bold"),
        ).pack(padx=12, pady=(10, 6))

        # đổi tên
        def do_rename():
            new_name = simpledialog.askstring(
                "Đổi tên phòng",
                "Tên mới:",
                parent=menu,
            )
            if new_name:
                self.client.admin_rename_room(self.current_room, new_name.strip())

        # đổi mật khẩu
        def do_change_pw():
            new_pw = simpledialog.askstring(
                "Đặt / đổi mật khẩu",
                "Mật khẩu mới (để trống = gỡ mật khẩu):",
                show="*",
                parent=menu,
            )
            if new_pw is None:
                return
            self.client.admin_change_password(self.current_room, new_pw or "")

        # kick
        def do_kick():
            target = simpledialog.askstring(
                "Kick thành viên",
                "Nhập username cần kick khỏi phòng:",
                parent=menu,
            )
            if target:
                self.client.admin_kick(self.current_room, target.strip())

        btn_rename = tk.Button(
            menu,
            text="Đổi tên phòng",
            command=do_rename,
            bg="#9b59b6",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10),
            width=22,
        )
        btn_rename.pack(padx=12, pady=(6, 4))

        btn_pw = tk.Button(
            menu,
            text="Đặt / đổi mật khẩu",
            command=do_change_pw,
            bg="#9b59b6",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10),
            width=22,
        )
        btn_pw.pack(padx=12, pady=4)

        btn_kick = tk.Button(
            menu,
            text="Kick thành viên",
            command=do_kick,
            bg="#e74c3c",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10),
            width=22,
        )
        btn_kick.pack(padx=12, pady=4)

        tk.Button(
            menu,
            text="Đóng",
            command=menu.destroy,
            bg="#bdc3c7",
            fg="#111",
            relief="flat",
            font=("Segoe UI", 10),
            width=22,
        ).pack(padx=12, pady=(8, 10))

    # ---------- RUN ----------
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ClientGUI()
    app.run()
