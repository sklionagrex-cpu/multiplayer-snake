[app]
title = Multiplayer Snake
package.name = multiplayersnake
package.domain = com.snake.mcpe
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 0.3.2
requirements = python3,kivy==2.2.1,kivymd==1.1.1,requests,certifi,urllib3,idna,charset-normalizer,pillow,pyjnius,android,openssl,cython==0.29.33
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 31
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.allow_backup = True
presplash.color = #122012
android.presplash_color = #122012
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 0
