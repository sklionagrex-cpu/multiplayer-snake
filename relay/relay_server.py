#!/usr/bin/env python3
"""
UDP room relay for Multiplayer Snake (MCPE 1.1.5).
Peers join a room by first packet; relay forwards all subsequent UDP between members.

Wire format (first 4 bytes magic optional for future):
  Client may send plain RakNet datagrams after registering via control.

Simple mode:
  - Control TCP port CONTROL_PORT: line protocol
      HOST <room_id> <token>
      JOIN <room_id> <token>
    response: OK <udp_port> or ERR ...
  - Game UDP on GAME_PORT: first packet must be:
      b"SNK1" + room_id_utf8_len(1 byte) + room_id + payload
    After first packet, same source addr is bound to room; further packets
    from that addr are forwarded to other members (raw payload after header
    on first packet only; subsequent packets are raw).

For simplicity v1: all members of a room share the same UDP socket on server;
each packet is prefixed with 2-byte peer index assigned on join... 

Even simpler v1 used here:
  Packet: [1 byte type][16 byte room_key][payload]
  type 1 = register as host
  type 2 = register as guest  
  type 3 = data
  Server remembers addr per (room_key, role) and forwards type=3 to others in room.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from collections import defaultdict

HOST = "0.0.0.0"
PORT = 40000
ROOM_TTL = 600  # seconds idle

# room_key(str) -> { "host": (addr, last_seen), "guests": {addr: last_seen} }
rooms: dict = {}
lock = threading.Lock()

TYPE_HOST = 1
TYPE_GUEST = 2
TYPE_DATA = 3
TYPE_KEEP = 4


def room_key_from(buf: bytes) -> str | None:
    if len(buf) < 18:
        return None
    return buf[1:17].rstrip(b"\x00").decode("utf-8", errors="ignore") or None


def cleanup_loop(sock: socket.socket):
    while True:
        time.sleep(30)
        now = time.time()
        with lock:
            dead = []
            for k, r in rooms.items():
                last = 0
                if r.get("host"):
                    last = max(last, r["host"][1])
                for _, t in r.get("guests", {}).items():
                    last = max(last, t)
                if now - last > ROOM_TTL:
                    dead.append(k)
            for k in dead:
                del rooms[k]


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    print(f"Snake UDP relay on {HOST}:{PORT}", flush=True)
    threading.Thread(target=cleanup_loop, args=(sock,), daemon=True).start()

    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except Exception as e:
            print("recv error", e, flush=True)
            continue
        if len(data) < 18:
            continue
        typ = data[0]
        key = room_key_from(data)
        if not key:
            continue
        payload = data[17:]
        now = time.time()

        with lock:
            if key not in rooms:
                rooms[key] = {"host": None, "guests": {}}
            r = rooms[key]

            if typ == TYPE_HOST:
                r["host"] = (addr, now)
                continue
            if typ == TYPE_GUEST:
                r["guests"][addr] = now
                continue
            if typ == TYPE_KEEP:
                if r.get("host") and r["host"][0] == addr:
                    r["host"] = (addr, now)
                elif addr in r.get("guests", {}):
                    r["guests"][addr] = now
                continue
            if typ != TYPE_DATA:
                continue

            # refresh
            if r.get("host") and r["host"][0] == addr:
                r["host"] = (addr, now)
            elif addr in r.get("guests", {}):
                r["guests"][addr] = now
            else:
                # auto-register as guest on first data
                r["guests"][addr] = now

            targets = []
            if r.get("host") and r["host"][0] != addr:
                targets.append(r["host"][0])
            for gaddr in list(r.get("guests", {}).keys()):
                if gaddr != addr:
                    targets.append(gaddr)

        # forward payload with same header so peers can strip
        out = data  # full packet
        for t in targets:
            try:
                sock.sendto(out, t)
            except Exception:
                pass


if __name__ == "__main__":
    main()
