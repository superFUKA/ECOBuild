"""インストーラー（Setup.exe）に入れる Python と ecobuild を用意する（配る側で、npm run dist の前に実行する）。

- out/python：Python の公式の NuGet パッケージ（フォルダごと動く Python。venv・ensurepip もある：型 python のモジュールの
  .venv は既定で ECOBuild と同じ Python で作る）。利用者の PC に Python がなくても GUI と ecobuild が動く。
- out/wheels：ecobuild（このリポジトリ）とその依存、pip の wheel。インストール時に install_cli.py が out/python に入れる
  （ecobuild.exe は入れた場所の Python を指すので、ここでは入れずにインストール時に作る）。

使い方：python gui/electron/bundle/prepare.py [--python 3.12.10]（git と、ネットワークが要る）
"""
import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
OUT = HERE / "out"
CACHE = HERE / "cache"   # ダウンロードした Python（作り直しのたびに取りに行かない）


def python(version: str) -> None:
    archive = CACHE / f"python.{version}.nupkg"
    if not archive.is_file():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = f"https://www.nuget.org/api/v2/package/python/{version}"
        print(f"取得：{url}")
        with urllib.request.urlopen(url) as response, open(archive.with_suffix(".part"), "wb") as file:
            shutil.copyfileobj(response, file)
        archive.with_suffix(".part").replace(archive)
    with zipfile.ZipFile(archive) as zip_file:   # 中の tools/ が Python のフォルダ
        for member in zip_file.infolist():
            if member.filename.startswith("tools/") and not member.is_dir():
                target = OUT / "python" / member.filename.removeprefix("tools/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zip_file.read(member))


def wheels() -> None:
    target = OUT / "wheels"
    pip = [sys.executable, "-m", "pip", "--disable-pip-version-check"]
    subprocess.run([*pip, "wheel", "--quiet", "--wheel-dir", str(target), str(REPOSITORY)], check=True)
    subprocess.run([*pip, "download", "--quiet", "--only-binary", ":all:", "--dest", str(target), "pip"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", default="3.12.10", help="同梱する Python の版（NuGet の python パッケージにあるもの）")
    args = parser.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    python(args.python)
    wheels()
    print(f"用意しました：{OUT}")


if __name__ == "__main__":
    main()
