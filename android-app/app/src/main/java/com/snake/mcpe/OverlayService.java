package com.snake.mcpe;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import androidx.core.app.NotificationCompat;

public class OverlayService extends Service {
    private WindowManager windowManager;
    private View overlayView;
    private static final String CHANNEL_ID = "snake_overlay";

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(1, buildNotification());

        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        ImageView btn = new ImageView(this);
        btn.setImageResource(R.mipmap.ic_launcher);
        btn.setScaleType(ImageView.ScaleType.CENTER_CROP);
        btn.setAlpha(0.5f);
        btn.setClipToOutline(true);

        float density = getResources().getDisplayMetrics().density;
        int size = (int) (48 * density);
        final WindowManager.LayoutParams params = new WindowManager.LayoutParams(
            size, size,
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.END;
        params.x = 24;
        params.y = 180;

        final int screenH = getResources().getDisplayMetrics().heightPixels;

        btn.setOnTouchListener(new View.OnTouchListener() {
            private int initialX, initialY;
            private float touchX, touchY;
            private boolean moved;

            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getAction()) {
                    case MotionEvent.ACTION_DOWN:
                        initialX = params.x;
                        initialY = params.y;
                        touchX = event.getRawX();
                        touchY = event.getRawY();
                        moved = false;
                        return true;
                    case MotionEvent.ACTION_MOVE: {
                        float dx = event.getRawX() - touchX;
                        float dy = event.getRawY() - touchY;
                        if (Math.abs(dx) > 8 || Math.abs(dy) > 8) moved = true;
                        params.x = initialX - (int) dx;
                        params.y = initialY + (int) dy;
                        // fade more when near bottom
                        float progress = Math.min(1f, Math.max(0f, (float) params.y / (screenH * 0.75f)));
                        v.setAlpha(0.5f * (1f - progress * 0.7f));
                        try { windowManager.updateViewLayout(overlayView, params); } catch (Exception ignored) {}
                        return true;
                    }
                    case MotionEvent.ACTION_UP:
                        // swipe down far enough -> dismiss
                        if (params.y > screenH * 0.72f) {
                            stopSelf();
                            return true;
                        }
                        v.setAlpha(0.5f);
                        if (!moved) {
                            Intent i = getPackageManager().getLaunchIntentForPackage(getPackageName());
                            if (i != null) {
                                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                                    | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                                startActivity(i);
                            }
                        }
                        return true;
                }
                return false;
            }
        });

        overlayView = btn;
        try {
            windowManager.addView(overlayView, params);
        } catch (Exception e) {
            stopSelf();
        }
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Snake overlay", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    private Notification buildNotification() {
        Intent open = getPackageManager().getLaunchIntentForPackage(getPackageName());
        PendingIntent pi = PendingIntent.getActivity(
            this, 0, open != null ? open : new Intent(this, MainActivity.class),
            PendingIntent.FLAG_IMMUTABLE);
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Multiplayer Snake")
            .setContentText("Потяни кнопку вниз, чтобы скрыть")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pi)
            .setOngoing(true)
            .build();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (overlayView != null && windowManager != null) {
            try { windowManager.removeView(overlayView); } catch (Exception ignored) {}
        }
    }
}
