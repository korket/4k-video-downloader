import os
import sys
import zipfile
import shutil
import urllib.request
import platform

FFMPEG_URL_WIN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
FFMPEG_EXE = os.path.join(BIN_DIR, 'ffmpeg.exe')

def download_ffmpeg():
    if os.path.exists(FFMPEG_EXE):
        print(f"FFmpeg already exists at {FFMPEG_EXE}")
        return

    print("Downloading FFmpeg...")
    if not os.path.exists(BIN_DIR):
        os.makedirs(BIN_DIR)

    zip_path = os.path.join(BIN_DIR, 'ffmpeg.zip')
    
    try:
        urllib.request.urlretrieve(FFMPEG_URL_WIN, zip_path)
        print("Download complete. Extracting...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Extract only ffmpeg.exe
            for file in zip_ref.namelist():
                if file.endswith('ffmpeg.exe'):
                    source = zip_ref.open(file)
                    target = open(FFMPEG_EXE, "wb")
                    with source, target:
                        shutil.copyfileobj(source, target)
                    break
        
        print(f"FFmpeg extracted to {FFMPEG_EXE}")
    except Exception as e:
        print(f"Error setting up FFmpeg: {e}")
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

if __name__ == "__main__":
    if platform.system() != "Windows":
        print("This script is configured for Windows only. Please install ffmpeg manually.")
    else:
        download_ffmpeg()
