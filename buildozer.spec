[app]
title = VBN Fortress
package.name = vbnfortress
package.domain = org.vbn.security
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.0
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.archs = arm64-v8a
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
