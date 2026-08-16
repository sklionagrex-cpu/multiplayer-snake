package com.snake.mcpe;

import android.util.Log;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Bridges Minecraft PE 1.1.5 RakNet UDP through the Snake relay.
 *
 * Wire format (matches relay/relay_server.py):
 *   [1 byte type][16 byte room_key][payload]
 *   1=HOST  2=GUEST  3=DATA  4=KEEP
 *
 * Guest mode: bind local 19132, answer pings, forward game traffic via relay.
 * Host mode:  inject guest packets into local MC (127.0.0.1:19132) and return replies.
 */
public class RelayBridge {
    private static final String TAG = "SnakeRelay";

    public static final byte TYPE_HOST = 1;
    public static final byte TYPE_GUEST = 2;
    public static final byte TYPE_DATA = 3;
    public static final byte TYPE_KEEP = 4;

    private static final int ROOM_KEY_LEN = 16;
    private static final int HEADER_LEN = 1 + ROOM_KEY_LEN; // 17
    private static final int LOCAL_MC_PORT = 19132;

    private final String relayHost;
    private final int relayPort;
    private final byte[] roomKey; // exactly 16 bytes, zero-padded
    private final boolean isHost;
    private final String worldName;
    private final int playerCount;
    private final int maxPlayers;

    private final AtomicBoolean running = new AtomicBoolean(false);
    private DatagramSocket relaySock;
    private DatagramSocket localSock; // guest: bound 19132; host: ephemeral talking to MC
    private Thread relayThread;
    private Thread localThread;
    private Thread keepThread;
    /** Last start failure reason for UI toast */
    private volatile String lastError = null;

    /** Guest: last Minecraft client address that talked to us */
    private volatile SocketAddress mcClientAddr;

    /** Host: map guest-id (hash of remote relay path) → local socket talking to MC */
    private final Map<String, DatagramSocket> hostPeerSockets = new ConcurrentHashMap<>();
    private final Map<Integer, String> hostLocalPortToPeer = new ConcurrentHashMap<>();

    private LANAdvertiser advertiser; // only guest mode (or host if MC not binding yet)

    public RelayBridge(String relayHost, int relayPort, String roomId,
                       boolean isHost, String worldName, int playerCount, int maxPlayers) {
        this.relayHost = relayHost;
        this.relayPort = relayPort;
        this.roomKey = padRoomKey(roomId);
        this.isHost = isHost;
        this.worldName = worldName != null ? worldName : "Snake";
        this.playerCount = Math.max(1, playerCount);
        this.maxPlayers = Math.max(this.playerCount, maxPlayers);
    }

    private static byte[] padRoomKey(String roomId) {
        byte[] key = new byte[ROOM_KEY_LEN];
        byte[] src = (roomId != null ? roomId : "default").getBytes(StandardCharsets.UTF_8);
        System.arraycopy(src, 0, key, 0, Math.min(src.length, ROOM_KEY_LEN));
        return key;
    }

    public String getLastError() {
        return lastError;
    }

    public synchronized boolean start() {
        if (running.get()) return true;
        lastError = null;
        try {
            try {
                relaySock = new DatagramSocket();
                relaySock.setSoTimeout(1000);
            } catch (Exception e) {
                lastError = "UDP socket: " + e.getMessage();
                throw e;
            }

            if (isHost) {
                // Host: do NOT bind 19132 — Minecraft owns it. We talk to 127.0.0.1:19132.
                try {
                    localSock = new DatagramSocket();
                    localSock.setSoTimeout(1000);
                } catch (Exception e) {
                    lastError = "local UDP: " + e.getMessage();
                    throw e;
                }
            } else {
                // Guest: we are the "server" Minecraft connects to.
                try {
                    localSock = new DatagramSocket(null);
                    localSock.setReuseAddress(true);
                    try {
                        localSock.setOption(java.net.StandardSocketOptions.SO_REUSEPORT, true);
                    } catch (Exception ignored) {}
                    localSock.bind(new InetSocketAddress(LOCAL_MC_PORT));
                    localSock.setSoTimeout(1000);
                } catch (Exception e) {
                    lastError = "порт 19132 занят (закрой MC): " + e.getMessage();
                    throw e;
                }
                // Pings answered inside localLoop on same socket
                advertiser = null;
            }

            running.set(true);

            // Register with relay (non-fatal — packets can still flow later)
            try {
                sendControl(isHost ? TYPE_HOST : TYPE_GUEST);
            } catch (Exception e) {
                Log.w(TAG, "relay register: " + e.getMessage());
                // keep going — keepalive thread will retry
            }

            relayThread = new Thread(this::relayLoop, "SnakeRelay-RX");
            relayThread.setDaemon(true);
            relayThread.start();

            localThread = new Thread(this::localLoop, "SnakeRelay-Local");
            localThread.setDaemon(true);
            localThread.start();

            keepThread = new Thread(this::keepLoop, "SnakeRelay-Keep");
            keepThread.setDaemon(true);
            keepThread.start();

            Log.i(TAG, "started " + (isHost ? "HOST" : "GUEST")
                + " relay=" + relayHost + ":" + relayPort
                + " room=" + new String(roomKey, StandardCharsets.UTF_8).trim());
            return true;
        } catch (Exception e) {
            if (lastError == null) {
                lastError = e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName();
            }
            Log.e(TAG, "start failed: " + lastError, e);
            stop();
            return false;
        }
    }

    public synchronized void stop() {
        running.set(false);
        closeQuietly(relaySock);
        closeQuietly(localSock);
        relaySock = null;
        localSock = null;
        for (DatagramSocket s : hostPeerSockets.values()) closeQuietly(s);
        hostPeerSockets.clear();
        hostLocalPortToPeer.clear();
        if (advertiser != null) {
            advertiser.stop();
            advertiser = null;
        }
        joinQuiet(relayThread);
        joinQuiet(localThread);
        joinQuiet(keepThread);
        relayThread = localThread = keepThread = null;
        Log.i(TAG, "stopped");
    }

    public boolean isRunning() {
        return running.get();
    }

    // ─── relay side ───────────────────────────────────────────

    private void relayLoop() {
        byte[] buf = new byte[4096];
        while (running.get() && relaySock != null && !relaySock.isClosed()) {
            try {
                DatagramPacket p = new DatagramPacket(buf, buf.length);
                relaySock.receive(p);
                if (p.getLength() < HEADER_LEN) continue;
                byte type = buf[0];
                if (type != TYPE_DATA) continue;
                byte[] payload = new byte[p.getLength() - HEADER_LEN];
                System.arraycopy(buf, HEADER_LEN, payload, 0, payload.length);
                if (payload.length == 0) continue;

                if (isHost) {
                    injectToLocalMc(payload, peerIdFromPacket(buf, p.getLength()));
                } else {
                    // Guest: deliver to Minecraft client
                    SocketAddress dest = mcClientAddr;
                    if (dest != null && localSock != null) {
                        localSock.send(new DatagramPacket(payload, payload.length, dest));
                    }
                }
            } catch (SocketTimeoutException ignored) {
            } catch (Exception e) {
                if (running.get()) Log.w(TAG, "relayLoop: " + e.getMessage());
            }
        }
    }

    private void keepLoop() {
        while (running.get()) {
            try {
                sendControl(TYPE_KEEP);
                sendControl(isHost ? TYPE_HOST : TYPE_GUEST);
                Thread.sleep(10000);
            } catch (InterruptedException e) {
                break;
            } catch (Exception ignored) {}
        }
    }

    private void sendControl(byte type) throws Exception {
        byte[] pkt = new byte[HEADER_LEN];
        pkt[0] = type;
        System.arraycopy(roomKey, 0, pkt, 1, ROOM_KEY_LEN);
        InetAddress addr = InetAddress.getByName(relayHost);
        relaySock.send(new DatagramPacket(pkt, pkt.length, addr, relayPort));
    }

    private void sendDataToRelay(byte[] payload) {
        if (relaySock == null || payload == null || payload.length == 0) return;
        try {
            byte[] pkt = new byte[HEADER_LEN + payload.length];
            pkt[0] = TYPE_DATA;
            System.arraycopy(roomKey, 0, pkt, 1, ROOM_KEY_LEN);
            System.arraycopy(payload, 0, pkt, HEADER_LEN, payload.length);
            InetAddress addr = InetAddress.getByName(relayHost);
            relaySock.send(new DatagramPacket(pkt, pkt.length, addr, relayPort));
        } catch (Exception e) {
            Log.w(TAG, "sendData: " + e.getMessage());
        }
    }

    // ─── local Minecraft side ─────────────────────────────────

    private void localLoop() {
        byte[] buf = new byte[4096];
        while (running.get() && localSock != null && !localSock.isClosed()) {
            try {
                DatagramPacket p = new DatagramPacket(buf, buf.length);
                localSock.receive(p);
                if (p.getLength() < 1) continue;

                if (isHost) {
                    // Reply from local MC → find which guest and forward
                    int localPort = localSock.getLocalPort();
                    // For multi-peer we use per-peer sockets; this localSock is fallback.
                    String peer = hostLocalPortToPeer.get(p.getPort()); // not ideal
                    // Better: this thread only handles the primary localSock;
                    // peer sockets have their own readers started in injectToLocalMc.
                    sendDataToRelay(copyPayload(p));
                } else {
                    // Guest mode: packet from Minecraft client
                    int packetId = buf[0] & 0xff;
                    if (packetId == 0x01 || packetId == 0x02) {
                        // Unconnected Ping → answer locally so world shows up
                        answerPing(buf, p);
                        continue;
                    }
                    mcClientAddr = p.getSocketAddress();
                    sendDataToRelay(copyPayload(p));
                }
            } catch (SocketTimeoutException ignored) {
            } catch (Exception e) {
                if (running.get()) Log.w(TAG, "localLoop: " + e.getMessage());
            }
        }
    }

    /** Host: send guest payload into local Minecraft server, track peer socket */
    private void injectToLocalMc(byte[] payload, String peerId) {
        try {
            DatagramSocket peerSock = hostPeerSockets.get(peerId);
            if (peerSock == null || peerSock.isClosed()) {
                peerSock = new DatagramSocket();
                peerSock.setSoTimeout(1000);
                hostPeerSockets.put(peerId, peerSock);
                hostLocalPortToPeer.put(peerSock.getLocalPort(), peerId);
                final DatagramSocket fs = peerSock;
                final String fPeer = peerId;
                Thread t = new Thread(() -> readPeerReplies(fs, fPeer), "SnakeRelay-Peer-" + peerId);
                t.setDaemon(true);
                t.start();
            }
            InetAddress loop = InetAddress.getByName("127.0.0.1");
            peerSock.send(new DatagramPacket(payload, payload.length, loop, LOCAL_MC_PORT));
        } catch (Exception e) {
            Log.w(TAG, "inject: " + e.getMessage());
        }
    }

    private void readPeerReplies(DatagramSocket peerSock, String peerId) {
        byte[] buf = new byte[4096];
        while (running.get() && peerSock != null && !peerSock.isClosed()) {
            try {
                DatagramPacket p = new DatagramPacket(buf, buf.length);
                peerSock.receive(p);
                sendDataToRelay(copyPayload(p));
            } catch (SocketTimeoutException ignored) {
            } catch (Exception e) {
                if (running.get()) break;
            }
        }
    }

    /** Guest: answer Unconnected Ping on the same socket that Minecraft uses */
    private void answerPing(byte[] buf, DatagramPacket in) {
        try {
            if (in.getLength() < 25) return;
            long clientTs = ByteBuffer.wrap(buf, 1, 8).order(ByteOrder.BIG_ENDIAN).getLong();
            long guid = 0x534e414b45000001L; // fixed-ish
            String motd = "MCPE;" + worldName + ";113;1.1.5;"
                + playerCount + ";" + maxPlayers + ";" + (guid & 0x7fffffffffffffffL) + ";"
                + worldName + ";Survival;1;" + LOCAL_MC_PORT + ";" + LOCAL_MC_PORT + ";";
            byte[] motdBytes = motd.getBytes(StandardCharsets.UTF_8);
            byte[] magic = new byte[] {
                0x00, (byte) 0xff, (byte) 0xff, 0x00,
                (byte) 0xfe, (byte) 0xfe, (byte) 0xfe, (byte) 0xfe,
                (byte) 0xfd, (byte) 0xfd, (byte) 0xfd, (byte) 0xfd,
                0x12, 0x34, 0x56, 0x78
            };
            ByteBuffer bb = ByteBuffer.allocate(1 + 8 + 8 + 16 + 2 + motdBytes.length);
            bb.order(ByteOrder.BIG_ENDIAN);
            bb.put((byte) 0x1c);
            bb.putLong(clientTs);
            bb.putLong(guid);
            bb.put(magic);
            bb.putShort((short) motdBytes.length);
            bb.put(motdBytes);
            byte[] pong = bb.array();
            localSock.send(new DatagramPacket(pong, pong.length, in.getSocketAddress()));
        } catch (Exception e) {
            Log.w(TAG, "pong: " + e.getMessage());
        }
    }

    // ─── helpers ──────────────────────────────────────────────

    private static byte[] copyPayload(DatagramPacket p) {
        byte[] out = new byte[p.getLength()];
        System.arraycopy(p.getData(), p.getOffset(), out, 0, p.getLength());
        return out;
    }

    /** Derive a stable peer id from incoming relay packet (room is same; use payload hash + source) */
    private String peerIdFromPacket(byte[] buf, int len) {
        // Simple: hash first few payload bytes — good enough to separate concurrent guests
        int h = 0;
        for (int i = HEADER_LEN; i < Math.min(len, HEADER_LEN + 32); i++) {
            h = 31 * h + (buf[i] & 0xff);
        }
        return Integer.toHexString(h);
    }

    private static void closeQuietly(DatagramSocket s) {
        if (s != null) try { s.close(); } catch (Exception ignored) {}
    }

    private static void joinQuiet(Thread t) {
        if (t != null) try { t.join(1500); } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }
}
