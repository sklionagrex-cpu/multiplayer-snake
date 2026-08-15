package com.snake.mcpe;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ImageView;
import androidx.core.app.NotificationCompat;

public class OverlayService extends Service {
    private WindowManager windowManager;
    private ImageView fab;
    private FrameLayout panel;
    private WebView panelWeb;
    private WindowManager.LayoutParams fabParams;
    private static final String CHANNEL_ID = "snake_overlay";

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(1, buildNotification());
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        addFab();
    }

    private void addFab() {
        fab = new ImageView(this);
        fab.setImageResource(R.mipmap.ic_launcher);
        fab.setScaleType(ImageView.ScaleType.CENTER_CROP);
        fab.setAlpha(0.5f);

        float density = getResources().getDisplayMetrics().density;
        int size = (int) (48 * density);
        fabParams = new WindowManager.LayoutParams(
            size,
            size,
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE,
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
                        if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
                            moved = true;
                        }
                        fabParams.x = initialX - (int) dx;
                        fabParams.y = initialY + (int) dy;
                        float progress = Math.min(1f, Math.max(0f, (float) fabParams.y / (screenH * 0.75f)));
                        v.setAlpha(0.5f * (1f - progress * 0.7f));
                        try {
                            windowManager.updateViewLayout(fab, fabParams);
                        } catch (Exception ignored) {
                        }
                        return true;
                    }
                    case MotionEvent.ACTION_UP:
                        if (fabParams.y > screenH * 0.72f) {
                            stopSelf();
                            return true;
                        }
                        v.setAlpha(0.5f);
                        if (!moved) {
                            if (panel != null) {
                                closePanel();
                            } else {
                                openPanel(screenW, screenH);
                            }
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

    private void openPanel(int screenW, int screenH) {
        closePanel();
        panel = new FrameLayout(this);
        panel.setBackgroundColor(Color.parseColor("#E60A120A"));

        panelWeb = new WebView(this);
        WebSettings ws = panelWeb.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setAllowFileAccess(true);
        panelWeb.setBackgroundColor(Color.TRANSPARENT);
        panelWeb.setWebViewClient(new WebViewClient());
        panelWeb.loadUrl("file:///android_asset/index.html?mode=overlay");

        int panelH = (int) (screenH * 0.55f);
        WindowManager.LayoutParams panelParams = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            panelH,
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        );
        panelParams.gravity = Gravity.BOTTOM;

        panel.addView(
            panelWeb,
            new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        try {
            windowManager.addView(panel, panelParams);
            if (fab != null) {
                fab.setVisibility(View.GONE);
            }
        } catch (Exception e) {
            panel = null;
            panelWeb = null;
        }
    }

    private void closePanel() {
        if (panel != null && windowManager != null) {
            try {
                windowManager.removeView(panel);
            } catch (Exception ignored) {
            }
        }
        panel = null;
        panelWeb = null;
        if (fab != null) {
            fab.setVisibility(View.VISIBLE);
            fab.setAlpha(0.5f);
        }
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Snake overlay", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(ch);
            }
        }
    }

    private Notification buildNotification() {
        Intent stop = new Intent(this, OverlayService.class);
        stop.setAction("STOP");
        PendingIntent stopPi = PendingIntent.getService(
            this, 1, stop, PendingIntent.FLAG_IMMUTABLE);
        Intent open = getPackageManager().getLaunchIntentForPackage(getPackageName());
        PendingIntent pi = PendingIntent.getActivity(
            this, 0, open != null ? open : new Intent(this, MainActivity.class),
            PendingIntent.FLAG_IMMUTABLE);
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Multiplayer Snake")
            .setContentText("Тап — панель · потяни вниз — скрыть")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pi)
            .addAction(0, "Скрыть", stopPi)
            .setOngoing(true)
            .build();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        closePanel();
        if (fab != null && windowManager != null) {
            try {
                windowManager.removeView(fab);
            } catch (Exception ignored) {
            }
        }
        fab = null;
    }
}
