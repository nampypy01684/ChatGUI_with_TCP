import socket
import threading
import json
import hashlib
from datetime import datetime
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, scrolledtext

USERS_FILE = "users.json"
HISTORY_FILE = "chat_history.json"


# ===================== UTILS =====================
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_users(db):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def hash_pw(pw: str):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            hist = json.load(f)
    except:
        return []

    for e in hist:
        if isinstance(e, dict) and "room" not in e:
            e["room"] = "Phòng chung"

    return hist


def save_history(hist):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist[-1000:], f, ensure_ascii=False, indent=2)


# ===================== SERVER =====================
class ChatServer:
    def __init__(self, host="0.0.0.0", port=5555):
        self.host = host
        self.port = port

        self.users = load_users()
        self.history = load_history()

        self.server_socket = None
        self.clients = {}  # sock -> {"username":..., "room":...}

        self.rooms = {
            "Phòng chung": {
                "creator": "SERVER",
                "password": "",
                "is_private": False,
                "members": set(),
            }
        }
        self.running = False
        self.logger = None

    # ------------------ SEND ------------------
    def send(self, sock, data: dict):
        try:
            payload = json.dumps(data) + "\n"
            sock.sendall(payload.encode("utf-8"))
        except:
            pass

    def broadcast_all(self, data: dict):
        payload = json.dumps(data) + "\n"
        dead = []
        for s in list(self.clients.keys()):
            try:
                s.sendall(payload.encode("utf-8"))
            except:
                dead.append(s)
        for ds in dead:
            self.remove_client(ds)

    def broadcast_user_list(self):
        lst = [info["username"] for info in self.clients.values()]
        self.broadcast_all({"type": "user_list", "users": lst})

    def send_room_list(self):
        arr = []
        for name, info in self.rooms.items():
            arr.append({
                "name": name,
                "creator": info["creator"],
                "is_private": info["is_private"],
                "members_count": len(info["members"]),
            })
        self.broadcast_all({"type": "room_list", "rooms": arr})

    # ------------------ HISTORY ------------------
    def add_history(self, user, msg, room):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": user,
            "message": msg,
            "room": room,
        }
        self.history.append(entry)
        save_history(self.history)
        # notify admin UI / logger if present
        try:
            if self.logger:
                self.logger(f"[{room}] {user}: {msg}")
        except:
            pass

    # ------------------ ROOM ------------------
    def broadcast_room(self, room_name, sender, message, mtype="chat"):
        if room_name not in self.rooms:
            return

        packet = {
            "type": mtype,
            "sender": sender,
            "message": message,
            "room": room_name,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }

        payload = json.dumps(packet) + "\n"

        dead = []
        for s in list(self.rooms[room_name]["members"]):
            try:
                s.sendall(payload.encode("utf-8"))
            except:
                dead.append(s)

        for ds in dead:
            self.remove_client(ds)

    def join_room(self, sock, room_name, password=""):
        info = self.clients.get(sock)
        if not info:
            return

        username = info["username"]

        if room_name not in self.rooms:
            self.rooms[room_name] = {
                "creator": username,
                "password": "",
                "is_private": False,
                "members": set(),
            }

        room = self.rooms[room_name]

        if room["is_private"] and room["password"] != password:
            self.send(sock, {"type": "error", "message": "Sai mật khẩu phòng."})
            return

        # rời phòng cũ
        old = info["room"]
        if old and old in self.rooms:
            self.rooms[old]["members"].discard(sock)

        # vào phòng mới
        room["members"].add(sock)
        info["room"] = room_name

        # gửi history
        hh = [e for e in self.history if e["room"] == room_name][-50:]
        self.send(sock, {"type": "history", "room": room_name, "history": hh})

        # thông báo join
        msg = f"{username} đã tham gia phòng {room_name}!"
        self.broadcast_room(room_name, "SERVER", msg)
        self.add_history("SERVER", msg, room_name)

        # gửi thông tin phòng
        self.send(sock, {
            "type": "room_joined",
            "room": room_name,
            "creator": room["creator"],
            "is_admin": (username == room["creator"])
        })

        self.send_room_list()
        try:
            if self.logger:
                self.logger(f"{username} joined room '{room_name}'")
        except:
            pass

    # ------------------ AUTH ------------------
    def handle_auth(self, sock):
        try:
            raw = sock.recv(4096).decode("utf-8")
            line = raw.split("\n", 1)[0]
            p = json.loads(line)
        except:
            return None

        if p.get("type") != "auth":
            self.send(sock, {"type": "error", "message": "Auth lỗi."})
            return None

        username = p.get("username")
        password = p.get("password")
        action = p.get("action")
        if not username or not password:
            self.send(sock, {"type": "error", "message": "Thiếu thông tin."})
            return None

        pw_hash = hash_pw(password)

        if action == "register":

            # ----- RÀNG BUỘC USERNAME -----
            if len(username) < 3:
                self.send(sock, {"type": "error", "message": "Tên đăng nhập phải có ít nhất 3 ký tự."})
                return None

            if not username.isalnum():
                self.send(sock, {"type": "error", "message": "Tên đăng nhập chỉ được chứa chữ và số."})
                return None

            # ----- RÀNG BUỘC PASSWORD -----
            if len(password) < 6:
                self.send(sock, {"type": "error", "message": "Mật khẩu phải có ít nhất 6 ký tự."})
                return None

            if username in self.users:
                self.send(sock, {"type": "error", "message": "Tên tài khoản đã tồn tại."})
                return None

            # OK → tạo tài khoản
            self.users[username] = {"password": pw_hash, "avatar": None}
            save_users(self.users)


        elif action == "login":
            if username not in self.users:
                self.send(sock, {"type": "error", "message": "Không có tài khoản."})
                return None
            if self.users[username]["password"] != pw_hash:
                self.send(sock, {"type": "error", "message": "Sai mật khẩu."})
                return None

        self.send(sock, {"type": "auth_ok", "username": username})
        try:
            if self.logger:
                self.logger(f"Auth OK: {username}")
        except:
            pass
        return username

    # ------------------ PACKET PROCESS ------------------
    def process_packet(self, sock, data):
        msg_type = data.get("type")
        info = self.clients.get(sock)
        if not info:
            return

        user = info["username"]
        room = info["room"]

        # CHAT
        if msg_type == "chat":
            msg = data.get("message", "")
            self.broadcast_room(room, user, msg)
            self.add_history(user, msg, room)
            try:
                if self.logger:
                    self.logger(f"[CHAT] ({room}) {user}: {msg}")
            except:
                pass

        # PM
        elif msg_type == "private":
            to = data.get("to")
            msg = data.get("message", "")
            for s, inf in self.clients.items():
                if inf["username"] == to:
                    self.send(s, {
                        "type": "private",
                        "sender": user,
                        "recipient": to,
                        "message": msg,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    self.send(sock, {
                        "type": "private",
                        "sender": user,
                        "recipient": to,
                        "message": msg,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    break
            try:
                if self.logger:
                    self.logger(f"[PM] {user} -> {to}: {msg}")
            except:
                pass

        # JOIN ROOM
        elif msg_type == "join_room":
            self.join_room(sock, data.get("room", ""), data.get("password", ""))

        # CREATE ROOM
        elif msg_type == "create_room":
            name = data.get("room")
            pw = data.get("password", "")
            self.rooms[name] = {
                "creator": user,
                "password": pw,
                "is_private": pw != "",
                "members": set()
            }
            self.send_room_list()
            try:
                if self.logger:
                    self.logger(f"{user} created room '{name}' private={pw != ''}")
            except:
                pass

        # update room (rename / change password)
        elif msg_type == "update_room":
            room = data.get("room")
            new_name = data.get("new_name")
            new_pw = data.get("password")
            info = self.clients.get(sock)
            if not info:
                return
            username = info["username"]
            if room not in self.rooms:
                self.send(sock, {"type": "error", "message": "Phòng không tồn tại."})
                return
            # only creator can update
            if self.rooms[room]["creator"] != username:
                self.send(sock, {"type": "error", "message": "Không có quyền chỉnh sửa phòng."})
                return

            # change password
            if new_pw is not None:
                self.rooms[room]["password"] = new_pw
                self.rooms[room]["is_private"] = new_pw != ""

            # rename
            if new_name and new_name != room:
                if new_name in self.rooms:
                    self.send(sock, {"type": "error", "message": "Tên phòng mới đã tồn tại."})
                    return
                self.rooms[new_name] = self.rooms.pop(room)
                # update members' current room name
                for s in list(self.rooms[new_name]["members"]):
                    if s in self.clients:
                        self.clients[s]["room"] = new_name

            self.send_room_list()
            try:
                if self.logger:
                    self.logger(f"{username} updated room '{room}' -> '{new_name or room}' password set={'yes' if new_pw else 'no'}")
            except:
                pass

        elif msg_type == "delete_room":
            room = data.get("room")
            info = self.clients.get(sock)
            if not info:
                return
            username = info["username"]
            if room not in self.rooms:
                self.send(sock, {"type": "error", "message": "Phòng không tồn tại."})
                return
            if self.rooms[room]["creator"] != username:
                self.send(sock, {"type": "error", "message": "Không có quyền xóa phòng."})
                return
            ok = self.delete_room(room)
            if ok:
                try:
                    if self.logger:
                        self.logger(f"{username} deleted room '{room}'")
                except:
                    pass

        # IMAGE
        elif msg_type == "image":
            filename = data.get("filename")
            b64 = data.get("data")
            caption = data.get("caption", "")

            img_packet = {
                "type": "image",
                "sender": user,
                "room": room,
                "filename": filename,
                "data": b64,
                "caption": caption,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }

            # thông báo (dạng tin nhắn text)
            self.broadcast_room(room, user, f"[ảnh] {filename}")

            # gửi file thật
            for s in self.rooms[room]["members"]:
                self.send(s, img_packet)

            self.add_history(user, f"[ảnh] {filename}", room)

    # ------------------ HANDLE CLIENT ------------------
    def handle_client(self, sock, addr):
        username = self.handle_auth(sock)
        if not username:
            try:
                sock.close()
            except:
                pass
            return

        print(f"[SERVER] {username} connected")

        # thêm vào danh sách online
        self.clients[sock] = {"username": username, "room": "Phòng chung"}
        self.rooms["Phòng chung"]["members"].add(sock)

        # gửi danh sách user + phòng
        self.broadcast_user_list()
        self.send_room_list()

        # gửi lịch sử phòng chung
        hh = [e for e in self.history if e["room"] == "Phòng chung"][-50:]
        self.send(sock, {"type": "history", "room": "Phòng chung", "history": hh})

        # thông báo join
        join_msg = f"{username} đã tham gia phòng Phòng chung!"
        self.broadcast_room("Phòng chung", "SERVER", join_msg)
        self.add_history("SERVER", join_msg, "Phòng chung")

        # gửi room_joined
        self.send(sock, {
            "type": "room_joined",
            "room": "Phòng chung",
            "creator": "SERVER",
            "is_admin": False
        })

        buffer = ""
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except:
                        continue
                    self.process_packet(sock, data)

        except:
            pass

        self.remove_client(sock)

    # ------------------ REMOVE CLIENT ------------------
    def remove_client(self, sock):
        if sock not in self.clients:
            return

        username = self.clients[sock]["username"]
        room = self.clients[sock]["room"]

        if room in self.rooms:
            self.rooms[room]["members"].discard(sock)
            msg = f"{username} đã rời phòng {room}!"
            self.broadcast_room(room, "SERVER", msg)
            self.add_history("SERVER", msg, room)

        del self.clients[sock]

        try:
            sock.close()
        except:
            pass

        self.broadcast_user_list()
        self.send_room_list()

    # ------------------ RUN ------------------
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # set timeout so we can stop cleanly
        self.server_socket.settimeout(1.0)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(20)
        self.running = True

        print(f"SERVER RUNNING: {self.host}:{self.port}")

        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True).start()

        print("SERVER STOPPED")

    def start_in_thread(self):
        threading.Thread(target=self.start, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except:
            pass
        # disconnect clients
        for s in list(self.clients.keys()):
            try:
                s.close()
            except:
                pass
        self.clients.clear()
        # reset rooms to only common room
        self.rooms = {
            "Phòng chung": {
                "creator": "SERVER",
                "password": "",
                "is_private": False,
                "members": set(),
            }
        }
        self.broadcast_user_list()
        self.send_room_list()
        print("SERVER: stopped and clients disconnected")

    def clear_history(self):
        self.history = []
        save_history(self.history)
        print("SERVER: history cleared")

    def delete_room(self, room_name: str):
        if room_name == "Phòng chung":
            return False
        if room_name not in self.rooms:
            return False
        members = list(self.rooms[room_name]["members"])
        for s in members:
            try:
                self.send(s, {"type": "info", "message": f"Phòng {room_name} đã bị xóa, chuyển về Phòng chung"})
                # move to common room
                self.rooms["Phòng chung"]["members"].add(s)
                if s in self.clients:
                    self.clients[s]["room"] = "Phòng chung"
            except:
                pass
        del self.rooms[room_name]
        self.add_history("SERVER", f"Phòng {room_name} bị xóa bởi quản trị viên.", "Phòng chung")
        self.send_room_list()
        return True

    def get_room_password(self, room_name: str):
        if room_name in self.rooms:
            return self.rooms[room_name].get("password", "")
        return None


if __name__ == "__main__":
    server = ChatServer()

    root = tk.Tk()
    root.title("Chat Server - Quản lý")

    # Top frame: host/port and control buttons
    top = tk.Frame(root)
    top.pack(fill=tk.X, padx=6, pady=6)

    tk.Label(top, text="Host:").pack(side=tk.LEFT)
    host_entry = tk.Entry(top, width=15)
    host_entry.insert(0, server.host)
    host_entry.pack(side=tk.LEFT, padx=(0, 6))

    tk.Label(top, text="Port:").pack(side=tk.LEFT)
    port_entry = tk.Entry(top, width=6)
    port_entry.insert(0, str(server.port))
    port_entry.pack(side=tk.LEFT, padx=(0, 6))

    status_label = tk.Label(top, text="Stopped", fg="red")
    status_label.pack(side=tk.LEFT, padx=(6, 6))

    def log(msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            log_area.configure(state=tk.NORMAL)
            log_area.insert(tk.END, f"[{ts}] {msg}\n")
            log_area.see(tk.END)
            log_area.configure(state=tk.DISABLED)
        except:
            pass
        print(msg)

    # connect server logger to GUI log
    server.logger = log

    def start_server():
        h = host_entry.get().strip() or server.host
        try:
            p = int(port_entry.get().strip())
        except:
            messagebox.showerror("Lỗi", "Port không hợp lệ")
            return
        server.host = h
        server.port = p
        server.start_in_thread()
        status_label.config(text=f"Running: {server.host}:{server.port}", fg="green")
        log(f"Server starting on {server.host}:{server.port}")

    def stop_server():
        server.stop()
        status_label.config(text="Stopped", fg="red")
        log("Server stopped")

    btn_start = tk.Button(top, text="Kết nối", command=start_server)
    btn_start.pack(side=tk.LEFT, padx=(4, 4))
    btn_stop = tk.Button(top, text="Ngắt kết nối", command=stop_server)
    btn_stop.pack(side=tk.LEFT)

    # Middle frame: lists and actions
    mid = tk.Frame(root)
    mid.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    users_frame = tk.LabelFrame(mid, text="Người dùng online")
    users_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,6))
    users_list = tk.Listbox(users_frame, height=12)
    users_list.pack(fill=tk.BOTH, expand=True)

    rooms_frame = tk.LabelFrame(mid, text="Phòng")
    rooms_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,6))
    rooms_list = tk.Listbox(rooms_frame, height=12)
    rooms_list.pack(fill=tk.BOTH, expand=True)

    actions = tk.Frame(mid)
    actions.pack(side=tk.LEFT, fill=tk.Y)

    def refresh_ui():
        # preserve current selections (by name)
        try:
            cur_user_sel = None
            user_sel = users_list.curselection()
            if user_sel:
                cur_user_sel = users_list.get(user_sel[0])
        except:
            cur_user_sel = None

        try:
            cur_room_sel = None
            room_sel = rooms_list.curselection()
            if room_sel:
                cur_room_sel = rooms_list.get(room_sel[0]).split(" (", 1)[0]
        except:
            cur_room_sel = None

        # users
        users_list.delete(0, tk.END)
        for info in server.clients.values():
            users_list.insert(tk.END, info.get("username"))

        # restore user selection if possible
        if cur_user_sel:
            try:
                idx = None
                for i in range(users_list.size()):
                    if users_list.get(i) == cur_user_sel:
                        idx = i
                        break
                if idx is not None:
                    users_list.selection_set(idx)
                    users_list.see(idx)
            except:
                pass

        # rooms
        rooms_list.delete(0, tk.END)
        for name, info in server.rooms.items():
            rooms_list.insert(tk.END, f"{name} ({len(info['members'])})")

        # restore room selection if possible
        if cur_room_sel:
            try:
                idx = None
                for i in range(rooms_list.size()):
                    rn = rooms_list.get(i).split(" (", 1)[0]
                    if rn == cur_room_sel:
                        idx = i
                        break
                if idx is not None:
                    rooms_list.selection_set(idx)
                    rooms_list.see(idx)
            except:
                pass

        # schedule next refresh
        root.after(1000, refresh_ui)

    def clear_history_ui():
        if messagebox.askyesno("Xóa lịch sử", "Bạn có chắc muốn xóa toàn bộ lịch sử chat?"):
            server.clear_history()
            log("Đã xóa lịch sử chat")

    def delete_room_ui():
        sel = rooms_list.curselection()
        if not sel:
            messagebox.showinfo("Chọn phòng", "Vui lòng chọn phòng để xóa")
            return
        text = rooms_list.get(sel[0])
        room_name = text.split(" (",1)[0]
        if room_name == "Phòng chung":
            messagebox.showwarning("Không thể xóa", "Không thể xóa Phòng chung")
            return
        if messagebox.askyesno("Xóa phòng", f"Xóa phòng '{room_name}' ?"):
            ok = server.delete_room(room_name)
            if ok:
                log(f"Đã xóa phòng {room_name}")
            else:
                messagebox.showerror("Lỗi", "Xóa phòng thất bại")

    def read_password_ui():
        sel = rooms_list.curselection()
        if not sel:
            messagebox.showinfo("Chọn phòng", "Vui lòng chọn phòng")
            return
        text = rooms_list.get(sel[0])
        room_name = text.split(" (",1)[0]
        pw = server.get_room_password(room_name)
        if pw is None:
            messagebox.showerror("Lỗi", "Không tìm thấy phòng")
            return
        if pw == "":
            messagebox.showinfo("Mật khẩu phòng", f"Phòng '{room_name}' không có mật khẩu (công khai)")
        else:
            messagebox.showinfo("Mật khẩu phòng", f"Mật khẩu phòng '{room_name}': {pw}")

    btn_clear_hist = tk.Button(actions, text="Xóa lịch sử", command=clear_history_ui)
    btn_clear_hist.pack(fill=tk.X, pady=(0,6))
    btn_delete_room = tk.Button(actions, text="Xóa phòng", command=delete_room_ui)
    btn_delete_room.pack(fill=tk.X, pady=(0,6))
    btn_read_pw = tk.Button(actions, text="Xem mật khẩu phòng", command=read_password_ui)
    btn_read_pw.pack(fill=tk.X, pady=(0,6))

    # Bottom: log
    log_frame = tk.LabelFrame(root, text="Log")
    log_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))
    log_area = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED, height=10)
    log_area.pack(fill=tk.BOTH, expand=True)

    def on_close():
        try:
            server.stop()
        except:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # start UI refresh loop
    refresh_ui()

    root.mainloop()
