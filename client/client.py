#!/usr/bin/env python3
"""
Multiplayer Snake — клиент для Minecraft PE 1.1.5
Работает в Termux и на ПК
"""

import json
import os
import sys
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box

from config import API_URL, TOKEN_FILE
from lan_advertiser import LANAdvertiser

console = Console()

# Глобальный рекламщик (один на процесс)
_advertiser: LANAdvertiser | None = None


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def save_token(token: str, user: dict):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "user": user}, f, ensure_ascii=False, indent=2)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None, None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("token"), data.get("user")
    except Exception:
        return None, None


def delete_token():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


def api(method: str, path: str, token: str = None, json_data: dict = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{API_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=15)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=json_data, timeout=15)
        elif method == "PATCH":
            r = requests.patch(url, headers=headers, json=json_data, timeout=15)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=15)
        else:
            return None, "Неизвестный метод"
        return r, None
    except requests.exceptions.ConnectionError:
        return None, "Нет соединения с сервером. Проверь, запущен ли бэкенд."
    except Exception as e:
        return None, str(e)


# ==================== ЭКРАНЫ ====================

def screen_welcome():
    clear()
    console.print(Panel.fit(
        "[bold cyan]Multiplayer Snake[/bold cyan]\n"
        "[dim]Лаунчер мультиплеера для Minecraft PE 1.1.5[/dim]",
        border_style="cyan",
    ))
    console.print()
    console.print("1. Войти")
    console.print("2. Зарегистрироваться")
    console.print("0. Выход")
    console.print()
    return Prompt.ask("Выбор", choices=["0", "1", "2"], default="1")


def screen_register():
    clear()
    console.print(Panel("[bold]Регистрация[/bold]", border_style="green"))
    username = Prompt.ask("Ник (от 3 символов)")
    password = Prompt.ask("Пароль (от 4 символов)", password=True)
    password2 = Prompt.ask("Повтори пароль", password=True)

    if password != password2:
        console.print("[red]Пароли не совпадают[/red]")
        Prompt.ask("Нажми Enter...")
        return None, None

    r, err = api("POST", "/register", json_data={"username": username, "password": password})
    if err:
        console.print(f"[red]Ошибка: {err}[/red]")
        Prompt.ask("Нажми Enter...")
        return None, None

    if r.status_code != 200:
        detail = r.json().get("detail", r.text)
        console.print(f"[red]Ошибка: {detail}[/red]")
        Prompt.ask("Нажми Enter...")
        return None, None

    data = r.json()
    save_token(data["access_token"], data["user"])
    console.print(f"[green]Успешно! Добро пожаловать, {data['user']['username']}[/green]")
    Prompt.ask("Нажми Enter...")
    return data["access_token"], data["user"]


def screen_login():
    clear()
    console.print(Panel("[bold]Вход[/bold]", border_style="blue"))
    username = Prompt.ask("Ник")
    password = Prompt.ask("Пароль", password=True)

    r, err = api("POST", "/login", json_data={"username": username, "password": password})
    if err:
        console.print(f"[red]Ошибка: {err}[/red]")
        Prompt.ask("Нажми Enter...")
        return None, None

    if r.status_code != 200:
        detail = r.json().get("detail", r.text)
        console.print(f"[red]Ошибка: {detail}[/red]")
        Prompt.ask("Нажми Enter...")
        return None, None

    data = r.json()
    save_token(data["access_token"], data["user"])
    console.print(f"[green]Успешно! Привет, {data['user']['username']}[/green]")
    Prompt.ask("Нажми Enter...")
    return data["access_token"], data["user"]


def screen_worlds(token: str, user: dict):
    while True:
        clear()
        console.print(Panel(
            f"[bold cyan]Multiplayer Snake[/bold cyan]  |  Игрок: [bold]{user['username']}[/bold]",
            border_style="cyan",
        ))

        r, err = api("GET", "/worlds", token=token)
        if err:
            console.print(f"[red]{err}[/red]")
            Prompt.ask("Нажми Enter...")
            return

        worlds = r.json() if r.status_code == 200 else []

        if not worlds:
            console.print("\n[dim]Сейчас нет открытых миров[/dim]\n")
        else:
            table = Table(title="Открытые миры", box=box.ROUNDED, show_lines=True)
            table.add_column("№", style="dim", width=4)
            table.add_column("Название", style="cyan", min_width=16)
            table.add_column("Описание", min_width=20)
            table.add_column("Хост", style="green")
            table.add_column("Игроки", justify="center")

            for i, w in enumerate(worlds, 1):
                table.add_row(
                    str(i),
                    w["name"],
                    (w["description"] or "—")[:40],
                    w["owner_username"],
                    f"{w['player_count']}/{w['max_players']}",
                )
            console.print(table)

        console.print()
        console.print("[bold]Действия:[/bold]")
        console.print("  [cyan]номер[/cyan] — присоединиться к миру")
        console.print("  [cyan]h[/cyan]     — стать хостом (открыть свой мир)")
        console.print("  [cyan]r[/cyan]     — обновить список")
        console.print("  [cyan]q[/cyan]     — выйти из аккаунта")
        console.print()

        choice = Prompt.ask("Выбор").strip().lower()

        if choice == "q":
            delete_token()
            return
        if choice == "r":
            continue
        if choice == "h":
            screen_host(token, user)
            continue

        # Попытка присоединиться по номеру
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(worlds):
                screen_join(worlds[idx], token, user)
            else:
                console.print("[red]Нет такого мира[/red]")
                Prompt.ask("Нажми Enter...")
        else:
            console.print("[red]Неизвестная команда[/red]")
            Prompt.ask("Нажми Enter...")


def screen_host(token: str, user: dict):
    global _advertiser
    clear()
    console.print(Panel("[bold]Открыть мир (стать хостом)[/bold]", border_style="green"))
    name = Prompt.ask("Название мира")
    description = Prompt.ask("Описание (можно пустое)", default="")
    max_players = Prompt.ask("Макс. игроков", default="5")

    try:
        max_players = int(max_players)
    except ValueError:
        max_players = 5

    r, err = api("POST", "/worlds", token=token, json_data={
        "name": name,
        "description": description,
        "max_players": max_players,
    })

    if err:
        console.print(f"[red]{err}[/red]")
        Prompt.ask("Нажми Enter...")
        return

    if r.status_code != 200:
        console.print(f"[red]Ошибка: {r.json().get('detail', r.text)}[/red]")
        Prompt.ask("Нажми Enter...")
        return

    world = r.json()
    console.print()
    console.print(f"[green]Мир «{world['name']}» открыт в базе![/green]")

    # Запускаем LAN-рекламу (чтобы другие в той же сети видели мир)
    if _advertiser:
        _advertiser.stop()
    _advertiser = LANAdvertiser(
        world_name=name,
        player_count=1,
        max_players=max_players,
    )
    if _advertiser.start():
        console.print("[green]LAN-реклама запущена.[/green]")
        console.print("[dim]Другие игроки в той же сети (Wi-Fi / ZeroTier / Radmin) должны увидеть мир в Друзьях.[/dim]")
    else:
        console.print("[yellow]Не удалось запустить LAN-рекламу (порт 19132 занят?).[/yellow]")
        console.print("[dim]Закрой Minecraft и попробуй снова, либо используй виртуальную сеть.[/dim]")

    console.print()
    console.print("[bold]Что делать дальше:[/bold]")
    console.print("  1. Открой Minecraft PE 1.1.5")
    console.print("  2. Создай/открой свой мир и включи «Visible to LAN Players»")
    console.print("  3. Друзья (в той же сети) должны увидеть мир в списке Друзей")
    console.print()
    console.print("Когда закончишь — нажми Enter, чтобы закрыть мир и остановить рекламу.")
    Prompt.ask("Нажми Enter...")

    # Закрываем мир
    api("DELETE", f"/worlds/{world['id']}", token=token)
    if _advertiser:
        _advertiser.stop()
        _advertiser = None
    console.print("[dim]Мир закрыт, реклама остановлена.[/dim]")


def screen_join(world: dict, token: str, user: dict):
    global _advertiser
    clear()
    console.print(Panel(
        f"[bold]Присоединиться к миру[/bold]\n\n"
        f"Название: [cyan]{world['name']}[/cyan]\n"
        f"Описание: {world['description'] or '—'}\n"
        f"Хост: [green]{world['owner_username']}[/green]\n"
        f"Игроки: {world['player_count']}/{world['max_players']}",
        border_style="cyan",
    ))
    console.print()

    # Запускаем фейковый LAN, чтобы мир появился в Друзьях
    if _advertiser:
        _advertiser.stop()
    _advertiser = LANAdvertiser(
        world_name=world["name"],
        player_count=world.get("player_count", 1),
        max_players=world.get("max_players", 5),
    )
    ok = _advertiser.start()

    if ok:
        console.print("[green]✓ Фейковый LAN запущен![/green]")
        console.print()
        console.print("[bold]Что делать:[/bold]")
        console.print("  1. Открой [cyan]Minecraft PE 1.1.5[/cyan]")
        console.print("  2. Зайди в [cyan]Играть → Друзья / LAN[/cyan]")
        console.print(f"  3. Должен появиться мир: [cyan]{world['name']}[/cyan]")
        console.print("  4. Нажми на него, чтобы зайти")
        console.print()
        console.print("[yellow]Важно:[/yellow]")
        console.print("  • Ты и хост должны быть в [bold]одной сети[/bold]")
        console.print("    (один Wi-Fi или виртуальная сеть: ZeroTier / Radmin / Hamachi)")
        console.print("  • Если порт 19132 занят — закрой Minecraft и запусти клиент снова")
        console.print()
        console.print(f"[dim]Пингов получено: будет обновляться...[/dim]")
    else:
        console.print("[red]Не удалось занять порт 19132.[/red]")
        console.print("Закрой Minecraft PE и попробуй снова.")

    console.print()
    Prompt.ask("Когда закончишь играть — нажми Enter, чтобы остановить рекламу...")

    if _advertiser:
        console.print(f"[dim]Всего пингов от Minecraft: {_advertiser.pings_received}[/dim]")
        _advertiser.stop()
        _advertiser = None


# ==================== MAIN ====================

def main():
    token, user = load_token()

    while True:
        if token and user:
            # Проверяем, что токен ещё жив
            r, err = api("GET", "/me", token=token)
            if err or r.status_code != 200:
                delete_token()
                token, user = None, None
            else:
                user = r.json()
                screen_worlds(token, user)
                token, user = load_token()  # мог разлогиниться
                continue

        choice = screen_welcome()
        if choice == "0":
            console.print("Пока!")
            sys.exit(0)
        elif choice == "1":
            token, user = screen_login()
        elif choice == "2":
            token, user = screen_register()


if __name__ == "__main__":
    main()
