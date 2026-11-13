import os
import json
import hashlib
import hmac
import time
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

Window.clearcolor = (0.05, 0.07, 0.09, 1)

VAULT_SIZE = 131072  # 128 KB
OFFSET_MASTER = 4096
OFFSET_DECOY = 69632
BLOCK_SIZE = 32768

class CryptoEngine:
    @staticmethod
    def get_vault_path():
        app = App.get_running_app()
        folder = app.user_data_dir if app else "."
        return os.path.join(folder, "vbn_fortress.dat")

    @staticmethod
    def derive_key(pin, salt):
        return hashlib.pbkdf2_hmac('sha256', pin.encode(), salt, 100000, dklen=32)

    @staticmethod
    def xor_stream(data, key):
        out = bytearray(len(data))
        counter = 0
        for i in range(0, len(data), 32):
            block_key = hmac.new(key, counter.to_bytes(8, 'big'), hashlib.sha256).digest()
            chunk = data[i:i+32]
            for j in range(len(chunk)):
                out[i+j] = chunk[j] ^ block_key[j]
            counter += 1
        return bytes(out)

    @classmethod
    def vault_exists(cls):
        return os.path.exists(cls.get_vault_path())

    @classmethod
    def init_vault(cls, master_pin, decoy_pin):
        container = bytearray(os.urandom(VAULT_SIZE))
        m_salt = os.urandom(16)
        d_salt = os.urandom(16)
        container[0:16] = m_salt
        container[16:32] = d_salt

        m_data = {"type": "MASTER", "balance": 0.0, "txs": []}
        d_data = {"type": "DECOY", "balance": 0.0, "txs": []}

        cls._write_slot(container, OFFSET_MASTER, cls.derive_key(master_pin, m_salt), m_data)
        cls._write_slot(container, OFFSET_DECOY, cls.derive_key(decoy_pin, d_salt), d_data)

        with open(cls.get_vault_path(), "wb") as f:
            f.write(container)

    @classmethod
    def _write_slot(cls, container, offset, key, data_dict):
        raw = json.dumps(data_dict).encode('utf-8')
        checksum = hashlib.sha256(raw).digest()[:8]
        payload = b"VBN1" + len(raw).to_bytes(4, 'big') + checksum + raw
        padded = payload + os.urandom(BLOCK_SIZE - len(payload))
        encrypted = cls.xor_stream(padded, key)
        container[offset:offset+BLOCK_SIZE] = encrypted

    @classmethod
    def unlock(cls, pin):
        path = cls.get_vault_path()
        if not os.path.exists(path):
            return None, None
        with open(path, "rb") as f:
            container = bytearray(f.read())
        if len(container) != VAULT_SIZE:
            return None, None

        m_salt = bytes(container[0:16])
        d_salt = bytes(container[16:32])

        for offset, salt in [(OFFSET_MASTER, m_salt), (OFFSET_DECOY, d_salt)]:
            key = cls.derive_key(pin, salt)
            dec = cls.xor_stream(bytes(container[offset:offset+BLOCK_SIZE]), key)
            if dec[:4] == b"VBN1":
                length = int.from_bytes(dec[4:8], 'big')
                if 0 < length < BLOCK_SIZE - 16:
                    checksum = dec[8:16]
                    raw = dec[16:16+length]
                    if hashlib.sha256(raw).digest()[:8] == checksum:
                        return json.loads(raw.decode('utf-8')), (offset, key)
        return None, None

    @classmethod
    def save_data(cls, slot_info, data_dict):
        offset, key = slot_info
        with open(cls.get_vault_path(), "rb") as f:
            container = bytearray(f.read())
        cls._write_slot(container, offset, key, data_dict)
        with open(cls.get_vault_path(), "wb") as f:
            f.write(container)

    @classmethod
    def destroy_vault(cls):
        path = cls.get_vault_path()
        if os.path.exists(path):
            with open(path, "wb") as f:
                f.write(os.urandom(VAULT_SIZE))
            os.remove(path)

class SetupScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=30, spacing=15)
        layout.add_widget(Label(text="VBN FORTRESS SETUP", font_size='24sp', bold=True, color=(0.35, 0.65, 1, 1)))
        layout.add_widget(Label(text="Create 128KB Dual-Vault Container", font_size='14sp', color=(0.6, 0.6, 0.6, 1)))

        self.m_pin = TextInput(hint_text="Master PIN (6-12 digits)", password=True, input_filter='int', multiline=False, font_size='18sp', size_hint_y=None, height=50)
        self.d_pin = TextInput(hint_text="Decoy PIN (6-12 digits)", password=True, input_filter='int', multiline=False, font_size='18sp', size_hint_y=None, height=50)
        self.status = Label(text="", color=(1, 0.3, 0.3, 1), font_size='14sp')

        btn = Button(text="INITIALIZE VAULTS", background_color=(0.14, 0.53, 0.21, 1), font_size='16sp', bold=True, size_hint_y=None, height=55)
        btn.bind(on_press=self.create_vaults)

        layout.add_widget(self.m_pin)
        layout.add_widget(self.d_pin)
        layout.add_widget(self.status)
        layout.add_widget(btn)
        self.add_widget(layout)

    def create_vaults(self, instance):
        mp, dp = self.m_pin.text.strip(), self.d_pin.text.strip()
        if not (6 <= len(mp) <= 12) or not (6 <= len(dp) <= 12):
            self.status.text = "Both PINs must be 6-12 digits!"
            return
        if mp == dp:
            self.status.text = "Master and Decoy PINs must differ!"
            return
        CryptoEngine.init_vault(mp, dp)
        self.m_pin.text = ""
        self.d_pin.text = ""
        self.manager.current = 'login'

class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=30, spacing=18)
        layout.add_widget(Label(text="VBN FORTRESS", font_size='28sp', bold=True, color=(0.35, 0.65, 1, 1)))
        layout.add_widget(Label(text="Enter Master or Decoy PIN", font_size='15sp', color=(0.6, 0.6, 0.6, 1)))

        self.pin_input = TextInput(hint_text="••••••", password=True, input_filter='int', multiline=False, halign='center', font_size='22sp', size_hint_y=None, height=55)
        self.status = Label(text="", color=(1, 0.3, 0.3, 1), font_size='14sp')

        btn = Button(text="UNLOCK VAULT", background_color=(0.14, 0.53, 0.21, 1), font_size='17sp', bold=True, size_hint_y=None, height=55)
        btn.bind(on_press=self.do_unlock)

        layout.add_widget(self.pin_input)
        layout.add_widget(self.status)
        layout.add_widget(btn)
        self.add_widget(layout)

    def do_unlock(self, instance):
        pin = self.pin_input.text.strip()
        self.pin_input.text = ""
        data, slot_info = CryptoEngine.unlock(pin)
        if data is None:
            self.status.text = "Invalid PIN or Corrupted Vault!"
            return
        self.status.text = ""
        dash = self.manager.get_screen('dashboard')
        dash.load_vault(data, slot_info)
        self.manager.current = 'dashboard'

class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = None
        self.slot_info = None
        layout = BoxLayout(orientation='vertical', padding=20, spacing=12)

        self.header = Label(text="", font_size='18sp', bold=True, size_hint_y=None, height=40)
        self.balance_lbl = Label(text="0.00 VBN", font_size='30sp', bold=True, color=(0.25, 0.73, 0.31, 1), size_hint_y=None, height=60)

        row = BoxLayout(spacing=10, size_hint_y=None, height=50)
        self.amt_input = TextInput(hint_text="Amount", input_filter='float', multiline=False, font_size='16sp')
        add_btn = Button(text="+ DEPOSIT", background_color=(0.14, 0.53, 0.21, 1), bold=True)
        add_btn.bind(on_press=self.deposit)
        sub_btn = Button(text="- SEND", background_color=(0.8, 0.5, 0.1, 1), bold=True)
        sub_btn.bind(on_press=self.withdraw)
        row.add_widget(self.amt_input)
        row.add_widget(add_btn)
        row.add_widget(sub_btn)

        self.tx_list = Label(text="", size_hint_y=None, halign='left', valign='top', font_size='13sp', color=(0.8, 0.8, 0.8, 1))
        self.tx_list.bind(texture_size=self.tx_list.setter('size'))
        scroll = ScrollView()
        scroll.add_widget(self.tx_list)

        lock_btn = Button(text="LOCK & WIPE RAM", background_color=(0.85, 0.21, 0.2, 1), bold=True, size_hint_y=None, height=50)
        lock_btn.bind(on_press=self.lock_vault)

        destroy_btn = Button(text="DESTROY VAULT PERMANENTLY", background_color=(0.4, 0.1, 0.1, 1), font_size='12sp', size_hint_y=None, height=40)
        destroy_btn.bind(on_press=self.destroy_all)

        layout.add_widget(self.header)
        layout.add_widget(self.balance_lbl)
        layout.add_widget(row)
        layout.add_widget(scroll)
        layout.add_widget(lock_btn)
        layout.add_widget(destroy_btn)
        self.add_widget(layout)

    def load_vault(self, data, slot_info):
        self.data = data
        self.slot_info = slot_info
        self.refresh_ui()

    def refresh_ui(self):
        v_type = self.data.get("type", "VAULT")
        self.header.text = f"[{v_type} MODE ACTIVE]"
        self.header.color = (0.25, 0.73, 0.31, 1) if v_type == "MASTER" else (0.85, 0.65, 0.13, 1)
        self.balance_lbl.text = f"{self.data.get('balance', 0.0):.2f} VBN"
        txs = self.data.get("txs", [])[-10:]
        lines = [f"{t['time']} | {t['type']} | {t['amount']} | #{t['hash']}" for t in reversed(txs)]
        self.tx_list.text = "\n".join(lines) if lines else "No transactions yet."

    def record_tx(self, tx_type, amount):
        tx_hash = hashlib.sha256(f"{time.time()}{amount}".encode()).hexdigest()[:8]
        self.data["txs"].append({
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "type": tx_type,

```bash
cat << 'EOF' > ~/vbn_app/buildozer.spec
[app]
title = VBN Fortress
package.name = vbnfortress
package.domain = org.vbn.security
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.0
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.archs = arm64-v8a
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
