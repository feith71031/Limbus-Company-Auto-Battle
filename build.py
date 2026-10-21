"""打包兩個工具成 exe，輸出到 dist\（需要先 pip install -r requirements.txt）。

用法：python build.py [輸出資料夾]
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = sys.argv[1] if len(sys.argv) > 1 else "dist"

TARGETS = [  # (exe 名稱, 程式, 是否使用自訂圖示, 要一起打包的資料)
    ("Limbus Company 自動戰鬥", "limbus_battle.pyw", True,
     ["../icon.ico;.", "../limbus_templates;limbus_templates", "../sounds;sounds"]),
    ("視窗自動按鍵器", "auto_key.pyw", False, []),
]

for name, script, use_icon, data in TARGETS:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
           "--name", name, "--distpath", DIST, "--workpath", "build", "--specpath", "build"]
    if use_icon:
        cmd += ["--icon", "../icon.ico"]
    for item in data:
        cmd += ["--add-data", item]
    print(f"=== 打包 {name} ===", flush=True)
    if subprocess.call(cmd + [script], cwd=ROOT) != 0:
        sys.exit(f"打包 {name} 失敗")

print(f"\n完成，檔案在 {os.path.join(ROOT, DIST)}")
