import socket
import threading
import tkinter as tk
from tkinter import scrolledtext
from tkinter import messagebox
from tkinter import simpledialog
import json  # Thêm import cho load_history
import os
from datetime import datetime

class ChatClient:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.username = None

        # GUI - Tăng kích thước window
        self.root = tk.Tk()
        self.root.title("Chat Client")
        self.root.geometry("500x400")

        # Chat area
        self.chat_area = scrolledtext.ScrolledText(self.root, state=tk.DISABLED, wrap=tk.WORD, height=15)
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Frame cho input và nút
        input_frame = tk.Frame(self.root)
        input_frame.pack(padx=10, pady=5, fill=tk.X)

        self.message_entry = tk.Entry(input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.message_entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(input_frame, text="Gửi", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=(5, 0))

        # Frame cho connect/disconnect và load history
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=5)

        self.connect_button = tk.Button(control_frame, text="Kết nối Server", command=self.connect_to_server)
        self.connect_button.pack(side=tk.LEFT, padx=5)

        self.disconnect_button = tk.Button(control_frame, text="Ngắt kết nối", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)

        # Thêm nút Xem Lịch Sử (enable sau khi connect)
        self.load_history_button = tk.Button(control_frame, text="Xem Lịch Sử", command=self.load_history, state=tk.DISABLED)
        self.load_history_button.pack(side=tk.LEFT, padx=5)

        # Nút Xóa Lịch Sử (enable sau khi connect)
        self.clear_history_button = tk.Button(control_frame, text="Xóa Lịch Sử", command=self.clear_history, state=tk.DISABLED)
        self.clear_history_button.pack(side=tk.LEFT, padx=5)

    def connect_to_server(self):
        try:
            if self.connected:
                return
            # Đảm bảo socket mới cho mỗi lần kết nối lại
            try:
                if self.client is None or self.client.fileno() == -1:
                    self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            except Exception:
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Hỏi tên người dùng
            name = simpledialog.askstring("Tên người dùng", "Nhập tên của bạn:")
            if name is None or not name.strip():
                self.add_message("Kết nối bị hủy: chưa nhập tên.\n")
                return
            self.username = name.strip()

            self.client.connect(('localhost', 12345))
            self.connected = True
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.load_history_button.config(state=tk.NORMAL)  # Enable nút sau connect
            self.clear_history_button.config(state=tk.NORMAL)
            self.chat_area.config(state=tk.NORMAL)
            self.chat_area.insert(tk.END, f"Đã kết nối đến server dưới tên: {self.username}\n")
            self.chat_area.config(state=tk.DISABLED)
            self.chat_area.see(tk.END)

            # Thread nhận tin nhắn
            thread = threading.Thread(target=self.receive_messages, daemon=True)
            thread.start()

            # Gửi tên người dùng cho server
            try:
                self.client.send(f"NAME:{self.username}".encode('utf-8'))
            except Exception as e:
                self.add_message(f"Lỗi gửi tên: {e}\n")
        except Exception as e:
            self.add_message(f"Lỗi kết nối: {e}")

    def load_history(self):
        # Mở cửa sổ lịch sử riêng
        history_window = tk.Toplevel(self.root)
        history_window.title("Lịch Sử Chat")
        history_window.geometry("600x450")

        btn_frame = tk.Frame(history_window)
        btn_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        text_area = scrolledtext.ScrolledText(history_window, state=tk.DISABLED, wrap=tk.WORD)
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def append_line(line: str):
            text_area.config(state=tk.NORMAL)
            text_area.insert(tk.END, line)
            text_area.config(state=tk.DISABLED)
            text_area.see(tk.END)

        def refresh_history():
            # Xóa nội dung cũ
            text_area.config(state=tk.NORMAL)
            text_area.delete('1.0', tk.END)
            text_area.config(state=tk.DISABLED)

            try:
                with open("chat_history.json", 'r') as f:
                    for line in f:
                        if line.strip():  # Bỏ qua line rỗng
                            data = json.loads(line)
                            msg = data.get('message', '')
                            sender = data.get('sender', '')
                            # Hiển thị thống nhất IP | time | name: content
                            # Bỏ qua các dòng tham gia cũ (NAME:...)
                            if isinstance(msg, str) and msg.startswith("NAME:"):
                                continue
                            if ' | ' in sender:
                                ip_part, name_part = sender.split(' | ', 1)
                            else:
                                ip_part, name_part = "127.0.0.1", sender
                            append_line(f"{ip_part} | {data['time']} | {name_part}: {msg}\n")
                append_line("Đã tải lịch sử chat.\n")
            except FileNotFoundError:
                append_line("Chưa có file lịch sử.\n")
            except json.JSONDecodeError:
                append_line("Lỗi đọc file lịch sử.\n")

        refresh_btn = tk.Button(btn_frame, text="Làm mới", command=refresh_history)
        refresh_btn.pack(side=tk.LEFT)

        close_btn = tk.Button(btn_frame, text="Đóng", command=history_window.destroy)
        close_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Tải lần đầu khi mở cửa sổ
        refresh_history()

    def disconnect(self):
        if self.connected:
            try:
                self.client.send("DISCONNECT".encode('utf-8'))
            except Exception:
                pass
            try:
                try:
                    self.client.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.client.close()
            finally:
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connected = False
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.load_history_button.config(state=tk.DISABLED)  # Disable nút
            self.clear_history_button.config(state=tk.DISABLED)
            self.add_message("Đã ngắt kết nối.\n")

    def send_message(self, event=None):
        if not self.connected:
            return
        message = self.message_entry.get()
        if message:
            try:
                self.client.send(message.encode('utf-8'))
                display_name = self.username if self.username else "Bạn"
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    ip_addr = self.client.getsockname()[0]
                except Exception:
                    ip_addr = "127.0.0.1"
                self.add_message(f"{ip_addr} | {timestamp} | {display_name}: {message}\n")
                self.message_entry.delete(0, tk.END)
            except Exception as e:
                self.add_message(f"Lỗi gửi: {e}")

    def receive_messages(self):
        while self.connected:
            try:
                message = self.client.recv(1024).decode('utf-8')
                if message:
                    # Server đã gửi đúng định dạng IP-time-name: content (đã có newline)
                    self.add_message(message)
            except:
                break
        # Mất kết nối từ phía server hoặc lỗi mạng: cập nhật UI, chuẩn bị socket mới
        if self.connected:
            self.connected = False
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.load_history_button.config(state=tk.DISABLED)
            self.clear_history_button.config(state=tk.DISABLED)
            try:
                self.client.close()
            except Exception:
                pass
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.add_message("Mất kết nối tới server.\n")

    def add_message(self, message):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, message)
        self.chat_area.config(state=tk.DISABLED)
        self.chat_area.see(tk.END)

    def clear_history(self):
        """Xóa hoặc làm trống file lịch sử chat."""
        history_path = "chat_history.json"
        try:
            confirm = messagebox.askyesno("Xác nhận", "Bạn có chắc muốn xóa lịch sử chat?")
            if not confirm:
                self.add_message("Đã hủy xóa lịch sử.\n")
                return
            # Luôn làm trống (truncate) file. Nếu file chưa tồn tại, tạo file rỗng.
            with open(history_path, 'w') as f:
                pass
            self.add_message("Đã làm trống lịch sử chat.\n")
        except Exception as e:
            self.add_message(f"Lỗi khi xóa lịch sử: {e}\n")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ChatClient()
    app.run()