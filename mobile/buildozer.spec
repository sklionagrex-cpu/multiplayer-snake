[app]
title = Multiplayer Snake
package.name = multiplayersnake
package.domain = com.snake.mcpe
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 0.3.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,requests,certifi,urllib3,idna,charset-normalizer,pillow,pyjnius,android
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = True
presplash.color = #122012
android.presplash_color = #122012

[buildozer]
log_level = 2
warn_on_root = 0
