package com.snake.mcpe;

import android.util.Log;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Fake LAN advertiser for Minecraft PE 1.1.5 (protocol 113).
 * Listens UDP 19132 and answers Unconnected Ping (0x01/0x02) with Unconnected Pong (0x1c).
 * This makes a world appear in Play → Friends / LAN.
 */
public class LANAdvertiser {
    private static final String TAG = "SnakeLAN";
    private static final int DEFAULT_PORT = 19132;
    private static final int PROTOCOL_VERSION = 113;
    private static final String GAME_VERSION = "1.1.5";

    // RakNet magic
    private static final byte[] RAKNET_MAGIC = new byte[] {
        0x00, (byte) 0xff, (byte) 0xff, 0x00,
        (byte) 0xfe, (byte) 0xfe, (byte) 0xfe, (byte) 0xfe,
        (byte) 0xfd, (byte) 0xfd, (byte) 0xfd, (byte) 0xfd,
        0x12, 0x34, 0x56, 0x78
    };

    private String worldName;
    private int playerCount;
    private int maxPlayers;
    private final int port;
    private final long serverGuid;
    private DatagramSocket socket;
    private Thread thread;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicInteger pingsReceived = new AtomicInteger(0);

    public LANAdvertiser(String worldName, int playerCount, int maxPlayers) {
        this(worldName, playerCount, maxPlayers, DEFAULT_PORT);
    }

    public LANAdvertiser(String worldName, int playerCount, int maxPlayers, int port) {
        this.worldName = worldName != null ? worldName : "Multiplayer Snake";
        this.playerCount = Math.max(1, playerCount);
        this.maxPlayers = Math.max(this.playerCount, maxPlayers);
        this.port = port > 0 ? port : DEFAULT_PORT;
        this.serverGuid = new Random().nextLong();
    }

    public synchronized boolean start() {
        if (running.get()) return true;
        try {
            socket = new DatagramSocket(null);
            socket.setReuseAddress(true);
            try {
                // Best-effort on devices that support it
                socket.setOption(java.net.StandardSocketOptions.SO_REUSEPORT, true);
            } catch (Exception ignored) {}
            socket.bind(new InetSocketAddress(port));
            socket.setSoTimeout(1000);
            running.set(true);
            thread = new Thread(this::loop, "SnakeLANAdvertiser");
            thread.setDaemon(true);
            thread.start();
            Log.i(TAG, "LAN advertiser started on " + port + " name=" + worldName);
            return true;
        } catch (SocketException e) {
            Log.e(TAG, "Cannot bind " + port + ": " + e.getMessage());
            closeSocketQuietly();
            running.set(false);
            return false;
        } catch (Exception e) {
            Log.e(TAG, "start failed", e);
            closeSocketQuietly();
            running.set(false);
            return false;
        }
    }

    public synchronized void stop() {
        running.set(false);
        closeSocketQuietly();
        if (thread != null) {
            try {
                thread.join(1500);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            thread = null;
        }
        Log.i(TAG, "LAN advertiser stopped. pings=" + pingsReceived.get());
    }

    public boolean isRunning() {
        return running.get();
    }

    public int getPingsReceived() {
        return pingsReceived.get();
    }

    public void update(String worldName, Integer playerCount, Integer maxPlayers) {
        if (worldName != null) this.worldName = worldName;
        if (playerCount != null) this.playerCount = Math.max(1, playerCount);
        if (maxPlayers != null) this.maxPlayers = Math.max(this.playerCount, maxPlayers);
    }

    private void loop() {
        byte[] buf = new byte[2048];
        while (running.get() && socket != null && !socket.isClosed()) {
            try {
                DatagramPacket packet = new DatagramPacket(buf, buf.length);
                socket.receive(packet);
                if (packet.getLength() < 1) continue;
                int packetId = buf[0] & 0xff;
                // 0x01 Unconnected Ping, 0x02 Unconnected Ping Open Connections
                if (packetId != 0x01 && packetId != 0x02) continue;
                if (packet.getLength() < 25) continue; // id + ts(8) + magic(16)

                long clientTs = ByteBuffer.wrap(buf, 1, 8).order(ByteOrder.BIG_ENDIAN).getLong();
                pingsReceived.incrementAndGet();

                byte[] pong = buildUnconnectedPong(clientTs);
                DatagramPacket out = new DatagramPacket(
                    pong, pong.length, packet.getAddress(), packet.getPort());
                socket.send(out);
            } catch (java.net.SocketTimeoutException ignored) {
                // normal
            } catch (Exception e) {
                if (running.get()) {
                    Log.w(TAG, "recv/send: " + e.getMessage());
                }
                break;
            }
        }
    }

    private byte[] buildUnconnectedPong(long clientTimestamp) {
        // MCPE;name;protocol;version;online;max;guid;subname;mode;mode_num;port4;port6;
        String motd = "MCPE;" + worldName + ";" + PROTOCOL_VERSION + ";" + GAME_VERSION + ";"
            + playerCount + ";" + maxPlayers + ";" + (serverGuid & 0x7fffffffffffffffL) + ";"
            + worldName + ";Survival;1;" + port + ";" + port + ";";
        byte[] motdBytes = motd.getBytes(StandardCharsets.UTF_8);

        ByteBuffer bb = ByteBuffer.allocate(1 + 8 + 8 + 16 + 2 + motdBytes.length);
        bb.order(ByteOrder.BIG_ENDIAN);
        bb.put((byte) 0x1c);                 // Unconnected Pong
        bb.putLong(clientTimestamp);
        bb.putLong(serverGuid);
        bb.put(RAKNET_MAGIC);
        bb.putShort((short) motdBytes.length);
        bb.put(motdBytes);
        return bb.array();
    }

    private void closeSocketQuietly() {
        if (socket != null) {
            try {
                socket.close();
            } catch (Exception ignored) {}
            socket = null;
        }
    }
}
