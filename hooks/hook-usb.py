# No-op hook — overrides pyinstaller-hooks-contrib's broken hook-usb.py.
# AutoCore has a local usb.py (not the PyUSB library), so PyUSB collection
# must be skipped entirely.
hiddenimports = []
