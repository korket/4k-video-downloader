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
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = BASE_DIR
        
    cookies_file = os.path.join(exe_dir, 'cookies.txt')
    if os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file
    else:
        # Priority 2: Attempt edge, but edge/chrome 127+ breaks due to DPAPI encryption
        # We handle the DPAPI error later
        opts['cookiesfrombrowser'] = ('edge',)
        
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
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            
            # Filter and process formats
            for f in info.get('formats', []):
                # We want video formats that have resolution
                if f.get('vcodec') != 'none' and f.get('resolution') != 'audio only':
                    res = f.get('height')
                    if res:
                        format_id = f['format_id']
                        # Combine video+audio (best audio)
                        formats.append({
                            'format_id': format_id,
                            'resolution': f"{res}p",
                            'ext': f['ext'],
                            'filesize': f.get('filesize', 0),
                            'note': f.get('format_note', '')
                        })

            # Video details
            duration_sec = info.get('duration')
            video_data = {
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': duration_sec,
                'duration_string': format_duration(duration_sec),
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

def update_job_progress(job_id, d):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        jobs[job_id]['downloaded_bytes'] = downloaded
        jobs[job_id]['total_bytes'] = total
        if total > 0:
            jobs[job_id]['progress'] = (downloaded / total) * 100
    elif d['status'] == 'finished':
        jobs[job_id]['progress'] = 100
        jobs[job_id]['status'] = 'merging'

def get_unique_filename(directory, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1
    return new_filename

def download_task(job_id, url, res, format_id, target_path=None):
    try:
        temp_dir = os.path.join(BASE_DIR, 'temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        ydl_opts = get_ydl_opts()
        ydl_opts['progress_hooks'] = [lambda d: update_job_progress(job_id, d)]
        
        # Use job_id in temp filename to avoid collisions during download
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
            
            jobs[job_id]['status'] = 'saved'
            jobs[job_id]['final_path'] = final_path
            jobs[job_id]['filename'] = os.path.basename(final_path)
            
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
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'starting', 
        'progress': 0,
        'downloaded_bytes': 0,
        'total_bytes': 0
    }
    
    thread = threading.Thread(target=download_task, args=(job_id, url, res, format_id, target_path))
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
