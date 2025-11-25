import tkinter as tk
from tkinter import ttk


class LoginDialog:
    def __init__(self, master):
        self.master = master
        self.result = None

        self.top = tk.Toplevel(master)
        self.top.title("Đăng nhập chat")
        self.top.geometry("320x220")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.configure(bg="#f0f0f0")

        # username
        tk.Label(self.top, text="Tài khoản:", bg="#f0f0f0").pack(anchor="w", padx=16, pady=(16, 2))
        self.username_entry = ttk.Entry(self.top)
        self.username_entry.pack(fill="x", padx=16)

        # password
        tk.Label(self.top, text="Mật khẩu:", bg="#f0f0f0").pack(anchor="w", padx=16, pady=(10, 2))
        self.password_entry = ttk.Entry(self.top, show="*")
        self.password_entry.pack(fill="x", padx=16)

        # radio login / register
        def on_action_change(*args):
            if self.action_var.get() == "register":
                self.show_requirements()

        self.action_var = tk.StringVar(value="login")
        self.action_var.trace("w", on_action_change)
        ttk.Radiobutton(frame_radio, text="Đăng nhập", value="login",
                        variable=self.action_var).pack(side="left")
        ttk.Radiobutton(frame_radio, text="Đăng ký", value="register",
                        variable=self.action_var).pack(side="left", padx=(10, 0))


        # buttons
        btn_frame = tk.Frame(self.top, bg="#f0f0f0")
        btn_frame.pack(fill="x", padx=16, pady=(16, 10))
        ttk.Button(btn_frame, text="OK", command=self.on_ok).pack(side="right")
        ttk.Button(btn_frame, text="Hủy", command=self.on_cancel).pack(side="right", padx=(0, 8))

        self.username_entry.focus_set()
        self.top.bind("<Return>", lambda e: self.on_ok())

    def on_ok(self):
        u = self.username_entry.get().strip()
        p = self.password_entry.get().strip()
        if not u or not p:
            return
        self.result = {
            "username": u,
            "password": p,
            "action": self.action_var.get()
        }
        self.top.destroy()

    def on_cancel(self):
        self.result = None
        self.top.destroy()

    def show(self):
        self.master.wait_window(self.top)
        return self.result
