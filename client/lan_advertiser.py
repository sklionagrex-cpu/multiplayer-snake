#!/usr/bin/env python3
"""
Фейковый LAN-рекламщик для Minecraft PE 1.1.5 (протокол 113).

Как работает:
- Слушает UDP 19132
- Отвечает на Unconnected Ping (0x01 / 0x02) пакетом Unconnected Pong (0x1c)
- Minecraft видит «локальный мир» во вкладке Друзья / LAN

Важно:
- Работает, когда устройства в одной сети (обычный Wi-Fi или виртуальная сеть: ZeroTier, Radmin и т.п.)
- Сам по себе не прокидывает трафик через интернет — для этого позже добавим прокси/туннель
"""

import socket
import struct
import threading
import time
import random
from typing import Optional

# RakNet Magic
RAKNET_MAGIC = bytes([
    0x00, 0xff, 0xff, 0x00,
    0xfe, 0xfe, 0xfe, 0xfe,
    0xfd, 0xfd, 0xfd, 0xfd,
    0x12, 0x34, 0x56, 0x78,
])

# Протокол Minecraft PE 1.1.5
PROTOCOL_VERSION = 113
GAME_VERSION = "1.1.5"


def build_unconnected_pong(
    client_timestamp: int,
    server_guid: int,
    world_name: str,
    player_count: int = 1,
    max_players: int = 5,
    port: int = 19132,
) -> bytes:
    """Собирает пакет Unconnected Pong (0x1c) для PE 1.1.5"""
    # Строка MOTD в формате Bedrock/MCPE
    # MCPE;название;протокол;версия;онлайн;макс;guid;подзаголовок;режим;режим_num;порт4;порт6;
    motd = (
        f"MCPE;{world_name};{PROTOCOL_VERSION};{GAME_VERSION};"
        f"{player_count};{max_players};{server_guid};"
        f"{world_name};Survival;1;{port};{port};"
    )
    motd_bytes = motd.encode("utf-8")

    packet = bytearray()
    packet.append(0x1c)  # Unconnected Pong
    packet += struct.pack(">Q", client_timestamp)  # timestamp из пинга
    packet += struct.pack(">Q", server_guid)       # GUID сервера
    packet += RAKNET_MAGIC
    packet += struct.pack(">H", len(motd_bytes))   # длина строки
    packet += motd_bytes
    return bytes(packet)


class LANAdvertiser:
    """
    Слушает пинги Minecraft и отвечает фейковым миром.
    Запускается в отдельном потоке.
    """

    def __init__(
        self,
        world_name: str = "Multiplayer Snake",
        player_count: int = 1,
        max_players: int = 5,
        port: int = 19132,
        bind_ip: str = "0.0.0.0",
    ):
        self.world_name = world_name
        self.player_count = player_count
        self.max_players = max_players
        self.port = port
        self.bind_ip = bind_ip
        self.server_guid = random.getrandbits(64)
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.pings_received = 0

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Чтобы можно было слушать на 19132 даже если Minecraft тоже пытается
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            self._sock.bind((self.bind_ip, self.port))
            self._sock.settimeout(1.0)
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True
        except OSError as e:
            print(f"[LAN] Не удалось занять порт {self.port}: {e}")
            print("[LAN] Возможно, порт уже занят Minecraft или другим процессом.")
            return False

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self):
        while self._running and self._sock:
            try:
                data, addr = self._sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                continue

            packet_id = data[0]
            # 0x01 = Unconnected Ping, 0x02 = Unconnected Ping Open Connections
            if packet_id not in (0x01, 0x02):
                continue

            if len(data) < 25:  # минимум: id + timestamp(8) + magic(16)
                continue

            # timestamp — следующие 8 байт
            client_ts = struct.unpack(">Q", data[1:9])[0]
            self.pings_received += 1

            pong = build_unconnected_pong(
                client_timestamp=client_ts,
                server_guid=self.server_guid,
                world_name=self.world_name,
                player_count=self.player_count,
                max_players=self.max_players,
                port=self.port,
            )
            try:
                self._sock.sendto(pong, addr)
            except OSError:
                pass

    def update(self, world_name: str = None, player_count: int = None, max_players: int = None):
        if world_name is not None:
            self.world_name = world_name
        if player_count is not None:
            self.player_count = player_count
        if max_players is not None:
            self.max_players = max_players


def test_advertiser():
    """Быстрый тест — запускает рекламу на 30 секунд"""
    print("Запуск LAN-рекламщика для теста (30 сек)...")
    print("Открой Minecraft PE 1.1.5 → Играть → Друзья / LAN")
    adv = LANAdvertiser(world_name="§aТест Multiplayer Snake", player_count=1, max_players=5)
    if not adv.start():
        return
    print(f"Реклама запущена. GUID={adv.server_guid}")
    try:
        for i in range(30):
            time.sleep(1)
            if i % 5 == 0:
                print(f"  ... пингов получено: {adv.pings_received}")
    except KeyboardInterrupt:
        pass
    adv.stop()
    print("Остановлено.")


if __name__ == "__main__":
    test_advertiser()
