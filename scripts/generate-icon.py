#!/usr/bin/env python3
"""Regenerate the PNG and embedded window icon from the SVG master (librsvg required)."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
subprocess.run(['rsvg-convert', '-w', '256', '-h', '256', str(root/'assets/wallpaper-lab.svg'), '-o', str(root/'assets/wallpaper-lab.png')], check=True)
data = (root/'assets/wallpaper-lab.png').read_bytes()
(root/'src/app_icon.h').write_text(
    '/* Generated from assets/wallpaper-lab.png. Keep in sync with the SVG master. */\n'
    '#ifndef WALLPAPER_LAB_APP_ICON_H\n#define WALLPAPER_LAB_APP_ICON_H\n'
    'static Texture2D appIconTexture;\nstatic void SetAppIcon(void) {\n    static const unsigned char png[] = {\n'
    + ''.join('        '+','.join(str(x) for x in data[i:i+24])+',\n' for i in range(0,len(data),24))
    + '    };\n    Image icon = LoadImageFromMemory(".png", png, sizeof(png));\n'
    '    if (icon.data) { SetWindowIcon(icon); appIconTexture = LoadTextureFromImage(icon); SetTextureFilter(appIconTexture, TEXTURE_FILTER_BILINEAR); UnloadImage(icon); }\n}\n#endif\n')
