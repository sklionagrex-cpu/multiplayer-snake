
"""Multiplayer Snake"""
import json, os
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import Snackbar

API_URL = os.environ.get("API_URL", "https://snake-master-3pzr.onrender.com")
TOKEN_FILE = "token.json"

KV = """
MDScreenManager:
    LoginScreen:
    RegisterScreen:
    WorldsScreen:
    HostScreen:

<LoginScreen>:
    name: "login"
    md_bg_color: app.bg
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(28)
        spacing: dp(16)
        MDLabel:
            text: "Multiplayer Snake"
            font_style: "H5"
            bold: True
            halign: "center"
            theme_text_color: "Custom"
            text_color: app.accent
            size_hint_y: None
            height: dp(48)
        MDLabel:
            text: "Minecraft PE 1.1.5"
            font_style: "Caption"
            halign: "center"
            theme_text_color: "Hint"
            size_hint_y: None
            height: dp(24)
        MDTextField:
            id: username
            hint_text: "Ник"
            mode: "rectangle"
            line_color_focus: app.accent
        MDTextField:
            id: password
            hint_text: "Пароль"
            password: True
            mode: "rectangle"
            line_color_focus: app.accent
        MDRaisedButton:
            text: "ВОЙТИ"
            pos_hint: {"center_x": 0.5}
            md_bg_color: app.accent
            on_release: app.do_login(username.text, password.text)
        MDFlatButton:
            text: "Регистрация"
            pos_hint: {"center_x": 0.5}
            theme_text_color: "Custom"
            text_color: app.accent
            on_release: root.manager.current = "register"
        MDLabel:
            id: status
            text: ""
            halign: "center"
            theme_text_color: "Error"
            size_hint_y: None
            height: dp(28)

<RegisterScreen>:
    name: "register"
    md_bg_color: app.bg
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(28)
        spacing: dp(14)
        MDLabel:
            text: "Регистрация"
            font_style: "H5"
            bold: True
            halign: "center"
            theme_text_color: "Custom"
            text_color: app.accent
            size_hint_y: None
            height: dp(48)
        MDTextField:
            id: username
            hint_text: "Ник"
            mode: "rectangle"
            line_color_focus: app.accent
        MDTextField:
            id: password
            hint_text: "Пароль"
            password: True
            mode: "rectangle"
            line_color_focus: app.accent
        MDTextField:
            id: password2
            hint_text: "Повтори пароль"
            password: True
            mode: "rectangle"
            line_color_focus: app.accent
        MDRaisedButton:
            text: "СОЗДАТЬ"
            pos_hint: {"center_x": 0.5}
            md_bg_color: app.accent
            on_release: app.do_register(username.text, password.text, password2.text)
        MDFlatButton:
            text: "Назад"
            pos_hint: {"center_x": 0.5}
            on_release: root.manager.current = "login"
        MDLabel:
            id: status
            text: ""
            halign: "center"
            theme_text_color: "Error"
            size_hint_y: None
            height: dp(28)

<WorldsScreen>:
    name: "worlds"
    md_bg_color: app.bg
    MDBoxLayout:
        orientation: "vertical"
        MDTopAppBar:
            title: "Миры"
            elevation: 2
            md_bg_color: app.bar
            specific_text_color: app.accent
            right_action_items: [["refresh", lambda x: app.load_worlds()], ["logout", lambda x: app.logout()]]
        MDLabel:
            id: subtitle
            text: "..."
            font_style: "Caption"
            halign: "center"
            size_hint_y: None
            height: dp(28)
            theme_text_color: "Hint"
        MDScrollView:
            MDList:
                id: world_list
                padding: dp(12)
                spacing: dp(10)
        MDBoxLayout:
            size_hint_y: None
            height: dp(72)
            padding: dp(12)
            MDRaisedButton:
                text: "+ ОТКРЫТЬ МИР"
                pos_hint: {"center_x": 0.5}
                md_bg_color: app.accent
                on_release: root.manager.current = "host"

<HostScreen>:
    name: "host"
    md_bg_color: app.bg
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(24)
        spacing: dp(14)
        MDTopAppBar:
            title: "Хост"
            elevation: 2
            md_bg_color: app.bar
            left_action_items: [["arrow-left", lambda x: app.go_worlds()]]
        MDTextField:
            id: name
            hint_text: "Название мира"
            mode: "rectangle"
            line_color_focus: app.accent
        MDTextField:
            id: description
            hint_text: "Описание"
            mode: "rectangle"
            line_color_focus: app.accent
        MDTextField:
            id: max_players
            hint_text: "Макс. игроков"
            text: "5"
            input_filter: "int"
            mode: "rectangle"
            line_color_focus: app.accent
        MDRaisedButton:
            text: "ОТКРЫТЬ"
            pos_hint: {"center_x": 0.5}
            md_bg_color: app.accent
            on_release: app.do_host(name.text, description.text, max_players.text)
        MDLabel:
            id: status
            text: ""
            halign: "center"
            size_hint_y: None
            height: dp(40)
"""

class LoginScreen(MDScreen):
    pass

class RegisterScreen(MDScreen):
    pass

class WorldsScreen(MDScreen):
    pass

class HostScreen(MDScreen):
    pass

class WorldCard(MDCard):
    def __init__(self, world, on_join, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = dp(14)
        self.spacing = dp(6)
        self.size_hint_y = None
        self.height = dp(120)
        self.radius = [16]
        self.md_bg_color = (0.12, 0.18, 0.12, 1)
        self.ripple_behavior = True
        self.add_widget(MDLabel(text=world.get("name", "?"), bold=True, font_style="Subtitle1", theme_text_color="Custom", text_color=(0.4, 0.9, 0.45, 1), size_hint_y=None, height=dp(28)))
        self.add_widget(MDLabel(text=(world.get("description") or "-")[:80], font_style="Caption", theme_text_color="Hint", size_hint_y=None, height=dp(22)))
        self.add_widget(MDLabel(text="Host: %s · %s/%s" % (world.get("owner_username", "?"), world.get("player_count", 0), world.get("max_players", 5)), font_style="Caption", theme_text_color="Secondary", size_hint_y=None, height=dp(20)))
        self.add_widget(MDRaisedButton(text="PLAY", md_bg_color=(0.2, 0.7, 0.3, 1), size_hint=(None, None), size=(dp(100), dp(36)), pos_hint={"right": 1}, on_release=lambda x, w=world: on_join(w)))

class SnakeApp(MDApp):
    bg = (0.07, 0.10, 0.07, 1)
    bar = (0.10, 0.14, 0.10, 1)
    accent = (0.35, 0.85, 0.40, 1)
    token = None
    user = None

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Green"
        self.title = "Multiplayer Snake"
        return Builder.load_string(KV)

    def on_start(self):
        self.load_token()
        if self.token:
            self.root.current = "worlds"
            Clock.schedule_once(lambda dt: self.load_worlds(), 0.3)

    def save_token(self, token, user):
        self.token = token
        self.user = user
        try:
            open(TOKEN_FILE, "w", encoding="utf-8").write(json.dumps({"token": token, "user": user}))
        except Exception:
            pass

    def load_token(self):
        try:
            if os.path.exists(TOKEN_FILE):
                data = json.load(open(TOKEN_FILE, encoding="utf-8"))
                self.token = data.get("token")
                self.user = data.get("user")
        except Exception:
            self.token = None

    def logout(self):
        self.token = None
        self.user = None
        try:
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
        except Exception:
            pass
        self.root.current = "login"

    def go_worlds(self):
        self.root.current = "worlds"
        self.load_worlds()

    def _api(self, method, path, json_data=None):
        import requests
        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        url = API_URL.rstrip("/") + path
        try:
            if method == "GET":
                r = requests.get(url, headers=headers, timeout=20)
            elif method == "POST":
                r = requests.post(url, headers=headers, json=json_data, timeout=20)
            else:
                r = requests.delete(url, headers=headers, timeout=20)
            return r, None
        except Exception as e:
            return None, str(e)

    def do_login(self, username, password):
        screen = self.root.get_screen("login")
        screen.ids.status.text = "..."
        def work(dt):
            r, err = self._api("POST", "/login", {"username": username.strip(), "password": password})
            if err:
                screen.ids.status.text = "No connection"
                return
            if r.status_code != 200:
                try:
                    screen.ids.status.text = str(r.json().get("detail", "Error"))
                except Exception:
                    screen.ids.status.text = "Error"
                return
            data = r.json()
            self.save_token(data["access_token"], data["user"])
            screen.ids.status.text = ""
            self.root.current = "worlds"
            self.load_worlds()
        Clock.schedule_once(work, 0.05)

    def do_register(self, username, password, password2):
        screen = self.root.get_screen("register")
        if password != password2:
            screen.ids.status.text = "Passwords differ"
            return
        screen.ids.status.text = "..."
        def work(dt):
            r, err = self._api("POST", "/register", {"username": username.strip(), "password": password})
            if err:
                screen.ids.status.text = "No connection"
                return
            if r.status_code != 200:
                try:
                    screen.ids.status.text = str(r.json().get("detail", "Error"))
                except Exception:
                    screen.ids.status.text = "Error"
                return
            data = r.json()
            self.save_token(data["access_token"], data["user"])
            self.root.current = "worlds"
            self.load_worlds()
        Clock.schedule_once(work, 0.05)

    def load_worlds(self):
        screen = self.root.get_screen("worlds")
        screen.ids.subtitle.text = "..."
        lst = screen.ids.world_list
        lst.clear_widgets()
        def work(dt):
            r, err = self._api("GET", "/worlds")
            if err:
                screen.ids.subtitle.text = "No connection"
                return
            if r.status_code != 200:
                screen.ids.subtitle.text = "Load error"
                return
            worlds = r.json()
            screen.ids.subtitle.text = ("Worlds: %d" % len(worlds)) if worlds else "No worlds"
            for w in worlds:
                lst.add_widget(WorldCard(w, on_join=self.join_world))
        Clock.schedule_once(work, 0.05)

    def join_world(self, world):
        Snackbar(text="Open MCPE 1.1.5 -> Friends/LAN: " + world.get("name", ""), duration=4).open()

    def do_host(self, name, description, max_players):
        screen = self.root.get_screen("host")
        if not name.strip():
            screen.ids.status.text = "Name required"
            return
        screen.ids.status.text = "..."
        def work(dt):
            try:
                mp = int(max_players or 5)
            except ValueError:
                mp = 5
            r, err = self._api("POST", "/worlds", {"name": name.strip(), "description": (description or "").strip(), "max_players": mp})
            if err:
                screen.ids.status.text = "No connection"
                return
            if r.status_code != 200:
                try:
                    screen.ids.status.text = str(r.json().get("detail", "Error"))
                except Exception:
                    screen.ids.status.text = "Error"
                return
            screen.ids.status.text = ""
            self.root.current = "worlds"
            self.load_worlds()
            Snackbar(text="World opened. Enable LAN in MCPE 1.1.5", duration=4).open()
        Clock.schedule_once(work, 0.05)

if __name__ == "__main__":
    SnakeApp().run()
