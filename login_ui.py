import tkinter as tk
from tkinter import ttk


class LoginDialog:
    def __init__(self, master):
        self.master = master
        self.result = None

        self.top = tk.Toplevel(master)
        self.top.title("Đăng nhập chat")
        self.top.geometry("360x260")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.configure(bg="#f0f0f0")

        # ----- FRAME CHÍNH -----
        main = ttk.Frame(self.top, padding=12)
        main.pack(fill="both", expand=True)

        # Username
        ttk.Label(main, text="Tên đăng nhập:").grid(row=0, column=0, sticky="w")
        self.username_entry = ttk.Entry(main, width=25)
        self.username_entry.grid(row=0, column=1, sticky="ew", pady=2)

        # Password
        ttk.Label(main, text="Mật khẩu:").grid(row=1, column=0, sticky="w")
        self.password_entry = ttk.Entry(main, show="*", width=25)
        self.password_entry.grid(row=1, column=1, sticky="ew", pady=2)

        # Server host
        ttk.Label(main, text="Server (IP/host):").grid(row=2, column=0, sticky="w")
        self.host_entry = ttk.Entry(main, width=25)
        self.host_entry.insert(0, "127.0.0.1")  # mặc định localhost
        self.host_entry.grid(row=2, column=1, sticky="ew", pady=2)

        # Port
        ttk.Label(main, text="Port:").grid(row=3, column=0, sticky="w")
        self.port_entry = ttk.Entry(main, width=25)
        self.port_entry.insert(0, "5555")
        self.port_entry.grid(row=3, column=1, sticky="ew", pady=2)

        # Action: login / register
        action_frame = ttk.Frame(main)
        action_frame.grid(row=4, column=0, columnspan=2, pady=6, sticky="w")

        self.action_var = tk.StringVar(value="login")
        ttk.Radiobutton(action_frame, text="Đăng nhập",
                        variable=self.action_var, value="login").pack(side="left", padx=4)
        ttk.Radiobutton(action_frame, text="Đăng ký",
                        variable=self.action_var, value="register").pack(side="left", padx=4)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=8)

        ok_btn = ttk.Button(btn_frame, text="OK", command=self.on_ok)
        ok_btn.pack(side="left", padx=5)
        cancel_btn = ttk.Button(btn_frame, text="Hủy", command=self.on_cancel)
        cancel_btn.pack(side="left", padx=5)

        # một chút layout
        main.columnconfigure(1, weight=1)

        # focus vào username
        self.username_entry.focus_set()

        # bind Enter
        self.top.bind("<Return>", lambda e: self.on_ok())

    def on_ok(self):
        u = self.username_entry.get().strip()
        p = self.password_entry.get().strip()
        h = self.host_entry.get().strip() or "127.0.0.1"
        port_str = self.port_entry.get().strip() or "5555"

        try:
            port = int(port_str)
        except ValueError:
            port = 5555

        if not u or not p:
            return  # có thể thêm messagebox nếu muốn

        self.result = {
            "username": u,
            "password": p,
            "action": self.action_var.get(),
            "host": h,
            "port": port,
        }
        self.top.destroy()

    def on_cancel(self):
        self.result = None
        self.top.destroy()

    def show(self):
        self.master.wait_window(self.top)
        return self.result
