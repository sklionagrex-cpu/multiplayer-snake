package com.snake.mcpe;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import java.util.List;

public class MainActivity extends AppCompatActivity {
    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private static final int FILE_CHOOSER_REQUEST = 1001;
    private static final String PREFS = "snake_prefs";

    private static final String[] MC_PACKAGES = {
        "com.mojang.minecraftpe",
        "com.mojang.minecraftpe.unlock",
        "com.mojang.minecraftpe.beta",
        "com.mojang.minecraftworlds"
    };

    public class Bridge {
        @JavascriptInterface
        public void saveSession(String token, String apiUrl) {
            SharedPreferences.Editor ed = getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit();
            if (token != null) ed.putString("token", token);
            if (apiUrl != null && apiUrl.length() > 0) ed.putString("api_url", apiUrl);
            ed.apply();
        }

        @JavascriptInterface
        public void clearSession() {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply();
        }

        @JavascriptInterface
        public void saveHostingWorld(int worldId) {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putInt("hosting_world_id", worldId).apply();
        }

        @JavascriptInterface
        public void saveHostingWorld(String worldIdStr) {
            try {
                int worldId = Integer.parseInt(worldIdStr);
                getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putInt("hosting_world_id", worldId).apply();
            } catch (Exception ignored) {}
        }

        @JavascriptInterface
        public void clearHostingWorld() {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putInt("hosting_world_id", 0).apply();
        }

        @JavascriptInterface
        public void launchMinecraft() {
            runOnUiThread(() -> {
                if (tryLaunchMinecraft()) return;
                Toast.makeText(MainActivity.this, "Minecraft PE не найден", Toast.LENGTH_LONG).show();
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
        public void openHostPanel(int worldId) {
            runOnUiThread(() -> {
                Intent svc = new Intent(MainActivity.this, OverlayService.class);
                svc.setAction("HOST_PANEL");
                svc.putExtra("world_id", worldId);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(svc);
                } else {
                    startService(svc);
                }
            });
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
        s.setAllowContentAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setLoadsImagesAutomatically(true);
        s.setBlockNetworkImage(false);
        try { s.setRenderPriority(WebSettings.RenderPriority.HIGH); } catch (Exception ignored) {}
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            webView.setLayerType(android.view.View.LAYER_TYPE_HARDWARE, null);
        }

        webView.addJavascriptInterface(new Bridge(), "AndroidBridge");
        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> callback,
                                             FileChooserParams fileChooserParams) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("image/*");
                try {
                    startActivityForResult(Intent.createChooser(intent, "Фото"), FILE_CHOOSER_REQUEST);
                } catch (Exception e) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "Не удалось открыть галерею", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST) {
            if (filePathCallback == null) return;
            Uri[] result = null;
            if (resultCode == Activity.RESULT_OK && data != null) {
                result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            }
            filePathCallback.onReceiveValue(result);
            filePathCallback = null;
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Back in launcher = left the game session → stop hosting immediately
        final SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        final int hostId = prefs.getInt("hosting_world_id", 0);
        final String token = prefs.getString("token", "");
        final String api = prefs.getString("api_url", "http://109.120.152.78:8000");
        if (hostId > 0 && token != null && token.length() > 0) {
            new Thread(() -> {
                try {
                    java.net.URL url = new java.net.URL(api.replaceAll("/$", "") + "/worlds/" + hostId);
                    java.net.HttpURLConnection c = (java.net.HttpURLConnection) url.openConnection();
                    c.setRequestMethod("DELETE");
                    c.setRequestProperty("Authorization", "Bearer " + token);
                    c.setConnectTimeout(5000);
                    c.setReadTimeout(5000);
                    c.getResponseCode();
                    c.disconnect();
                } catch (Exception ignored) {}
                prefs.edit().putInt("hosting_world_id", 0).apply();
            }).start();
        }
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
