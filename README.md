# 4K Video Downloader

A standalone desktop application for downloading YouTube videos in various resolutions (up to 4K) or extracting audio as MP3. Built with React, Python (Flask), and yt-dlp.

## Features

- **High Quality Downloads**: Support for 4K video resolution.
- **Audio Extraction**: Convert videos to MP3 format.
- **Monochrome UI**: Clean, distraction-free Black/White/Grey interface.
- **Smart Renaming**: Automatically handles file naming and extensions.
- **Direct Save**: System-native "Save As" dialog for file management.

## Installation

### Prerequisites

- Python 3.12 or higher
- Node.js (for building the frontend)
- FFmpeg (included in binary builds, required in system PATH for dev)

### Setup

1.  Clone the repository:
    ```bash
    git clone git@github.com:korket/4k-youtube-video-downloader.git
    cd 4k-youtube-video-downloader
    ```

2.  Install Python dependencies:
    ```bash
    pip install -r backend/requirements.txt
    ```

3.  Install Frontend dependencies:
    ```bash
    cd frontend
    npm install
    cd ..
    ```

## Development

1.  Start the frontend development server:
    ```bash
    cd frontend
    npm run dev
    ```

2.  Start the backend server (in a new terminal):
    ```bash
    python backend/server.py
    ```

## Building the Executable

To create a standalone `.exe` file:

1.  Build the frontend:
    ```bash
    cd frontend
    npm run build
    cd ..
    ```

2.  Run PyInstaller:
    ```bash
    python -m PyInstaller --clean --noconfirm youtube_downloader.spec
    ```

The executable will be located in the `dist/` folder.

## Technologies Used

- **Frontend**: React, Vite, Tailwind CSS
- **Backend**: Python, Flask, yt-dlp
- **Window Management**: pywebview
- **Processing**: FFmpeg
