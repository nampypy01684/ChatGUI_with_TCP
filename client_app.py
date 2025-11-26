import socket
import threading
import json
from datetime import datetime
import base64
import os
import io

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext

from PIL import Image, ImageTk
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

        # callback dùng cho GUI
        self.message_callback = None
        self.user_list_callback = None
        self.room_list_callback = None
        self.room_joined_callback = None
        self.image_callback = None
        self.chat_event_callback = None
        self.history_callback = None
        self.receive_thread = None

        # lưu lỗi lần connect gần nhất
        self.last_error = ""

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
        self.last_error = ""  # reset lỗi cũ
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

            # đọc auth_ok
            buffer = ""
            while True:
                chunk = self.client_socket.recv(4096).decode("utf-8")
                if not chunk:
                    self.last_error = "Mất kết nối khi chờ phản hồi đăng nhập."
                    log_cb("[LỖI] Mất kết nối khi chờ phản hồi đăng nhập.\n", "error")
                    return False
                buffer += chunk
                if "\n" in buffer:
                    line, rest = buffer.split("\n", 1)
                    line = line.strip()
                    break

            try:
                data = json.loads(line)
            except:
                self.last_error = "Phản hồi đăng nhập không hợp lệ."
                log_cb("[LỖI] Phản hồi đăng nhập không hợp lệ.\n", "error")
                return False

            if data.get("type") == "error":
                msg = data.get("message", "Đăng nhập / đăng ký thất bại.")
                self.last_error = msg
                log_cb(f"[LỖI] {msg}\n", "error")
                return False

            if data.get("type") != "auth_ok":
                self.last_error = "Phản hồi đăng nhập không hợp lệ."
                log_cb("[LỖI] Phản hồi đăng nhập không hợp lệ.\n", "error")
                return False

            self.connected = True

            # bắt đầu luồng nhận
            self.receive_thread = threading.Thread(
                target=self.receive_loop,
                args=(rest,),
                daemon=True,
            )
            self.receive_thread.start()
            return True

        except Exception as e:
            self.last_error = f"Không thể kết nối server: {e}"
            log_cb(f"[LỖI] Không thể kết nối server: {e}\n", "error")
            return False

    # ---------- nhận dữ liệu ----------
    def receive_loop(self, initial_buffer=""):
        buffer = initial_buffer or ""
        while self.connected:
            try:
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except:
                        continue
                    self.handle_packet(data)

                chunk = self.client_socket.recv(4096).decode("utf-8")
                if not chunk:
                    if self.message_callback:
                        self.message_callback("[SYSTEM] Mất kết nối.\n", "error")
                    self.connected = False
                    break
                buffer += chunk

            except:
                self.connected = False
                break

    # ---------- xử lý packet ----------
    def handle_packet(self, data):
        msg_type = data.get("type")

        def log(txt, tag="system"):
            if self.message_callback:
                self.message_callback(txt, tag)

        # CHAT
        if msg_type == "chat":
            sender = data.get("sender", "")
            room = data.get("room", "Phòng chung")
            msg = data.get("message", "")
            ts = data.get("timestamp", "??:??:??")

            if sender == "SERVER":
                line = f"[{ts}] 🔔 ({room}) {msg}\n"
                tag = "server"
            elif sender == self.username:
                line = f"[{ts}] ({room}) Bạn: {msg}\n"
                tag = "self"
            else:
                line = f"[{ts}] ({room}) {sender}: {msg}\n"
                tag = "other"

            log(line, tag)

        # PM
        elif msg_type == "private":
            sender = data.get("sender")
            recipient = data.get("recipient")
            msg = data.get("message")
            ts = data.get("timestamp")

            if sender == self.username:
                log(f"[{ts}] [PM -> {recipient}] {msg}\n", "self")
            else:
                log(f"[{ts}] [PM từ {sender}] {msg}\n", "pm")

        elif msg_type == "user_list":
            if self.user_list_callback:
                self.user_list_callback(data.get("users", []))

        elif msg_type == "room_list":
            if self.room_list_callback:
                self.room_list_callback(data.get("rooms", []))

        elif msg_type == "room_joined":
            if self.room_joined_callback:
                self.room_joined_callback(
                    data.get("room"),
                    data.get("creator"),
                    data.get("is_admin", False),
                )

        elif msg_type == "history":
            if self.history_callback:
                self.history_callback(
                    data.get("room", "Phòng chung"),
                    data.get("history", []),
                )

        # ẢNH
        elif msg_type == "image":
            if self.image_callback:
                self.image_callback(data)

    # ---------- Gửi ----------
    def send_chat(self, message: str, room: str = None):
        data = {"type": "chat", "message": message}
        if room:
            data["room"] = room
        return self.send_packet(data)

    def send_private(self, target, message):
        return self.send_packet({"type": "private", "to": target, "message": message})

    def request_history(self, room):
        return self.send_packet({"type": "get_history", "room": room})

    def create_room(self, name, password=""):
        return self.send_packet({
            "type": "create_room",
            "room": name,
            "password": password,
        })

    def join_room(self, name, password=""):
        return self.send_packet({
            "type": "join_room",
            "room": name,
            "password": password,
        })

    # QTV
    def admin_kick(self, room, target):
        return self.send_packet({"type": "admin_kick", "room": room, "target": target})

    def admin_change_password(self, room, new_password):
        return self.send_packet({
            "type": "admin_change_password",
            "room": room,
            "new_password": new_password,
        })

    def admin_rename_room(self, room, new_name):
        return self.send_packet({
            "type": "admin_rename_room",
            "room": room,
            "new_name": new_name,
        })


# ================== GUI ==================
class ClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cute Chat")
        self.root.geometry("1100x650")
        self.root.configure(bg="#dfe3ee")

        self.client = ChatClient()

        self.current_room = "Phòng chung"
        self.current_room_creator = None
        self.current_is_admin = False

        self._img_refs = []  # giữ ảnh tránh GC

        self.build_layout()
        self.do_login()

    # ---------- UI ----------
    def build_layout(self):

        # ----- FIX LỖI CHAT BỊ TRÀN SANG PHẢI -----
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=0)  
        self.root.grid_columnconfigure(1, weight=1)  

        # LEFT SIDEBAR
        left = tk.Frame(self.root, bg="#f0f2f5", width=260)
        left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False)

        # CENTER
        center = tk.Frame(self.root, bg="#dfe3ee")
        center.grid(row=0, column=1, sticky="nsew")

        # ====== FIX QUAN TRỌNG ======
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)
        # ============================

        header = tk.Frame(center, bg="#ffffff", height=50)
        header.grid(row=0, column=0, sticky="new")
        header.grid_propagate(False)

        self.chat_text = scrolledtext.ScrolledText(center, wrap="word", bg="#dfe3ee")
        self.chat_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        # LEFT SIDEBAR
        left = tk.Frame(self.root, bg="#f0f2f5", width=260)
        left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False)

        tk.Label(left, text="  ✉ Chat App", bg="#ffffff",
                 fg="#111", font=("Segoe UI", 11, "bold")).pack(fill="x")

        tk.Button(left, text="+ Tạo phòng", command=self.create_room_dialog,
                  bg="#9b59b6", fg="white").pack(fill="x", padx=12, pady=8)

        tk.Label(left, text="Phòng chat", bg="#f0f2f5").pack(anchor="w", padx=14)
        self.room_list = tk.Listbox(left, bg="white")
        self.room_list.pack(fill="x", padx=12)
        self.room_list.bind("<<ListboxSelect>>", self.on_room_click)

        tk.Label(left, text="Người online", bg="#f0f2f5").pack(anchor="w", padx=14, pady=(8, 2))
        self.user_list = tk.Listbox(left, bg="white")
        self.user_list.pack(fill="both", expand=True, padx=12)
        self.user_list.bind("<Double-Button-1>", self.start_private_chat)

        # CENTER CHAT
        center = tk.Frame(self.root, bg="#dfe3ee")
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_rowconfigure(1, weight=1)

        header = tk.Frame(center, bg="#ffffff", height=50)
        header.grid(row=0, column=0, sticky="new")
        header.grid_propagate(False)

        self.username_label = tk.Label(header, text="Chưa đăng nhập", bg="white", fg="#111")
        self.username_label.pack(side="left", padx=10)

        self.roomname_label = tk.Label(header, text="Phòng: Phòng chung", bg="white")
        self.roomname_label.pack(side="left", padx=10)

        self.admin_label = tk.Label(header, text="", bg="white", fg="#e67e22")
        self.admin_label.pack(side="left")

        self.manage_btn = tk.Button(header, text="⚙ QTV",
                                    command=self.open_room_admin_menu, state="disabled")
        self.manage_btn.pack(side="right", padx=10)

        # chat box
        self.chat_text = scrolledtext.ScrolledText(center, wrap="word",
                                                   bg="#dfe3ee", font=("Segoe UI", 10))
        self.chat_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.chat_text.config(state="disabled")

        self.chat_text.tag_config("self",
            foreground="white",
            background="#9b59b6",
            justify="right",
            spacing1=4, spacing3=4,
            lmargin1=80, lmargin2=80,
            rmargin=10
        )

        self.chat_text.tag_config("other",
            foreground="#111",
            background="#ffffff",
            justify="left",
            spacing1=4, spacing3=4,
            lmargin1=10, lmargin2=10,
            rmargin=80
        )

        self.chat_text.tag_config("server",
            foreground="#2c3e50",
            background="#f9e79f",
            justify="left",
            spacing1=4, spacing3=4,
            lmargin1=10, lmargin2=10,
            rmargin=10
        )

        self.chat_text.tag_config("pm",
            foreground="white",
            background="#e84393",
            justify="left",
            spacing1=4, spacing3=4,
            lmargin1=40, lmargin2=40,
            rmargin=40
        )

        self.chat_text.tag_config("img_text",
            foreground="#555",
            background="#ffffff",
            justify="left",
            lmargin1=10,
            lmargin2=10,
            rmargin=10
        )

   
        # input
        input_frame = tk.Frame(center, bg="white", height=70)
        input_frame.grid(row=2, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.message_entry = tk.Entry(input_frame, bg="#f0f2f5")
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=14)
        self.message_entry.bind("<Return>", self.send_message)

        tk.Button(input_frame, text="Gửi", bg="#9b59b6", fg="white",
                  command=self.send_message).grid(row=0, column=1, padx=4)

        tk.Button(input_frame, text="📎", command=self.send_image).grid(row=0, column=2, padx=10)

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

        # đăng ký callback TRƯỚC connect
        self.client.message_callback = self.display_message
        self.client.user_list_callback = self.update_user_list
        self.client.room_list_callback = self.update_room_list
        self.client.room_joined_callback = self.on_room_joined
        self.client.chat_event_callback = self.on_chat_event
        self.client.history_callback = self.show_history
        self.client.image_callback = self.show_image  # NEW

        ok = self.client.connect(user, pw, action, self.display_message)
        if not ok:
            msg = self.client.last_error or "Sai thông tin hoặc không thỏa điều kiện.\nVui lòng đăng ký lại."
            messagebox.showerror("Lỗi đăng nhập / đăng ký", msg)
            self.do_login()   # mở lại form đăng nhập
            return


    # ---------- CALLBACK ----------
    def display_message(self, text, tag="other"):
        self.chat_text.config(state="normal")
        self.chat_text.insert("end", text, tag)
        self.chat_text.config(state="disabled")
        self.chat_text.see("end")

    def show_history(self, room, entries):
        self.current_room = room
        self.roomname_label.config(text=f"Phòng: {room}")

        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", "end")

        my_name = self.username_label.cget("text")
        for e in entries:
            ts = e.get("timestamp", "")[-8:]
            u = e.get("username", "")
            m = e.get("message", "")

            if u == "SERVER":
                tag = "server"
                text = f"[{ts}] 🔔 ({room}) {m}\n"
            elif u == my_name:
                tag = "self"
                text = f"[{ts}] ({room}) Bạn: {m}\n"
            else:
                tag = "other"
                text = f"[{ts}] ({room}) {u}: {m}\n"

            self.chat_text.insert("end", text, tag)

        self.chat_text.config(state="disabled")
        self.chat_text.see("end")

    # ========== HIỂN THỊ ẢNH ==========
    def show_image(self, data):
        try:
            b64 = data.get("data")
            filename = data.get("filename", "")
            sender = data.get("sender", "")
            room = data.get("room", "")
            ts = data.get("timestamp", "")

            raw = base64.b64decode(b64)
            img = Image.open(io.BytesIO(raw))
            img.thumbnail((240, 240))
            tk_img = ImageTk.PhotoImage(img)
            self._img_refs.append(tk_img)

            self.chat_text.config(state="normal")

            # prefix text dùng tag riêng để không phá layout bubble
            if sender == self.username_label.cget("text"):
                prefix = f"[{ts}] ({room}) Bạn gửi ảnh: {filename}"
            else:
                prefix = f"[{ts}] ({room}) {sender} gửi ảnh: {filename}"

            self.chat_text.insert("end", prefix + "\n", "img_text")

            # ---------- FIX QUAN TRỌNG ----------
            # TÁCH ẢNH RA KHỎI CƠ CHẾ WRAP / JUSTIFY CỦA TAG TRƯỚC ĐÓ
            self.chat_text.insert("end", "\n", "img_text")
            self.chat_text.window_create("end",
                                        window=tk.Label(self.chat_text, image=tk_img, bg="#ffffff"))
            self.chat_text.insert("end", "\n\n", "img_text")
            # -------------------------------------

            self.chat_text.config(state="disabled")
            self.chat_text.see("end")

        except Exception as e:
            self.display_message(f"[Lỗi hiển thị ảnh] {e}\n", "error")

    # ---------- UPDATE UI ----------
    def update_user_list(self, users):
        self.user_list.delete(0, "end")
        for u in users:
            self.user_list.insert("end", u)

    def update_room_list(self, rooms):
        self.room_list.delete(0, "end")
        for r in rooms:
            name = r["name"]
            is_private = r["is_private"]
            label = ("🔒 " if is_private else "") + name
            self.room_list.insert("end", label)

    def on_room_joined(self, room, creator, is_admin):
        self.current_room = room
        self.current_room_creator = creator
        self.current_is_admin = is_admin

        self.roomname_label.config(text=f"Phòng: {room}")
        if is_admin:
            self.admin_label.config(text="(QTV)")
            self.manage_btn.config(state="normal")
        else:
            self.admin_label.config(text="")
            self.manage_btn.config(state="disabled")

    def on_chat_event(self, kind, name, preview, is_outgoing):
        pass

    # ---------- ACTIONS ----------
    def on_room_click(self, event):
        sel = self.room_list.curselection()
        if not sel:
            return

        raw = self.room_list.get(sel[0])
        room_name = raw.replace("🔒 ", "")

        if room_name == self.current_room:
            self.client.request_history(room_name)
            return

        pwd = ""
        if raw.startswith("🔒"):
            pwd = simpledialog.askstring("Mật khẩu phòng",
                                         f"Mật khẩu phòng '{room_name}':",
                                         show="*")
            if pwd is None:
                return

        self.client.join_room(room_name, pwd)

    def start_private_chat(self, event):
        sel = self.user_list.curselection()
        if not sel:
            return
        target = self.user_list.get(sel[0])
        if target == self.username_label.cget("text"):
            return
        msg = simpledialog.askstring("PM", f"Gửi tin nhắn tới {target}:")
        if msg:
            self.client.send_private(target, msg)

    # ---------- SEND ----------
    def send_message(self, event=None):
        msg = self.message_entry.get().strip()
        if not msg:
            return
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
            self.client.send_packet({
                "type": "image",
                "filename": filename,
                "data": b64,
                "caption": "",
            })
        except Exception as e:
            messagebox.showerror("Lỗi gửi ảnh", str(e))

    # ---------- QUẢN LÝ PHÒNG ----------
    def create_room_dialog(self):
        name = simpledialog.askstring("Tạo phòng", "Tên phòng:")
        if not name:
            return
        pw = simpledialog.askstring("Mật khẩu", "Đặt mật khẩu (tùy chọn):", show="*")
        self.client.create_room(name.strip(), pw or "")

    def open_room_admin_menu(self):
        if not self.current_is_admin:
            messagebox.showinfo("Không phải QTV", "Bạn không phải QTV.")
            return
        menu = tk.Toplevel(self.root)
        menu.title("Quản lý phòng")
        menu.configure(bg="#f0f2f5")

        tk.Label(menu,
                 text=f"Phòng: {self.current_room}",
                 bg="#f0f2f5", fg="#111",
                 font=("Segoe UI", 11, "bold")).pack(pady=10)

        def rename():
            new = simpledialog.askstring("Đổi tên", "Tên mới:", parent=menu)
            if new:
                self.client.admin_rename_room(self.current_room, new.strip())

        def change_pw():
            pw = simpledialog.askstring("Đổi mật khẩu", "Mật khẩu mới:", show="*", parent=menu)
            if pw is not None:
                self.client.admin_change_password(self.current_room, pw or "")

        def kick_user():
            target = simpledialog.askstring("Kick", "Tên thành viên:", parent=menu)
            if target:
                self.client.admin_kick(self.current_room, target)

        tk.Button(menu, text="Đổi tên phòng", bg="#9b59b6", fg="white",
                  command=rename).pack(pady=4)
        tk.Button(menu, text="Đặt / đổi mật khẩu", bg="#9b59b6", fg="white",
                  command=change_pw).pack(pady=4)
        tk.Button(menu, text="Kick thành viên", bg="#e74c3c", fg="white",
                  command=kick_user).pack(pady=4)

        tk.Button(menu, text="Đóng",
                  command=menu.destroy).pack(pady=10)

    # ---------- RUN ----------
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ClientGUI()
    app.run()
