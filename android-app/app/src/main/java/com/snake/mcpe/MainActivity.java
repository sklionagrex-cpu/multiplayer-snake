package com.snake.mcpe;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import java.util.List;

public class MainActivity extends AppCompatActivity {
    private WebView webView;

    private static final String[] MC_PACKAGES = {
        "com.mojang.minecraftpe",
        "com.mojang.minecraftpe.unlock",
        "com.mojang.minecraftpe.beta",
        "com.mojang.minecraftworlds"
    };

    public class Bridge {
        @JavascriptInterface
        public void launchMinecraft() {
            runOnUiThread(() -> {
                if (tryLaunchMinecraft()) return;
                Toast.makeText(MainActivity.this,
                    "Minecraft PE не найден. Установите Minecraft PE 1.1.5",
                    Toast.LENGTH_LONG).show();
            });
        }

        @JavascriptInterface
        public void startOverlay() {
            runOnUiThread(() -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                        && !Settings.canDrawOverlays(MainActivity.this)) {
                    Intent i = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getPackageName()));
                    startActivity(i);
                    Toast.makeText(MainActivity.this,
                        "Разрешите показ поверх других окон", Toast.LENGTH_LONG).show();
                    return;
                }
                Intent svc = new Intent(MainActivity.this, OverlayService.class);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(svc);
                } else {
                    startService(svc);
                }
            });
        }

        @JavascriptInterface
        public void stopOverlay() {
            runOnUiThread(() ->
                stopService(new Intent(MainActivity.this, OverlayService.class)));
        }

        @JavascriptInterface
        public boolean hasOverlayPermission() {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                return Settings.canDrawOverlays(MainActivity.this);
            }
            return true;
        }
    }

    private boolean tryLaunchMinecraft() {
        PackageManager pm = getPackageManager();
        for (String pkg : MC_PACKAGES) {
            Intent launch = pm.getLaunchIntentForPackage(pkg);
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try {
                    startActivity(launch);
                    return true;
                } catch (Exception ignored) {}
            }
        }
        // Scan installed apps for "minecraft"
        try {
            List<ApplicationInfo> apps = pm.getInstalledApplications(PackageManager.GET_META_DATA);
            for (ApplicationInfo app : apps) {
                String pkg = app.packageName == null ? "" : app.packageName.toLowerCase();
                String label = "";
                try { label = pm.getApplicationLabel(app).toString().toLowerCase(); } catch (Exception ignored) {}
                if (pkg.contains("minecraft") || label.contains("minecraft")) {
                    Intent launch = pm.getLaunchIntentForPackage(app.packageName);
                    if (launch != null) {
                        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        startActivity(launch);
                        return true;
                    }
                }
            }
        } catch (Exception ignored) {}
        return false;
    }

    @Override
    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.addJavascriptInterface(new Bridge(), "AndroidBridge");
        webView.setWebViewClient(new WebViewClient());
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
