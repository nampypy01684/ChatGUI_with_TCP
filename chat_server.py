import socket
import threading
import json
import hashlib
from datetime import datetime
import os

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
    def __init__(self, host="127.0.0.1", port=5555):
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
            if username in self.users:
                self.send(sock, {"type": "error", "message": "Tên đã tồn tại."})
                return None
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
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(20)

        print(f"SERVER RUNNING: {self.host}:{self.port}")

        while True:
            client_sock, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True).start()


if __name__ == "__main__":
    ChatServer().start()
