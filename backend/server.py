import yt_dlp
import os
import webview
import sys
import threading
import uuid
import time
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# Determine if running from PyInstaller
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'web')
    static_folder = os.path.join(sys._MEIPASS, 'web', 'assets')
    FFMPEG_PATH = os.path.join(sys._MEIPASS, 'bin', 'ffmpeg.exe')
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
else:
    template_folder = os.path.join(BASE_DIR, '../frontend/dist')
    static_folder = os.path.join(BASE_DIR, '../frontend/dist/assets')
    FFMPEG_PATH = os.path.join(BASE_DIR, 'bin', 'ffmpeg.exe')
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)

CORS(app, expose_headers=["Content-Disposition"])

def get_ydl_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    # Priority 1: cookies.txt file next to the executable
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        BASE_DIR = sys._MEIPASS
        exe_dir = os.path.dirname(sys.executable)
        bundle_dir = sys._MEIPASS
    else:
        # Running as script
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        exe_dir = BASE_DIR
        bundle_dir = BASE_DIR

    # Ensure bundled executables (like deno.exe and ffmpeg.exe) are discoverable by yt-dlp
    os.environ['PATH'] = bundle_dir + os.pathsep + os.path.join(bundle_dir, 'bin') + os.pathsep + os.environ.get('PATH', '')
            
    cookies_file = os.path.join(exe_dir, 'cookies.txt')
    if os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file
    else:
        opts['cookiesfrombrowser'] = ('firefox',)
        
    if os.path.exists(FFMPEG_PATH):
        opts['ffmpeg_location'] = FFMPEG_PATH
    return opts

@app.before_request
def log_request():
    try:
        with open('debug_server.log', 'a') as f:
            f.write(f"Request: {request.method} {request.path}\n")
    except:
        pass

def format_duration(seconds):
    if not seconds:
        return '--:--'
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        ydl_opts = get_ydl_opts()
        ydl_opts['extract_flat'] = 'in_playlist'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            is_playlist = info.get('_type') == 'playlist'
            
            if is_playlist:
                entries = info.get('entries', [])
                video_data = {
                    'title': info.get('title'),
                    'thumbnail': None,
                    'duration_string': f"{len(entries)} Videos",
                    'is_playlist': True,
                    'formats': [
                        {'format_id': 'best', 'resolution': 'Best Quality', 'ext': 'mp4', 'note': 'Highest available'},
                        {'format_id': '1080', 'resolution': '1080p Limit', 'ext': 'mp4', 'note': 'Up to 1080p'},
                        {'format_id': '720', 'resolution': '720p Limit', 'ext': 'mp4', 'note': 'Up to 720p'},
                        {'format_id': '480', 'resolution': '480p Limit', 'ext': 'mp4', 'note': 'Up to 480p'},
                        {'format_id': 'mp3', 'resolution': 'Audio Only', 'ext': 'mp3', 'note': 'Best Audio'}
                    ]
                }
                return jsonify(video_data)
            
            formats = []
            
            # Filter and process formats
            unique_formats = {}
            for f in info.get('formats', []):
                # We want video formats that have resolution
                if f.get('vcodec') != 'none' and f.get('resolution') != 'audio only':
                    res = f.get('height')
                    if res:
                        format_id = f['format_id']
                        ext = f['ext']
                        filesize = f.get('filesize') or f.get('filesize_approx') or 0
                        # yt-dlp sorts from worst to best, so later entries overwrite earlier ones
                        # grouping by (res, ext) gives us the best variant per resolution/container
                        unique_formats[(res, ext)] = {
                            'format_id': format_id,
                            'resolution': f"{res}p",
                            'ext': ext,
                            'filesize': filesize,
                            'note': f.get('format_note', '')
                        }
            
            formats = list(unique_formats.values())

            # Video details
            duration_sec = info.get('duration')
            video_data = {
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': duration_sec,
                'duration_string': format_duration(duration_sec),
                'is_playlist': False,
                'formats': sorted(formats, key=lambda x: int(x['resolution'].replace('p','')) if x['resolution'] and 'p' in x['resolution'] else 0, reverse=True)
            }
            
            # Add MP3 option manually
            video_data['formats'].insert(0, {
                'format_id': 'mp3',
                'resolution': 'Audio Only',
                'ext': 'mp3',
                'filesize': 0, 
                'note': 'Best Audio'
            })
            
            return jsonify(video_data)
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Failed to decrypt with DPAPI" in error_msg or "Could not copy Chrome cookie database" in error_msg or "Permission denied" in error_msg:
            return jsonify({'error': "Browser cookies are encrypted (App-Bound Encryption/DPAPI). To bypass YouTube's bot block, use an extension to export 'cookies.txt' and place the file exactly next to this App's .exe file."}), 400
        elif "Sign in to confirm you’re not a bot" in error_msg:
             return jsonify({'error': "YouTube bot protection is active. Please place an exported 'cookies.txt' file next to the .exe to bypass it."}), 400
        return jsonify({'error': error_msg}), 400
    except Exception as e:
        return jsonify({'error': f"Unexpected Error: {str(e)}"}), 500

# ... (rest of code)

class Api:
    def open_folder_dialog(self, title=None):
        try:
            if webview.windows:
                active_window = webview.windows[0]
                result = active_window.create_file_dialog(
                    webview.FOLDER_DIALOG, 
                    directory=''
                )
                if result and len(result) > 0:
                    return result if isinstance(result, str) else result[0]
            return None
        except Exception as e:
            return None

    def save_file_dialog(self, filename, file_filter=None):
        try:
            if webview.windows:
                active_window = webview.windows[0]
                
                # Try with filter first
                try:
                    # Arg is file_types (tuple), not file_filter
                    # Format: ('Description (*.ext)',)
                    types = (file_filter,) if file_filter else ()
                    result = active_window.create_file_dialog(
                        webview.SAVE_DIALOG, 
                        directory='', 
                        save_filename=filename,
                        file_types=types
                    )
                except Exception as e:
                    # Fallback without filter
                    print(f"Dialog error: {e}") # Simple print for packaged app debugging if visible
                    result = active_window.create_file_dialog(
                        webview.SAVE_DIALOG, 
                        directory='', 
                        save_filename=filename
                    )

                # webview.create_file_dialog returns a tuple/list, even for save dialog
                if result and len(result) > 0:
                    return result if isinstance(result, str) else result[0]
                return None
            return None
        except Exception as e:
            return None

# ... (Job/Download code)

# Note: Make sure Api is instantiated and passed in main block
# (This replace covers the info route update, I will check the main block next)

# In-memory job store
jobs = {}

import re

def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', str(text)) if text else ''

def update_job_progress(job_id, d):
    job = jobs.get(job_id)
    if not job: return

    if d['status'] == 'downloading':
        job['status'] = 'downloading'
        
        info = d.get('info_dict', {})
        if 'req_count' not in job:
            req = info.get('requested_downloads')
            job['req_count'] = len(req) if req else 1
            job['current_file_index'] = 1
            job['current_filename'] = d.get('filename')
            
        p_index = info.get('playlist_index')
        p_count = info.get('playlist_count')
        if p_index and p_count:
            job['playlist_index'] = p_index
            job['playlist_count'] = p_count

        if d.get('filename') and d.get('filename') != job.get('current_filename'):
            job['current_filename'] = d.get('filename')
            job['current_file_index'] = job.get('current_file_index', 1) + 1

        req_count = job.get('req_count', 1)
        idx = job.get('current_file_index', 1)
        
        if req_count > 1:
            job['stream_type'] = 'Audio' if idx > 1 else 'Video'
        else:
            job['stream_type'] = ''

        speed = strip_ansi(d.get('_speed_str', '')).strip()
        eta = strip_ansi(d.get('_eta_str', '')).strip()
        down_str = strip_ansi(d.get('_downloaded_bytes_str', '')).strip()
        total_str = strip_ansi(d.get('_total_bytes_str') or d.get('_total_bytes_estimate_str', '')).strip()
        
        if speed: job['speed'] = speed
        if eta: job['eta'] = eta
        if down_str: job['downloaded_str'] = down_str
        if total_str: job['total_str'] = total_str

        percent_str = strip_ansi(d.get('_percent_str', '')).replace('%', '').strip()
        try:
            job['progress'] = float(percent_str)
        except:
            pass
            
    elif d['status'] == 'finished':
        finished_bytes = d.get('total_bytes') or d.get('downloaded_bytes') or 0
        job['previous_files_bytes'] = job.get('previous_files_bytes', 0) + finished_bytes

def update_job_postprocessor(job_id, d):
    job = jobs.get(job_id)
    if not job: return
    if d['status'] == 'started':
        job['status'] = 'merging'
        job['progress'] = 100

def get_unique_filename(directory, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1
    return new_filename

def download_task(job_id, url, res, format_id, target_path=None, is_playlist=False):
    try:
        ydl_opts = get_ydl_opts()
        ydl_opts['progress_hooks'] = [lambda d: update_job_progress(job_id, d)]
        ydl_opts['postprocessor_hooks'] = [lambda d: update_job_postprocessor(job_id, d)]
        
        if is_playlist:
            # For playlists, target_path should be a directory the user chose
            from yt_dlp.utils import sanitize_filename
            target_dir = target_path if target_path else os.path.join(os.path.expanduser('~'), 'Downloads', 'Playlist')
            os.makedirs(target_dir, exist_ok=True)
            output_template = os.path.join(target_dir, f'%(playlist_index)02d - %(title)s.%(ext)s')
            ydl_opts['outtmpl'] = output_template
        else:
            temp_dir = os.path.join(BASE_DIR, 'temp')
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            output_template = os.path.join(temp_dir, f'%(title)s_{job_id}.%(ext)s')
            ydl_opts['outtmpl'] = output_template

        if format_id == 'mp3':
             format_str = 'bestaudio/best'
             ydl_opts.update({
                 'format': format_str,
                 'postprocessors': [{
                     'key': 'FFmpegExtractAudio',
                     'preferredcodec': 'mp3',
                     'preferredquality': '192',
                 }],
             })
        elif is_playlist and format_id != 'best':
             # E.g. format_id == '1080'
             format_str = f"bestvideo[height<={format_id}]+bestaudio/best[height<={format_id}]/best"
             ydl_opts.update({
                'format': format_str,
                'merge_output_format': 'mp4',
             })
        elif is_playlist and format_id == 'best':
             format_str = "bestvideo+bestaudio/best"
             ydl_opts.update({
                'format': format_str,
                'merge_output_format': 'mp4',
             })
        elif format_id:
             format_str = f"{format_id}+bestaudio/best"
             ydl_opts.update({
                'format': format_str,
                'merge_output_format': 'mp4',
             })
        else:
             format_str = f"bestvideo[height<={res}]+bestaudio/best[height<={res}]/best" if res else "bestvideo+bestaudio/best"
             ydl_opts.update({
                'format': format_str,
                'merge_output_format': 'mp4',
             })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not is_playlist:
                temp_filename = ydl.prepare_filename(info)
                
                # Adjust extension for mp3 or merged mp4
                if format_id == 'mp3':
                    temp_filename = temp_filename.rsplit('.', 1)[0] + '.mp3'
                elif info.get('requested_downloads'):
                     # It might have been merged, check if mp4 exists
                     possible_name = temp_filename.rsplit('.', 1)[0] + '.mp4'
                     if os.path.exists(possible_name):
                         temp_filename = possible_name
                
                # Determine destination
                if target_path:
                    final_path = target_path
                    # Ensure directory exists (though save dialog usually handles this)
                    os.makedirs(os.path.dirname(final_path), exist_ok=True)
                else:
                    # Fallback to Downloads folder
                    title = info.get('title', 'video')
                    uploader = info.get('uploader', 'unknown')
                    ext = os.path.splitext(temp_filename)[1]
    
                    import re
                    safe_title = re.sub(r'[<>:"/\\|?*]', '', title).strip()
                    safe_uploader = re.sub(r'[<>:"/\\|?*]', '', uploader).strip()
                    desired_filename = f"{safe_title} - {safe_uploader}{ext}"
                    
                    downloads_folder = os.path.join(os.path.expanduser('~'), 'Downloads')
                    if not os.path.exists(downloads_folder):
                        downloads_folder = os.path.join(os.path.expanduser('~'), 'Desktop')
    
                    final_filename = get_unique_filename(downloads_folder, desired_filename)
                    final_path = os.path.join(downloads_folder, final_filename)
                
                # Move file
                import shutil
                # If target exists, overwrite or handle? shutil.move overwrites if dest is file
                shutil.move(temp_filename, final_path)
                
                jobs[job_id]['final_path'] = final_path
                jobs[job_id]['filename'] = os.path.basename(final_path)
            else:
                # Playlist just uses the Target Directory as its complete destination
                jobs[job_id]['filename'] = f"Playlist downloaded to Folder"
                
            jobs[job_id]['status'] = 'saved'
            
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Failed to decrypt with DPAPI" in error_msg or "Could not copy Chrome cookie database" in error_msg or "Permission denied" in error_msg:
            jobs[job_id]['error'] = "Browser cookies are encrypted (App-Bound Encryption/DPAPI). To bypass YouTube's bot block, use an extension to export 'cookies.txt' and place the file exactly next to this App's .exe file."
        elif "Sign in to confirm you’re not a bot" in error_msg:
            jobs[job_id]['error'] = "YouTube bot protection is active. Please place an exported 'cookies.txt' file next to the .exe to bypass it."
        else:
            jobs[job_id]['error'] = error_msg
        jobs[job_id]['status'] = 'error'
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)

@app.route('/api/prepare_download', methods=['POST'])
def prepare_download():
    data = request.json
    url = data.get('url')
    res = data.get('res')
    format_id = data.get('format_id')
    target_path = data.get('target_path')
    is_playlist = data.get('is_playlist', False)
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'starting', 
        'progress': 0,
        'downloaded_bytes': 0,
        'total_bytes': 0
    }
    
    thread = threading.Thread(target=download_task, args=(job_id, url, res, format_id, target_path, is_playlist))
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/api/progress/<job_id>', methods=['GET'])
def get_progress(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/')
def index():
    return send_from_directory(template_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path.startswith('api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    return send_from_directory(template_folder, path)

if __name__ == '__main__':
    # Find an open port
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))
    port = sock.getsockname()[1]
    sock.close()

    def start_server():
        app.run(host='127.0.0.1', port=port, threaded=True)

    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

    # Create API instance
    api = Api()

    # Create webview window pointing to the local server, passing js_api
    webview.create_window('4K Video Downloader', f'http://127.0.0.1:{port}', width=600, height=600, resizable=False, js_api=api)
    webview.start()
