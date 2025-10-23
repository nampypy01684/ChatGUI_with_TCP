import socket
import threading
import sys
import json
from datetime import datetime

# Tên file log (global để dùng chung)
log_file = "chat_history.json"

# Danh sách client kết nối
clients = []
# Map socket -> username
client_names = {}
messages = []  # Không dùng nữa, có thể xóa nếu không cần

def broadcast(message, sender_socket=None):
    """Gửi tin nhắn đến tất cả client trừ sender."""
    for client in clients:
        if client != sender_socket:
            try:
                client.send(message.encode('utf-8'))
            except:
                # Xóa client nếu lỗi
                if client in clients:
                    clients.remove(client)
                client_names.pop(client, None)
                client.close()

def handle_client(client_socket, addr):
    """Xử lý tin nhắn từ một client."""
    print(f"Client mới kết nối: {addr}")
    username = None
    while True:
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if message == "DISCONNECT":
                if client_socket in clients:
                    clients.remove(client_socket)
                client_socket.close()
                left_name = client_names.pop(client_socket, None)
                display_left = left_name if left_name else f"{addr[0]}:{addr[1]}"
                print(f"Client {display_left} ngắt kết nối.")
                break
            else:
                # Nếu là gói tên người dùng: NAME:<username>
                if message.startswith("NAME:"):
                    username = message.split(":", 1)[1].strip() or None
                    client_names[client_socket] = username
                    join_name = username if username else f"{addr[0]}:{addr[1]}"
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    notice = f"{addr[0]} | {timestamp} | [Hệ thống]: {join_name} đã tham gia.\n"
                    print(notice.strip())
                    broadcast(notice, sender_socket=client_socket)
                    continue

                display_name = username or client_names.get(client_socket) or f"{addr[0]}:{addr[1]}"
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                full_message = f"{addr[0]} | {timestamp} | {display_name}: {message}\n"
                # messages.append(full_message)  # Không dùng nữa
                log_entry = {"time": timestamp, "sender": f"{addr[0]} | {display_name}", "message": message}
                with open(log_file, 'a') as f:
                    json.dump(log_entry, f)
                    f.write('\n')
                print(full_message.strip())
                broadcast(full_message, client_socket)
        except:
            if client_socket in clients:
                clients.remove(client_socket)
            client_names.pop(client_socket, None)
            client_socket.close()
            break

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('localhost', 12345))  # Có thể thay '' để bind all IP nếu cần mạng ngoài
    server.listen(5)
    print("Server đang lắng nghe trên localhost:12345...")

    while True:
        client_socket, addr = server.accept()
        clients.append(client_socket)
        thread = threading.Thread(target=handle_client, args=(client_socket, addr))
        thread.start()

if __name__ == "__main__":
    start_server()