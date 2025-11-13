import tkinter as tk
from tkinter import messagebox


class LoginDialog:
    """
    Hộp thoại đăng nhập / đăng kí.

    Dùng:
        dialog = LoginDialog(root)
        info = dialog.show()   # dict {"username","password","action"} hoặc None nếu huỷ
    """
    def __init__(self, parent):
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Đăng nhập / Đăng kí")
        self.dialog.geometry("420x360")
        self.dialog.configure(bg='#1e1e1e')
        self.dialog.resizable(False, False)

        # đặt giữa màn hình
        self.dialog.update_idletasks()
        w = 420
        h = 360
        x = (self.dialog.winfo_screenwidth() // 2) - w // 2
        y = (self.dialog.winfo_screenheight() // 2) - h // 2
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.action_var = tk.StringVar(value="login")  # "login" hoặc "register"

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self.dialog, bg='#6c5ce7', height=80)
        header.pack(fill='x')
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="🐱 Chat App",
            bg='#6c5ce7',
            fg='white',
            font=('Segoe UI', 18, 'bold')
        )
        title.pack(pady=(10, 0))

        subtitle = tk.Label(
            header,
            text="Đăng nhập hoặc đăng kí để tiếp tục",
            bg='#6c5ce7',
            fg='white',
            font=('Segoe UI', 10)
        )
        subtitle.pack(pady=(0, 10))

        body = tk.Frame(self.dialog, bg='#1e1e1e')
        body.pack(fill='both', expand=True, padx=30, pady=20)

        # chọn chế độ
        mode_frame = tk.Frame(body, bg='#1e1e1e')
        mode_frame.pack(fill='x', pady=(0, 10))

        rb_login = tk.Radiobutton(
            mode_frame,
            text="Đăng nhập",
            variable=self.action_var,
            value="login",
            bg='#1e1e1e',
            fg='white',
            selectcolor='#1e1e1e',
            activebackground='#1e1e1e',
            font=('Segoe UI', 10)
        )
        rb_login.pack(side='left', padx=5)

        rb_register = tk.Radiobutton(
            mode_frame,
            text="Đăng kí",
            variable=self.action_var,
            value="register",
            bg='#1e1e1e',
            fg='white',
            selectcolor='#1e1e1e',
            activebackground='#1e1e1e',
            font=('Segoe UI', 10)
        )
        rb_register.pack(side='left', padx=5)

        # username
        user_frame = tk.Frame(body, bg='#2d2d2d')
        user_frame.pack(fill='x', pady=(5, 10))

        user_icon = tk.Label(user_frame, text="👤", bg='#2d2d2d', fg='white',
                             font=('Segoe UI', 14))
        user_icon.pack(side='left', padx=8)

        self.username_entry = tk.Entry(
            user_frame,
            bg='#2d2d2d',
            fg='white',
            relief='flat',
            font=('Segoe UI', 12),
            insertbackground='white'
        )
        self.username_entry.pack(side='left', fill='x', expand=True,
                                 padx=(0, 8), pady=8)

        # password
        pwd_frame = tk.Frame(body, bg='#2d2d2d')
        pwd_frame.pack(fill='x', pady=(0, 10))

        pwd_icon = tk.Label(pwd_frame, text="🔑", bg='#2d2d2d', fg='white',
                            font=('Segoe UI', 14))
        pwd_icon.pack(side='left', padx=8)

        self.password_entry = tk.Entry(
            pwd_frame,
            bg='#2d2d2d',
            fg='white',
            relief='flat',
            font=('Segoe UI', 12),
            insertbackground='white',
            show='*'
        )
        self.password_entry.pack(side='left', fill='x', expand=True,
                                 padx=(0, 8), pady=8)
        self.password_entry.bind('<Return>', lambda e: self.submit())

        # buttons
        btn_frame = tk.Frame(body, bg='#1e1e1e')
        btn_frame.pack(pady=20)

        ok_btn = tk.Button(
            btn_frame,
            text="Tiếp tục",
            command=self.submit,
            bg='#00cec9',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            relief='flat',
            padx=28,
            pady=8,
            cursor='hand2'
        )
        ok_btn.pack(side='left', padx=5)

        cancel_btn = tk.Button(
            btn_frame,
            text="Huỷ",
            command=self.cancel,
            bg='#d63031',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            relief='flat',
            padx=28,
            pady=8,
            cursor='hand2'
        )
        cancel_btn.pack(side='left', padx=5)

        self.username_entry.focus()

    def submit(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showwarning("Thiếu thông tin",
                                   "Vui lòng nhập đầy đủ tên và mật khẩu.")
            return

        self.result = {
            "username": username,
            "password": password,
            "action": self.action_var.get()
        }
        self.dialog.destroy()

    def cancel(self):
        self.result = None
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.result
