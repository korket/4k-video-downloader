import { useState, useEffect } from 'react'

const API_BASE = '/api';

function App() {
    const [url, setUrl] = useState('');
    const [loadingInfo, setLoadingInfo] = useState(false);
    const [videoInfo, setVideoInfo] = useState({
        title: 'Video Title',
        thumbnail: null,
        duration_string: '--:--',
        formats: []
    });
    const [selectedFormat, setSelectedFormat] = useState('');
    const [downloading, setDownloading] = useState(false);
    const [downloadProgress, setDownloadProgress] = useState({ loaded: 0, total: 0, serverProgress: 0, status: 'idle' });
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    const fetchInfo = async () => {
        if (!url) return;
        setLoadingInfo(true);
        setError('');
        setSuccessMessage('');
        setSelectedFormat('');

        try {
            const res = await fetch(`${API_BASE}/info`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url }),
            });

            if (!res.ok) {
                const text = await res.text();
                let parsedError = null;
                try {
                    const data = JSON.parse(text);
                    parsedError = data.error || `Server Error: ${res.status}`;
                } catch (e) {
                    // Not JSON
                    parsedError = `Request failed: ${res.status} ${res.statusText}`;
                }
                throw new Error(parsedError);
            }

            const data = await res.json();

            setVideoInfo(data);
            if (data.formats && data.formats.length > 0) {
                setSelectedFormat(data.formats[0].format_id);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoadingInfo(false);
        }
    };

    const handleDownload = async () => {
        if (!videoInfo.formats.length || !selectedFormat) return;
        setDownloading(true);
        setDownloadProgress({ loaded: 0, total: 0, serverProgress: 0, status: 'initializing' });
        setError('');
        setSuccessMessage('');

        try {
            // 1. Ask for save location via PyWebview API
            let targetPath = null;

            // Check if pywebview is available (it might be injected)
            if (window.pywebview && window.pywebview.api) {
                const safeTitle = (videoInfo.title || 'video').replace(/[<>:"/\\|?*]/g, '').trim();
                const isMp3 = selectedFormat === 'mp3';
                const ext = isMp3 ? 'mp3' : 'mp4';
                const defaultName = `${safeTitle}.${ext}`;
                const fileFilter = isMp3 ? 'MP3 Audio (*.mp3)' : 'MP4 Video (*.mp4)';

                try {
                    // Open Save Dialog
                    targetPath = await window.pywebview.api.save_file_dialog(defaultName, fileFilter);
                    if (!targetPath) {
                        setDownloading(false);
                        setDownloadProgress(prev => ({ ...prev, status: 'idle' }));
                        return; // User cancelled
                    }
                } catch (err) {
                    console.error("Dialog error", err);
                    setError("Save Dialog Failed: " + err);
                    setDownloading(false);
                    return;
                }
            } else {
                console.warn("PyWebView API not found, falling back to auto-download.");
            }

            // 2. Prepare Download
            const prepareRes = await fetch(`${API_BASE}/prepare_download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url,
                    res: selectedFormat,
                    format_id: selectedFormat,
                    target_path: targetPath // Send chosen path to backend
                }),
            });

            if (!prepareRes.ok) {
                const text = await prepareRes.text();
                let parsedError = null;
                try {
                    const err = JSON.parse(text);
                    parsedError = err.error || 'Failed to start download';
                } catch (e) {
                    // Not JSON
                    parsedError = `Prepare failed: ${prepareRes.status}`;
                }
                throw new Error(parsedError);
            }

            const { job_id } = await prepareRes.json();

            // 3. Poll Progress
            let jobStatus = 'starting';
            while (jobStatus !== 'saved' && jobStatus !== 'error') {
                await new Promise(r => setTimeout(r, 1000));

                const progressRes = await fetch(`${API_BASE}/progress/${job_id}`);
                if (!progressRes.ok) throw new Error('Failed to fetch progress');

                const progressData = await progressRes.json();
                jobStatus = progressData.status;

                if (jobStatus === 'error') {
                    throw new Error(progressData.error || 'Server download failed');
                }

                setDownloadProgress(prev => ({
                    ...prev,
                    serverProgress: progressData.progress || 0,
                    status: jobStatus
                }));

                if (jobStatus === 'saved') {
                    setSuccessMessage(`Saved to: ${progressData.filename}`);
                    setDownloading(false);
                    return;
                }
            }

        } catch (err) {
            setError(err.message);
            setDownloading(false);
        }
    };

    return (
        <div className="h-screen w-screen bg-black text-white flex flex-col font-sans overflow-hidden m-0 p-0 selection:bg-gray-700 selection:text-white">
            {/* Full width container, no card styling, ensuring full stretch */}
            <div className="flex-1 flex flex-col p-6 w-full h-full max-w-none box-border">

                <div className="text-center mb-6">
                    <h1 className="text-3xl font-bold text-white mb-1 tracking-tight">
                        4K Video Downloader
                    </h1>
                    {/* Removed subtitle as requested */}
                </div>

                <div className="space-y-4 flex-1 flex flex-col">
                    <div className="relative shrink-0">
                        <input
                            type="text"
                            placeholder="Paste YouTube URL here..."
                            className="w-full bg-neutral-900 border border-neutral-800 rounded-lg py-3 px-4 pr-16 focus:outline-none focus:ring-1 focus:ring-white transition-all text-white placeholder-neutral-500 text-sm"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && fetchInfo()}
                        />
                        <button
                            onClick={fetchInfo}
                            disabled={loadingInfo || !url}
                            className="absolute right-1.5 top-1.5 bottom-1.5 bg-white hover:bg-gray-200 disabled:bg-neutral-800 disabled:text-neutral-600 text-black px-4 rounded-md transition-colors text-xs font-bold uppercase tracking-wider"
                        >
                            {loadingInfo ? '...' : 'Get'}
                        </button>
                    </div>

                    {error && (
                        <div className="bg-neutral-900 border border-neutral-800 text-red-400 text-sm p-3 rounded-lg break-words shadow-sm shrink-0">
                            {error}
                        </div>
                    )}

                    {successMessage && (
                        <div className="bg-neutral-900 border border-neutral-800 text-green-400 text-sm p-3 rounded-lg break-words shadow-sm flex flex-col gap-1 shrink-0">
                            <span className="font-bold text-white">Download Complete</span>
                            <span className="text-xs text-gray-400 break-all">{successMessage}</span>
                        </div>
                    )}

                    <div className="animate-fade-in mt-2 space-y-4 flex-1 flex flex-col">
                        {/* Media Preview */}
                        <div className="flex gap-4 bg-neutral-900 p-3 rounded-lg border border-neutral-800 shrink-0">
                            {videoInfo.thumbnail ? (
                                <img
                                    src={videoInfo.thumbnail}
                                    alt="Thumbnail"
                                    className="w-28 h-20 object-cover rounded-md bg-neutral-800"
                                />
                            ) : (
                                <div className="w-28 h-20 rounded-md shrink-0 bg-neutral-800 flex items-center justify-center text-neutral-600 border border-neutral-700">
                                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-8 h-8 opacity-40">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
                                    </svg>
                                </div>
                            )}

                            <div className="flex-1 min-w-0 flex flex-col justify-center">
                                <h3 className={`font-semibold text-sm leading-tight line-clamp-2 ${!videoInfo.thumbnail ? 'text-neutral-500 italic' : 'text-white'}`} title={videoInfo.title}>
                                    {videoInfo.title}
                                </h3>
                                <p className="text-xs text-gray-500 mt-1.5 flex items-center gap-1">
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3 h-3">
                                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z" clipRule="evenodd" />
                                    </svg>
                                    {videoInfo.duration_string || '--:--'}
                                </p>
                            </div>
                        </div>

                        {/* Format Selection */}
                        <div className="space-y-2 mt-auto shrink-0 mb-4">
                            <label className="text-xs text-gray-500 font-bold uppercase tracking-wide ml-1">Select Quality</label>
                            <div className="relative">
                                <select
                                    className="w-full bg-neutral-900 border border-neutral-800 rounded-lg py-3 px-4 text-sm focus:outline-none focus:ring-1 focus:ring-white appearance-none disabled:opacity-50 text-white shadow-sm transition-all hover:bg-neutral-800"
                                    value={selectedFormat}
                                    onChange={(e) => setSelectedFormat(e.target.value)}
                                    disabled={!videoInfo.formats.length}
                                >
                                    {videoInfo.formats.length === 0 ? (
                                        <option>Waiting for video...</option>
                                    ) : (
                                        videoInfo.formats.map((fmt) => (
                                            <option key={fmt.format_id} value={fmt.format_id}>
                                                {fmt.resolution} {fmt.filesize ? `(${Math.round(fmt.filesize / 1024 / 1024)}MB)` : ''} - {fmt.ext.toUpperCase()}
                                            </option>
                                        ))
                                    )}
                                </select>
                                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-gray-500">
                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                                </div>
                            </div>
                        </div>

                        {/* Download Button - With bottom margin to ensure it's not cut off */}
                        <button
                            onClick={handleDownload}
                            disabled={downloading || !videoInfo.formats.length}
                            className="w-full bg-white hover:bg-gray-200 disabled:bg-neutral-800 disabled:text-neutral-600 disabled:cursor-not-allowed text-black font-bold py-3.5 rounded-lg transform active:scale-[0.98] transition-all flex flex-col items-center justify-center gap-1 relative overflow-hidden text-sm border border-transparent shrink-0 mb-2"
                        >
                            {downloading ? (
                                <>
                                    <div className="flex items-center gap-2 z-10">
                                        <svg className="animate-spin h-4 w-4 text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        <span className="font-bold tracking-wide">
                                            {downloadProgress.status === 'downloading' && `${(downloadProgress.serverProgress || 0).toFixed(0)}%`}
                                            {downloadProgress.status === 'merging' && 'Processing...'}
                                            {downloadProgress.status === 'saved' && 'Done'}
                                            {(downloadProgress.status === 'starting' || downloadProgress.status === 'initializing') && 'Starting...'}
                                        </span>
                                    </div>

                                    {/* Progress Bar */}
                                    {(downloadProgress.status === 'downloading' || downloadProgress.status === 'merging') && (
                                        <div
                                            className="absolute bottom-0 left-0 h-1 bg-black/20 transition-all duration-200"
                                            style={{ width: `${downloadProgress.serverProgress}%` }}
                                        />
                                    )}
                                </>
                            ) : (
                                'Download Now'
                            )}
                        </button>
                    </div>

                </div>

                {/* Footer Removed as requested */}
            </div>
        </div>
    )
}

export default App
