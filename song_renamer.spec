# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

# Collect everything from librosa (data files + binaries)
librosa_datas, librosa_binaries, librosa_hiddenimports = collect_all('librosa')

a = Analysis(
    ['song_renamer.py'],
    pathex=[],
    binaries=librosa_binaries,
    datas=librosa_datas,
    hiddenimports=librosa_hiddenimports + [
        'librosa', 'librosa.core', 'librosa.core.audio',
        'librosa.feature', 'librosa.feature.spectral',
        'librosa.feature.rhythm', 'librosa.beat',
        'librosa.effects', 'librosa.onset', 'librosa.util',
        'soundfile', 'soxr',
        'scipy', 'scipy.signal', 'scipy.fft', 'scipy.ndimage',
        'scipy.special', 'scipy.interpolate',
        'numba', 'numba.core', 'llvmlite', 'llvmlite.binding',
        'PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'jupyter', 'tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Song Renamer',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Song Renamer',
)

app = BUNDLE(
    coll,
    name='Song Renamer.app',
    icon='icon.icns',
    bundle_identifier='com.flurobyte.songrenamer',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'Song Renamer',
        'LSApplicationCategoryType': 'public.app-category.music',
        'NSRequiresAquaSystemAppearance': False,
    },
)
