# chat_client.py
import socket, threading, json, queue
import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, messagebox
from datetime import datetime

HOST, PORT = "127.0.0.1", 12345

class ChatClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.username = None
        self.current_room = None
        self.recv_thread = None
        self.inq = queue.Queue()  # hàng đợi thông điệp từ thread mạng

        # ====== UI ======
        self.root = tk.Tk()
        self.root.title("TCP Chat Client (Rooms + PM)")
        self.root.geometry("760x520")

        topbar = ttk.Frame(self.root)
        topbar.pack(fill=tk.X, padx=10, pady=8)

        self.host_entry = ttk.Entry(topbar, width=18)
        self.host_entry.insert(0, HOST)
        self.port_entry = ttk.Entry(topbar, width=6)
        self.port_entry.insert(0, str(PORT))

        ttk.Label(topbar, text="Host:").pack(side=tk.LEFT)
        self.host_entry.pack(side=tk.LEFT, padx=(4,10))
        ttk.Label(topbar, text="Port:").pack(side=tk.LEFT)
        self.port_entry.pack(side=tk.LEFT, padx=(4,10))

        self.btn_connect = ttk.Button(topbar, text="Kết nối", command=self.connect)
        self.btn_disconnect = ttk.Button(topbar, text="Ngắt", command=self.disconnect, state=tk.DISABLED)
        self.btn_connect.pack(side=tk.LEFT)
        self.btn_disconnect.pack(side=tk.LEFT, padx=(6,0))

        ttk.Label(topbar, text="Phòng:").pack(side=tk.LEFT, padx=(14,4))
        self.room_box = ttk.Combobox(topbar, values=["lobby","class","random"], width=14, state="readonly")
        self.room_box.set("lobby")
        self.room_box.pack(side=tk.LEFT)
        self.btn_join = ttk.Button(topbar, text="Join", command=self.join_room, state=tk.DISABLED)
        self.btn_join.pack(side=tk.LEFT, padx=(6,0))

        self.btn_users = ttk.Button(topbar, text="Users", command=self.ask_users, state=tk.DISABLED)
        self.btn_hist = ttk.Button(topbar, text="History", command=self.ask_history, state=tk.DISABLED)
        self.btn_users.pack(side=tk.LEFT, padx=(6,0))
        self.btn_hist.pack(side=tk.LEFT, padx=(6,0))

        # main panes
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        # left/chat
        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_area = scrolledtext.ScrolledText(left, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_area.pack(fill=tk.BOTH, expand=True)

        entry_row = ttk.Frame(left)
        entry_row.pack(fill=tk.X, pady=(6,0))
        self.entry = ttk.Entry(entry_row)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", self.on_send)
        self.btn_send = ttk.Button(entry_row, text="Gửi", command=self.on_send)
        self.btn_send.pack(side=tk.LEFT, padx=(6,0))

        # right/users & pm
        right = ttk.Frame(main, width=200)
        right.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(right, text="Đang trong phòng").pack(anchor="w")
        self.room_label = ttk.Label(right, text="-")
        self.room_label.pack(anchor="w", pady=(0,6))

        ttk.Label(right, text="Người dùng").pack(anchor="w")
        self.user_list = tk.Listbox(right, height=12)
        self.user_list.pack(fill=tk.Y, expand=False)
        self.btn_pm = ttk.Button(right, text="PM người chọn", command=self.send_pm)
        self.btn_pm.pack(fill=tk.X, pady=(6,0))

        self.status = ttk.Label(self.root, text="Chưa kết nối.")
        self.status.pack(fill=tk.X, padx=10, pady=(0,6))

        # tick UI updates
        self.root.after(50, self._drain_incoming)

    # =========== networking helpers ===========
    def _send(self, obj):
        try:
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            self.sock.sendall(line.encode("utf-8"))
        except Exception as e:
            self._append(f"[Lỗi gửi] {e}\n")

    def _append(self, text):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, text)
        self.chat_area.config(state=tk.DISABLED)
        self.chat_area.see(tk.END)

    def connect(self):
        if self.connected:
            return
        host = self.host_entry.get().strip()
        port = int(self.port_entry.get())
        name = simpledialog.askstring("Tên đăng nhập", "Nhập username:")
        if not name:
            return
        self.username = name

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self.connected = True
            self.status.config(text=f"Đã kết nối {host}:{port} dưới tên {self.username}")
            self.btn_connect.config(state=tk.DISABLED)
            self.btn_disconnect.config(state=tk.NORMAL)
            self.btn_join.config(state=tk.NORMAL)
            self.btn_users.config(state=tk.NORMAL)
            self.btn_hist.config(state=tk.NORMAL)

            # start recv thread
            self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.recv_thread.start()

            # hello + login
            self._send({"type":"hello","username": self.username})

            # auto join room chọn sẵn
            self.join_room()
        except Exception as e:
            self._append(f"[Lỗi kết nối] {e}\n")
            self.connected = False
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def disconnect(self):
        if not self.connected:
            return
        try:
            self._send({"type":"bye"})
        except:
            pass
        try:
            self.sock.close()
        except:
            pass
        self.connected = False
        self.sock = None
        self.btn_connect.config(state=tk.NORMAL)
        for b in (self.btn_disconnect, self.btn_join, self.btn_users, self.btn_hist):
            b.config(state=tk.DISABLED)
        self.status.config(text="Đã ngắt kết nối.")
        self.room_label.config(text="-")
        self.user_list.delete(0, tk.END)

    def join_room(self):
        if not self.connected:
            return
        room = self.room_box.get().strip() or "lobby"
        self._send({"type":"join","room": room})

    def ask_users(self):
        if self.connected:
            self._send({"type":"list"})

    def ask_history(self):
        if self.connected:
            r = self.current_room or "lobby"
            self._send({"type":"history","room": r, "limit": 200})

    def on_send(self, evt=None):
        if not self.connected:
            return
        text = self.entry.get().strip()
        if not text:
            return
        # cú pháp nhanh cho PM: /pm username nội_dung
        if text.startswith("/pm "):
            try:
                _, to, *parts = text.split(" ")
                pm_text = " ".join(parts).strip()
                if to and pm_text:
                    self._send({"type":"pm","to": to, "text": pm_text})
                    self._append(f"[PM -> {to}] {pm_text}\n")
                    self.entry.delete(0, tk.END)
                    return
            except Exception:
                pass
        # chat thường
        self._send({"type":"chat","text": text})
        self.entry.delete(0, tk.END)

    def send_pm(self):
        sel = self.user_list.curselection()
        if not sel:
            messagebox.showinfo("PM", "Chọn 1 người trong danh sách ở phòng hiện tại.")
            return
        to_user = self.user_list.get(sel[0])
        content = simpledialog.askstring("PM", f"Nội dung gửi {to_user}:")
        if content:
            self._send({"type":"pm","to": to_user, "text": content})
            self._append(f"[PM -> {to_user}] {content}\n")

    def _recv_loop(self):
        buf = b""
        try:
            while self.connected:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8", errors="ignore"))
                        self.inq.put(msg)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.inq.put({"type":"_netdown"})

    # xử lý message từ queue trong thread UI
    def _drain_incoming(self):
        try:
            while True:
                msg = self.inq.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.root.after(50, self._drain_incoming)

    def _handle_msg(self, msg):
        mtype = msg.get("type")
        if mtype == "_netdown":
            if self.connected:
                self._append("[Mất kết nối tới server]\n")
                self.disconnect()
            return

        if mtype in ("hello","ok"):
            # lược bỏ, chỉ hiện status
            return

        if mtype == "joined":
            room = msg.get("room")
            self.current_room = room
            self.room_label.config(text=room)
            # users
            self.user_list.delete(0, tk.END)
            for u in msg.get("users", []):
                self.user_list.insert(tk.END, u)
            # history
            hist = msg.get("history", [])
            self._append(f"== Đã vào phòng [{room}] ==\n")
            for h in hist:
                self._append(self._format_line(h))
            return

        if mtype == "users":
            if msg.get("room") == self.current_room:
                self.user_list.delete(0, tk.END)
                for u in msg.get("users", []):
                    self.user_list.insert(tk.END, u)
            return

        if mtype == "chat":
            self._append(self._format_line(msg))
            return

        if mtype == "system":
            self._append(f"[{msg.get('time')}] [Hệ thống] {msg.get('text')}\n")
            return

        if mtype == "pm":
            self._append(f"[{msg.get('time')}] [PM {msg.get('from')} -> {msg.get('to')}] {msg.get('text')}\n")
            return

        if mtype == "history":
            room = msg.get("room")
            items = msg.get("items", [])
            self._append(f"== Lịch sử gần đây của phòng [{room}] ==\n")
            for h in items:
                self._append(self._format_line(h))
            return

        if mtype == "error":
            self._append(f"[Lỗi] {msg.get('error')}\n")

    def _format_line(self, h):
        if h.get("type") == "chat":
            t = h.get("time"); who = h.get("from"); text = h.get("text")
            ip = h.get("ip","")
            return f"[{t}] {ip} | {who}: {text}\n"
        elif h.get("type") == "system":
            return f"[{h.get('time')}] [Hệ thống] {h.get('text')}\n"
        else:
            return f"{h}\n"

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    ChatClient().run()
