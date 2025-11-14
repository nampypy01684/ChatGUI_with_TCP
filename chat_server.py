import socket
import threading
import json
import os
import hashlib
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox


class ChatServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555):
        self.host = host
        self.port = port
        self.server_socket: socket.socket | None = None
        # {sock: {"username": str, "current_room": str | None}}
        self.clients: dict[socket.socket, dict] = {}
        # {room_name: {"creator": str, "password": str, "is_private": bool, "members": set[socket.socket]}}
        self.rooms: dict[str, dict] = {}
        self.running = False

        # history
        self.history_file = "chat_history.json"
        self.chat_history: list[dict] = self.load_history()

        # user accounts
        self.users_file = "users.json"
        self.users: dict[str, dict] = self.load_users()

    # ---------- history ----------
    def load_history(self) -> list:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_history(self) -> None:
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_history[-1000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Lỗi lưu lịch sử:", e)

    def add_to_history(self, username: str, message: str, room: str = "Phòng chung") -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.chat_history.append({
            "timestamp": ts,
            "username": username,
            "message": message,
            "room": room,
        })
        self.save_history()

    # ---------- users ----------
    def load_users(self) -> dict:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_users(self) -> None:
        try:
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(self.users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Lỗi lưu users:", e)

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    # ---------- utilities ----------
    def send_json(self, sock: socket.socket, data: dict) -> None:
        try:
            payload = json.dumps(data) + "\n"
            sock.sendall(payload.encode("utf-8"))
        except Exception:
            pass

    def ensure_default_room(self) -> None:
        if "Phòng chung" not in self.rooms:
            self.rooms["Phòng chung"] = {
                "creator": "SERVER",
                "password": "",
                "is_private": False,
                "members": set(),
            }

    def broadcast_user_list(self) -> None:
        users = []
        for info in self.clients.values():
            name = info.get("username")
            if name and name not in users:
                users.append(name)
        data = {"type": "user_list", "users": users}
        payload = json.dumps(data) + "\n"
        disconnected = []
        for sock in list(self.clients.keys()):
            try:
                sock.sendall(payload.encode("utf-8"))
            except Exception:
                disconnected.append(sock)
        for sock in disconnected:
            self.remove_client(sock)

    def broadcast_room_list(self) -> None:
        rooms = list(self.rooms.keys())
        data = {"type": "room_list", "rooms": rooms}
        payload = json.dumps(data) + "\n"
        disconnected = []
        for sock in list(self.clients.keys()):
            try:
                sock.sendall(payload.encode("utf-8"))
            except Exception:
                disconnected.append(sock)
        for sock in disconnected:
            self.remove_client(sock)

    def broadcast_room_message(self, room: str, sender: str, message: str) -> None:
        if room not in self.rooms:
            return
        data = {
            "type": "chat",
            "sender": sender,
            "message": message,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "room": room,
        }
        payload = json.dumps(data) + "\n"
        disconnected = []
        for sock in list(self.rooms[room]["members"]):
            try:
                sock.sendall(payload.encode("utf-8"))
            except Exception:
                disconnected.append(sock)
        for sock in disconnected:
            self.remove_client(sock)

    def add_client_to_room(self, sock: socket.socket, room: str) -> None:
        self.ensure_default_room()
        info = self.clients.get(sock)
        if not info:
            return
        old_room = info.get("current_room")
        if old_room and old_room in self.rooms:
            self.rooms[old_room]["members"].discard(sock)

        if room not in self.rooms:
            self.rooms[room] = {
                "creator": info["username"],
                "password": "",
                "is_private": False,
                "members": set(),
            }
        self.rooms[room]["members"].add(sock)
        info["current_room"] = room

        # gửi lịch sử cho phòng đó
        history = [h for h in self.chat_history if h.get("room") == room][-50:]
        self.send_json(sock, {"type": "history", "room": room, "history": history})

        msg = f"{info['username']} đã tham gia phòng {room}."
        self.broadcast_room_message(room, "SERVER", msg)
        self.add_to_history("SERVER", msg, room)
        self.broadcast_room_list()

    def remove_client(self, sock: socket.socket) -> None:
        info = self.clients.pop(sock, None)
        if info:
            username = info.get("username", "???")
            room = info.get("current_room")
            if room and room in self.rooms:
                self.rooms[room]["members"].discard(sock)
                msg = f"{username} đã rời khỏi phòng {room}."
                self.broadcast_room_message(room, "SERVER", msg)
                self.add_to_history("SERVER", msg, room)
        try:
            sock.close()
        except Exception:
            pass
        self.broadcast_user_list()
        self.broadcast_room_list()

    # ---------- server loop ----------
    def start_server(self, log_cb) -> bool:
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            self.ensure_default_room()
            log_cb(f"[SERVER] Đang chạy trên {self.host}:{self.port}\n")

            threading.Thread(
                target=self.accept_loop, args=(log_cb,), daemon=True
            ).start()
            return True
        except Exception as e:
            log_cb(f"[LỖI] Không thể khởi động server: {e}\n")
            return False

    def stop_server(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None
        for sock in list(self.clients.keys()):
            self.remove_client(sock)

    def accept_loop(self, log_cb):
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                log_cb(f"[CONNECT] {addr}\n")
                threading.Thread(
                    target=self.handle_client, args=(client_sock, addr, log_cb), daemon=True
                ).start()
            except Exception:
                break

    # ---------- auth + handling client ----------
    def handle_client(self, sock: socket.socket, addr, log_cb):
        username = None
        try:
            # bước 1: nhận gói auth đầu tiên
            first = sock.recv(4096).decode("utf-8").strip()
            if not first:
                sock.close()
                return
            try:
                packet = json.loads(first)
            except json.JSONDecodeError:
                packet = None

            if isinstance(packet, dict) and packet.get("type") == "auth":
                action = packet.get("action", "login")
                username = (packet.get("username") or "").strip()
                password = packet.get("password") or ""
                if not username:
                    username = f"user-{addr[1]}"

                if action == "register":
                    if username in self.users:
                        self.send_json(sock, {
                            "type": "error",
                            "message": "Username đã tồn tại."
                        })
                        sock.close()
                        return
                    self.users[username] = {
                        "password": self.hash_password(password),
                        "avatar": None,
                    }
                    self.save_users()
                else:  # login
                    if username not in self.users:
                        self.send_json(sock, {
                            "type": "error",
                            "message": "Tài khoản không tồn tại."
                        })
                        sock.close()
                        return
                    if self.users[username]["password"] != self.hash_password(password):
                        self.send_json(sock, {
                            "type": "error",
                            "message": "Sai mật khẩu."
                        })
                        sock.close()
                        return

                # ok
                self.clients[sock] = {"username": username, "current_room": None}
                log_cb(f"[JOIN] {username} (auth) từ {addr}\n")
                avatar_b64 = self.users[username].get("avatar")
                self.send_json(sock, {
                    "type": "auth_ok",
                    "username": username,
                    "avatar": avatar_b64,
                })

            else:
                # client cũ: xem 'first' là username
                username = first.strip() or f"user-{addr[1]}"
                self.clients[sock] = {"username": username, "current_room": None}
                log_cb(f"[JOIN] {username} từ {addr}\n")
                # không gửi auth_ok (client cũ không cần)

            # sau khi login xong
            self.broadcast_user_list()
            self.broadcast_room_list()
            self.add_client_to_room(sock, "Phòng chung")

            buffer = ""
            while self.running:
                chunk = sock.recv(4096).decode("utf-8")
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
                    except json.JSONDecodeError:
                        # xem như chat plain text
                        data = {"type": "chat", "message": line}

                    msg_type = data.get("type", "chat")
                    info = self.clients.get(sock)
                    if not info:
                        break
                    username = info["username"]
                    room = info.get("current_room") or "Phòng chung"

                    if msg_type == "chat":
                        msg = data.get("message", "")
                        if not msg:
                            continue
                        log_cb(f"[{username} @ {room}] {msg}\n")
                        self.broadcast_room_message(room, username, msg)
                        self.add_to_history(username, msg, room)

                    elif msg_type == "private":
                        target_name = data.get("to")
                        pm_text = data.get("message", "")
                        if not target_name or not pm_text:
                            continue
                        target_sock = None
                        for s2, inf2 in self.clients.items():
                            if inf2.get("username") == target_name:
                                target_sock = s2
                                break
                        if not target_sock:
                            self.send_json(sock, {
                                "type": "error",
                                "message": f"Không tìm thấy người dùng '{target_name}'."
                            })
                            continue
                        ts = datetime.now().strftime("%H:%M:%S")
                        payload = {
                            "type": "private",
                            "sender": username,
                            "recipient": target_name,
                            "message": pm_text,
                            "timestamp": ts,
                        }
                        self.send_json(sock, payload)
                        self.send_json(target_sock, payload)
                        log_cb(f"[PM] {username} -> {target_name}: {pm_text}\n")

                    elif msg_type == "create_room":
                        room_name = (data.get("room") or "").strip()
                        password = data.get("password", "") or ""
                        if not room_name:
                            self.send_json(sock, {
                                "type": "error",
                                "message": "Tên phòng không được để trống."
                            })
                            continue
                        if room_name in self.rooms:
                            self.send_json(sock, {
                                "type": "error",
                                "message": "Phòng đã tồn tại."
                            })
                            continue
                        self.rooms[room_name] = {
                            "creator": username,
                            "password": password,
                            "is_private": bool(password),
                            "members": set(),
                        }
                        log_cb(f"[ROOM] {username} tạo phòng {room_name}\n")
                        self.add_client_to_room(sock, room_name)
                        self.send_json(sock, {
                            "type": "room_joined",
                            "room": room_name,
                            "creator": username,
                            "is_admin": True,
                        })

                    elif msg_type == "join_room":
                        room_name = (data.get("room") or "").strip()
                        password = data.get("password", "") or ""
                        if room_name not in self.rooms:
                            self.send_json(sock, {
                                "type": "error",
                                "message": "Phòng không tồn tại."
                            })
                            continue
                        rinfo = self.rooms[room_name]
                        if rinfo["is_private"] and rinfo["password"]:
                            if password != rinfo["password"]:
                                self.send_json(sock, {
                                    "type": "error",
                                    "message": "Sai mật khẩu phòng."
                                })
                                continue
                        self.add_client_to_room(sock, room_name)
                        self.send_json(sock, {
                            "type": "room_joined",
                            "room": room_name,
                            "creator": rinfo["creator"],
                            "is_admin": (username == rinfo["creator"]),
                        })

                    elif msg_type == "get_history":
                        room_name = data.get("room") or room
                        history = [h for h in self.chat_history if h.get("room") == room_name][-50:]
                        self.send_json(sock, {
                            "type": "history",
                            "room": room_name,
                            "history": history,
                        })

                    elif msg_type == "update_avatar":
                        img_b64 = data.get("image_data")
                        if not img_b64:
                            continue
                        if username not in self.users:
                            self.users[username] = {
                                "password": "",
                                "avatar": img_b64,
                            }
                        else:
                            self.users[username]["avatar"] = img_b64
                        self.save_users()
                        self.send_json(sock, {
                            "type": "avatar_updated",
                            "message": "Avatar đã được cập nhật."
                        })

                    elif msg_type == "image":
                        img_b64 = data.get("image_data")
                        filename = data.get("filename", "image")
                        caption = data.get("caption", "")
                        if not img_b64:
                            continue
                        ts = datetime.now().strftime("%H:%M:%S")
                        payload = {
                            "type": "image",
                            "sender": username,
                            "room": room,
                            "timestamp": ts,
                            "image_data": img_b64,
                            "filename": filename,
                            "caption": caption,
                        }
                        if room in self.rooms:
                            for s2 in list(self.rooms[room]["members"]):
                                self.send_json(s2, payload)
                        hist_text = f"[Ảnh] {filename}"
                        if caption:
                            hist_text += f" - {caption}"
                        self.add_to_history(username, hist_text, room)

                    elif msg_type == "error":
                        # từ client gửi, ít dùng
                        log_cb(f"[CLIENT-ERROR {username}] {data.get('message')}\n")

        except Exception as e:
            log_cb(f"[LỖI] Lỗi kết nối với {addr}: {e}\n")
        finally:
            self.remove_client(sock)


# ================= GUI CHO SERVER =================

class ServerGUI:
    def __init__(self):
        self.server = ChatServer()

        self.root = tk.Tk()
        self.root.title("Chat Server")
        self.root.geometry("700x500")
        self.root.configure(bg="#1e1e1e")

        self.build_ui()

    def build_ui(self):
        top = tk.Frame(self.root, bg="#1e1e1e")
        top.pack(fill="x", pady=5)

        tk.Label(
            top,
            text=f"Server: {self.server.host}:{self.server.port}",
            bg="#1e1e1e",
            fg="white",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=10)

        self.status_label = tk.Label(
            top,
            text="Trạng thái: DỪNG",
            bg="#1e1e1e",
            fg="#e74c3c",
            font=("Segoe UI", 10),
        )
        self.status_label.pack(side="right", padx=10)

        control = tk.Frame(self.root, bg="#1e1e1e")
        control.pack(fill="x", pady=5)

        self.start_btn = tk.Button(
            control,
            text="▶ Khởi động",
            command=self.start_server,
            bg="#2ecc71",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
        )
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = tk.Button(
            control,
            text="■ Dừng",
            command=self.stop_server,
            bg="#e74c3c",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            state="disabled",
        )
        self.stop_btn.pack(side="left")

        clear_btn = tk.Button(
            control,
            text="Xoá log",
            command=self.clear_logs,
            bg="#95a5a6",
            fg="white",
            font=("Segoe UI", 10),
            relief="flat",
            padx=10,
        )
        clear_btn.pack(side="right", padx=10)

        self.log_text = scrolledtext.ScrolledText(
            self.root,
            bg="#2d3436",
            fg="#ecf0f1",
            font=("Consolas", 10),
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def log(self, text: str):
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def start_server(self):
        if self.server.start_server(self.log):
            self.status_label.config(text="Trạng thái: ĐANG CHẠY", fg="#2ecc71")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")

    def stop_server(self):
        self.server.stop_server()
        self.status_label.config(text="Trạng thái: DỪNG", fg="#e74c3c")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def clear_logs(self):
        self.log_text.delete("1.0", "end")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        if messagebox.askokcancel("Thoát", "Bạn có chắc muốn thoát server?"):
            self.server.stop_server()
            self.root.destroy()


if __name__ == "__main__":
    gui = ServerGUI()
    gui.run()
