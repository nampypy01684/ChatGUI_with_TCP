# chat_server.py
import socket, threading, json, time, os
from datetime import datetime

HOST, PORT = '0.0.0.0', 12345
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Trạng thái server
clients_lock = threading.Lock()
# client_sockets -> {"name": str, "room": str}
clients = {}
# room -> set(client_sockets)
rooms = {}
# room -> list of log dicts (giới hạn kích thước để tránh phình bộ nhớ)
room_buffers = {}
MAX_ROOM_BUFFER = 500  # giới hạn lịch sử giữ trong RAM

def nowstr():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def send_json(sock, obj):
    try:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        sock.sendall(line.encode("utf-8"))
    except Exception:
        # rơi về xử lý ngắt kết nối ở nơi khác
        pass

def log_line(room, entry):
    # Lưu RAM
    buf = room_buffers.setdefault(room, [])
    buf.append(entry)
    if len(buf) > MAX_ROOM_BUFFER:
        del buf[: len(buf) - MAX_ROOM_BUFFER]
    # Lưu file JSON lines theo phòng
    path = os.path.join(LOG_DIR, f"{room}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def broadcast_room(room, payload, exclude=None):
    with clients_lock:
        targets = list(rooms.get(room, set()))
    for s in targets:
        if s is exclude:
            continue
        send_json(s, payload)

def system_to_room(room, text):
    entry = {
        "type": "system",
        "time": nowstr(),
        "room": room,
        "text": text,
    }
    log_line(room, entry)
    broadcast_room(room, entry)

def user_list(room):
    with clients_lock:
        users = []
        for s in rooms.get(room, set()):
            meta = clients.get(s)
            if meta:
                users.append(meta["name"])
    return sorted(users)

def switch_room(sock, new_room):
    with clients_lock:
        meta = clients.get(sock)
        if not meta:
            return
        old_room = meta.get("room")
        if old_room and old_room in rooms:
            rooms[old_room].discard(sock)
            # thông báo rời phòng cũ
            system_to_room(old_room, f"{meta['name']} đã rời phòng.")
        meta["room"] = new_room
        rooms.setdefault(new_room, set()).add(sock)

    # thông báo vào phòng mới
    system_to_room(new_room, f"{meta['name']} đã tham gia phòng.")
    # cập nhật danh sách user cho cả phòng
    payload = {"type": "users", "room": new_room, "users": user_list(new_room)}
    broadcast_room(new_room, payload)

def handle_client(sock, addr):
    peer = f"{addr[0]}:{addr[1]}"
    # Chưa đăng ký
    name = None
    room = None

    # Chào sơ bộ
    send_json(sock, {"type": "hello", "server": "pychat", "time": nowstr()})

    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8", errors="ignore"))
                except Exception:
                    send_json(sock, {"type": "error", "error": "invalid_json"})
                    continue

                mtype = msg.get("type")

                # 1) HELLO/LOGIN
                if mtype == "hello":
                    proposed = (msg.get("username") or "").strip()
                    if not proposed:
                        send_json(sock, {"type": "error", "error": "username_required"})
                        continue
                    # gán tên
                    name = proposed
                    with clients_lock:
                        clients[sock] = {"name": name, "room": None}
                    send_json(sock, {"type": "ok", "what": "login", "time": nowstr()})

                # 2) JOIN ROOM
                elif mtype == "join":
                    r = (msg.get("room") or "lobby").strip()
                    if not name:
                        send_json(sock, {"type": "error", "error": "login_first"})
                        continue
                    switch_room(sock, r)
                    room = r
                    # trả user list + lịch sử gần đây
                    hist = list(room_buffers.get(room, []))[-100:]
                    send_json(sock, {"type": "joined", "room": room, "users": user_list(room), "history": hist})

                # 3) CHAT MESSAGE (broadcast trong phòng)
                elif mtype == "chat":
                    if not (name and room):
                        send_json(sock, {"type": "error", "error": "join_room_first"})
                        continue
                    text = str(msg.get("text", "")).strip()
                    if not text:
                        continue
                    entry = {
                        "type": "chat",
                        "time": nowstr(),
                        "room": room,
                        "from": name,
                        "ip": addr[0],
                        "text": text
                    }
                    log_line(room, entry)
                    broadcast_room(room, entry)

                # 4) PRIVATE MESSAGE
                elif mtype == "pm":
                    if not name:
                        send_json(sock, {"type": "error", "error": "login_first"})
                        continue
                    to_user = (msg.get("to") or "").strip()
                    text = str(msg.get("text", "")).strip()
                    if not to_user or not text:
                        continue
                    found = None
                    with clients_lock:
                        for s, meta in clients.items():
                            if meta["name"] == to_user:
                                found = s
                                break
                    if not found:
                        send_json(sock, {"type": "error", "error": "user_not_found", "to": to_user})
                    else:
                        payload = {"type": "pm", "time": nowstr(), "from": name, "to": to_user, "text": text}
                        send_json(found, payload)
                        send_json(sock, {"type": "ok", "what": "pm"})

                # 5) LIST USERS TRONG PHÒNG HIỆN TẠI
                elif mtype == "list":
                    if not room:
                        send_json(sock, {"type": "users", "room": None, "users": []})
                    else:
                        send_json(sock, {"type": "users", "room": room, "users": user_list(room)})

                # 6) HISTORY (đọc từ file nhanh gọn)
                elif mtype == "history":
                    r = (msg.get("room") or room or "lobby").strip()
                    limit = int(msg.get("limit", 100))
                    path = os.path.join(LOG_DIR, f"{r}.jsonl")
                    lines = []
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as f:
                            for ln in f:
                                ln = ln.strip()
                                if ln:
                                    lines.append(json.loads(ln))
                    lines = lines[-limit:]
                    send_json(sock, {"type": "history", "room": r, "items": lines})

                # 7) BYE
                elif mtype == "bye":
                    raise ConnectionResetError

                else:
                    send_json(sock, {"type": "error", "error": "unknown_type", "got": mtype})

    except Exception:
        pass
    finally:
        # cleanup
        with clients_lock:
            meta = clients.pop(sock, None)
            if meta:
                r = meta.get("room")
                if r and r in rooms:
                    rooms[r].discard(sock)
                    system_to_room(r, f"{meta['name']} đã thoát.")
                    # cập nhật user list
                    broadcast_room(r, {"type": "users", "room": r, "users": user_list(r)})
        try:
            sock.close()
        except:
            pass

def serve_forever():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(64)
    print(f"Server lắng nghe tại {HOST}:{PORT}")
    try:
        while True:
            c, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(c, addr), daemon=True)
            t.start()
    finally:
        srv.close()

if __name__ == "__main__":
    serve_forever()
