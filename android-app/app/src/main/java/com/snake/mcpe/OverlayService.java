package com.snake.mcpe;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.core.app.NotificationCompat;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

/**
 * Floating button over Minecraft.
 * Tap = compact native modals (servers / host players), NOT the launcher.
 * Drag down = dismiss.
 */
public class OverlayService extends Service {
    private WindowManager windowManager;
    private ImageView fab;
    private LinearLayout modalRoot;
    private WindowManager.LayoutParams fabParams;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private static final String CHANNEL_ID = "snake_overlay";
    private static final String CHANNEL_FRIEND = "snake_friend_host";
    private static final String PREFS = "snake_prefs";
    private Runnable friendPoll;
    private final Set<Integer> knownHostWorldIds = new HashSet<>();

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannels();
        startForeground(1, buildOngoingNotification());
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        addFab();
        startFriendHostPolling();
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private String apiBase() {
        return prefs().getString("api_url", "https://snake-master-3pzr.onrender.com");
    }

    private String token() {
        return prefs().getString("token", "");
    }

    private void addFab() {
        fab = new ImageView(this);
        fab.setImageResource(R.mipmap.ic_launcher);
        fab.setScaleType(ImageView.ScaleType.CENTER_CROP);
        fab.setAlpha(0.5f);

        float density = getResources().getDisplayMetrics().density;
        int size = (int) (48 * density);
        fabParams = new WindowManager.LayoutParams(
            size, size,
            overlayType(),
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        );
        fabParams.gravity = Gravity.TOP | Gravity.END;
        fabParams.x = 24;
        fabParams.y = 180;

        final int screenH = getResources().getDisplayMetrics().heightPixels;
        final int screenW = getResources().getDisplayMetrics().widthPixels;

        fab.setOnTouchListener(new View.OnTouchListener() {
            private int initialX, initialY;
            private float touchX, touchY;
            private boolean moved;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = fabParams.x;
                        initialY = fabParams.y;
                        touchX = event.getRawX();
                        touchY = event.getRawY();
                        moved = false;
                        return true;
                    case MotionEvent.ACTION_MOVE: {
                        float dx = event.getRawX() - touchX;
                        float dy = event.getRawY() - touchY;
                        if (Math.abs(dx) > 8 || Math.abs(dy) > 8) moved = true;
                        fabParams.x = initialX - (int) dx;
                        fabParams.y = initialY + (int) dy;
                        float progress = Math.min(1f, Math.max(0f, (float) fabParams.y / (screenH * 0.75f)));
                        v.setAlpha(0.5f * (1f - progress * 0.7f));
                        try { windowManager.updateViewLayout(fab, fabParams); } catch (Exception ignored) {}
                        return true;
                    }
                    case MotionEvent.ACTION_UP:
                        if (fabParams.y > screenH * 0.72f) {
                            stopSelf();
                            return true;
                        }
                        v.setAlpha(0.5f);
                        if (!moved) {
                            if (modalRoot != null) closeModal();
                            else openCorrectPanel(screenW);
                        }
                        return true;
                    default:
                        return false;
                }
            }
        });

        try {
            windowManager.addView(fab, fabParams);
        } catch (Exception e) {
            stopSelf();
        }
    }

    private int overlayType() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            : WindowManager.LayoutParams.TYPE_PHONE;
    }

    private GradientDrawable cardBg() {
        GradientDrawable d = new GradientDrawable();
        d.setColor(Color.parseColor("#F0121F12"));
        d.setCornerRadius(dp(16));
        d.setStroke(dp(1), Color.parseColor("#243324"));
        return d;
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private void closeModal() {
        if (modalRoot != null && windowManager != null) {
            try { windowManager.removeView(modalRoot); } catch (Exception ignored) {}
        }
        modalRoot = null;
        if (fab != null) {
            fab.setVisibility(View.VISIBLE);
            fab.setAlpha(0.5f);
        }
    }

    private void attachModal(LinearLayout content, int screenW) {
        closeModal();
        modalRoot = new LinearLayout(this);
        modalRoot.setOrientation(LinearLayout.VERTICAL);
        modalRoot.setPadding(dp(12), dp(16), dp(12), dp(16));
        modalRoot.setBackground(cardBg());

        // Right vertical drawer ~35% width, full height
        int width = Math.max(dp(140), (int) (screenW * 0.35f));
        int height = getResources().getDisplayMetrics().heightPixels;
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
            width,
            height,
            overlayType(),
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        );
        lp.gravity = Gravity.TOP | Gravity.END;

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        modalRoot.addView(scroll, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.MATCH_PARENT));

        try {
            windowManager.addView(modalRoot, lp);
            if (fab != null) fab.setVisibility(View.GONE);
        } catch (Exception e) {
            modalRoot = null;
            toast("Не удалось открыть панель");
        }
    }

    private TextView title(String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(Color.parseColor("#4ade80"));
        t.setTextSize(17);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(0, 0, 0, dp(10));
        return t;
    }

    private TextView muted(String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(Color.parseColor("#8aaa8a"));
        t.setTextSize(13);
        t.setPadding(0, 0, 0, dp(8));
        return t;
    }

    private Button actionBtn(String label, boolean primary) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(13);
        if (primary) {
            b.setBackgroundColor(Color.parseColor("#4ade80"));
            b.setTextColor(Color.parseColor("#052e16"));
        } else {
            b.setBackgroundColor(Color.parseColor("#1a2b1a"));
            b.setTextColor(Color.parseColor("#e8ffe8"));
        }
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(44));
        lp.topMargin = dp(6);
        b.setLayoutParams(lp);
        return b;
    }

    private void showServersModal(int screenW) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.addView(title("Активные серверы"));
        TextView status = muted("Загрузка...");
        box.addView(status);

        ScrollView scroll = new ScrollView(this);
        LinearLayout list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(list);
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(220));
        box.addView(scroll, slp);

        Button close = actionBtn("Закрыть", false);
        close.setOnClickListener(v -> closeModal());
        box.addView(close);

        attachModal(box, screenW);

        new Thread(() -> {
            try {
                String json = httpGet("/worlds");
                JSONArray arr = new JSONArray(json);
                handler.post(() -> {
                    list.removeAllViews();
                    if (arr.length() == 0) {
                        status.setText("Нет активных хостов");
                        return;
                    }
                    status.setText("Открытых: " + arr.length());
                    for (int i = 0; i < arr.length(); i++) {
                        try {
                            JSONObject w = arr.getJSONObject(i);
                            final int worldId = w.optInt("id");
                            String name = w.optString("name", "Мир");
                            String owner = w.optString("owner_username", "?");
                            int pc = w.optInt("player_count", 0);
                            int max = w.optInt("max_players", 5);

                            LinearLayout row = new LinearLayout(this);
                            row.setOrientation(LinearLayout.VERTICAL);
                            row.setPadding(dp(10), dp(10), dp(10), dp(10));
                            GradientDrawable bg = new GradientDrawable();
                            bg.setColor(Color.parseColor("#1a2b1a"));
                            bg.setCornerRadius(dp(12));
                            row.setBackground(bg);
                            LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(
                                LinearLayout.LayoutParams.MATCH_PARENT,
                                LinearLayout.LayoutParams.WRAP_CONTENT);
                            rlp.bottomMargin = dp(8);
                            row.setLayoutParams(rlp);

                            TextView n = new TextView(this);
                            n.setText(name);
                            n.setTextColor(Color.WHITE);
                            n.setTypeface(Typeface.DEFAULT_BOLD);
                            row.addView(n);
                            TextView m = muted(owner + " · " + pc + "/" + max);
                            row.addView(m);

                            Button play = actionBtn("Играть", true);
                            play.setOnClickListener(v -> {
                                closeModal();
                                toast("Открой MC → Друзья / LAN: " + name);
                            });
                            row.addView(play);
                            list.addView(row);
                        } catch (Exception ignored) {}
                    }
                });
            } catch (Exception e) {
                handler.post(() -> status.setText("Нет связи"));
            }
        }).start();
    }

    private void showHostPanel(int screenW, int worldId) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.addView(title("Панель хоста"));
        TextView ping = muted("Пинг: …");
        box.addView(ping);
        ScrollView scroll = new ScrollView(this);
        LinearLayout list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(list);
        box.addView(scroll, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(200)));

        Button close = actionBtn("Закрыть", false);
        close.setOnClickListener(v -> closeModal());
        box.addView(close);

        attachModal(box, screenW);

        long t0 = System.currentTimeMillis();
        new Thread(() -> {
            try {
                httpGet("/health");
                long rtt = System.currentTimeMillis() - t0;
                String json = httpGet("/worlds/" + worldId + "/players");
                JSONObject data = new JSONObject(json);
                JSONArray players = data.optJSONArray("players");
                boolean isOwner = data.optBoolean("is_owner", false);
                handler.post(() -> {
                    ping.setText("Пинг: " + rtt + " мс");
                    list.removeAllViews();
                    if (players == null || players.length() == 0) {
                        list.addView(muted("Пока только ты"));
                        return;
                    }
                    for (int i = 0; i < players.length(); i++) {
                        try {
                            JSONObject p = players.getJSONObject(i);
                            int uid = p.optInt("id");
                            String uname = p.optString("username", "?");
                            int prtt = p.optInt("rtt_ms", 0);
                            boolean isHost = p.optBoolean("is_host", false);

                            LinearLayout row = new LinearLayout(this);
                            row.setOrientation(LinearLayout.VERTICAL);
                            row.setPadding(dp(8), dp(8), dp(8), dp(8));
                            TextView line = new TextView(this);
                            line.setText(uname + (isHost ? " · хост" : "") + " · " + prtt + " мс");
                            line.setTextColor(Color.WHITE);
                            row.addView(line);

                            if (isOwner && !isHost) {
                                LinearLayout actions = new LinearLayout(this);
                                actions.setOrientation(LinearLayout.HORIZONTAL);
                                Button fr = smallBtn("Друг");
                                fr.setOnClickListener(v -> new Thread(() -> {
                                    try { httpPost("/friends/" + uid, null); } catch (Exception ignored) {}
                                    handler.post(() -> toast("Добавлен"));
                                }).start());
                                Button kick = smallBtn("Кик");
                                kick.setOnClickListener(v -> new Thread(() -> {
                                    try {
                                        httpPost("/worlds/" + worldId + "/kick",
                                            "{\"user_id\":" + uid + "}");
                                    } catch (Exception ignored) {}
                                }).start());
                                Button ban = smallBtn("Бан");
                                ban.setOnClickListener(v -> new Thread(() -> {
                                    try {
                                        httpPost("/worlds/" + worldId + "/ban",
                                            "{\"user_id\":" + uid + "}");
                                    } catch (Exception ignored) {}
                                    handler.post(() -> showHostPanel(screenW, worldId));
                                }).start());
                                actions.addView(fr);
                                actions.addView(kick);
                                actions.addView(ban);
                                row.addView(actions);
                            } else if (!isHost) {
                                Button fr = smallBtn("В друзья");
                                fr.setOnClickListener(v -> new Thread(() -> {
                                    try { httpPost("/friends/" + uid, null); } catch (Exception ignored) {}
                                    handler.post(() -> toast("Добавлен"));
                                }).start());
                                row.addView(fr);
                            }
                            list.addView(row);
                        } catch (Exception ignored) {}
                    }
                });
            } catch (Exception e) {
                handler.post(() -> ping.setText("Нет связи"));
            }
        }).start();
    }

    private Button smallBtn(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(11);
        b.setPadding(dp(8), dp(4), dp(8), dp(4));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, dp(36));
        lp.rightMargin = dp(6);
        b.setLayoutParams(lp);
        return b;
    }

    private String httpGet(String path) throws Exception {
        return http("GET", path, null);
    }

    private String httpDelete(String path) throws Exception {
        return http("DELETE", path, null);
    }

    private String httpPost(String path, String body) throws Exception {
        return http("POST", path, body);
    }

    private String http(String method, String path, String body) throws Exception {
        URL url = new URL(apiBase().replaceAll("/$", "") + path);
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(8000);
        c.setReadTimeout(8000);
        c.setRequestProperty("Content-Type", "application/json");
        String tok = token();
        if (tok != null && !tok.isEmpty()) {
            c.setRequestProperty("Authorization", "Bearer " + tok);
        }
        if (body != null && ("POST".equals(method) || "PATCH".equals(method))) {
            c.setDoOutput(true);
            try (OutputStream os = c.getOutputStream()) {
                os.write(body.getBytes(StandardCharsets.UTF_8));
            }
        }
        int code = c.getResponseCode();
        BufferedReader br = new BufferedReader(new InputStreamReader(
            code >= 400 ? c.getErrorStream() : c.getInputStream(), StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = br.readLine()) != null) sb.append(line);
        br.close();
        if (code >= 400) throw new RuntimeException("HTTP " + code + " " + sb);
        return sb.toString();
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private void startFriendHostPolling() {
        // Keep host alive while overlay is running (WebView timers may pause in background)
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                final int hostId = prefs().getInt("hosting_world_id", 0);
                if (hostId > 0) {
                    new Thread(() -> {
                        try {
                            httpPost("/worlds/" + hostId + "/heartbeat", "{\"player_count\":1}");
                        } catch (Exception ignored) {}
                    }).start();
                }
                handler.postDelayed(this, 20000);
            }
        }, 5000);

        friendPoll = new Runnable() {
            @Override
            public void run() {
                new Thread(() -> {
                    try {
                        String json = httpGet("/friends");
                        JSONArray arr = new JSONArray(json);
                        for (int i = 0; i < arr.length(); i++) {
                            JSONObject f = arr.getJSONObject(i);
                            JSONObject hosting = f.optJSONObject("hosting");
                            if (hosting != null) {
                                int wid = hosting.optInt("id");
                                String fname = f.optString("username", "Друг");
                                String wname = hosting.optString("name", "мир");
                                if (!knownHostWorldIds.contains(wid)) {
                                    knownHostWorldIds.add(wid);
                                    handler.post(() -> notifyFriendHost(fname, wname));
                                }
                            }
                        }
                    } catch (Exception ignored) {}
                    handler.postDelayed(friendPoll, 20000);
                }).start();
            }
        };
        handler.postDelayed(friendPoll, 5000);
    }

    private void notifyFriendHost(String friend, String world) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;
        Notification n = new NotificationCompat.Builder(this, CHANNEL_FRIEND)
            .setContentTitle("Друг начал хостить")
            .setContentText(friend + " · " + world)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setAutoCancel(true)
            .build();
        nm.notify(2000 + (friend.hashCode() & 0xfff), n);
    }

    private void createChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm == null) return;
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Snake overlay", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
            NotificationChannel fr = new NotificationChannel(
                CHANNEL_FRIEND, "Друг хостит", NotificationManager.IMPORTANCE_DEFAULT);
            nm.createNotificationChannel(fr);
        }
    }

    private Notification buildOngoingNotification() {
        Intent stop = new Intent(this, OverlayService.class);
        stop.setAction("STOP");
        PendingIntent stopPi = PendingIntent.getService(
            this, 1, stop, PendingIntent.FLAG_IMMUTABLE);
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Multiplayer Snake")
            .setContentText("Тап — серверы · вниз — скрыть")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .addAction(0, "Скрыть", stopPi)
            .setOngoing(true)
            .build();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) {
            stopHostingOnServer();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (intent != null && "HOST_PANEL".equals(intent.getAction())) {
            int wid = intent.getIntExtra("world_id", 0);
            int screenW = getResources().getDisplayMetrics().widthPixels;
            if (wid > 0) handler.post(() -> showHostPanel(screenW, wid));
        }
        return START_STICKY;
    }

    private void stopHostingOnServer() {
        final int hostId = prefs().getInt("hosting_world_id", 0);
        if (hostId <= 0) return;
        new Thread(() -> {
            try {
                httpDelete("/worlds/" + hostId);
            } catch (Exception ignored) {}
            prefs().edit().putInt("hosting_world_id", 0).apply();
        }).start();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        stopHostingOnServer();
        if (friendPoll != null) handler.removeCallbacks(friendPoll);
        closeModal();
        if (fab != null && windowManager != null) {
            try { windowManager.removeView(fab); } catch (Exception ignored) {}
        }
        fab = null;
    }
}
