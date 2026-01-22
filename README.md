# Video Downloader

Download videos from Xiaohongshu (小红书) and Weibo (微博) posts by scanning QR codes from screenshots.

## Features

- Multi-platform support: Xiaohongshu and Weibo
- Enhanced QR code reading with OpenCV fallback
- Automatic platform detection from URL
- Auto-resolve short URLs (xhslink.com)
- Download videos with original Chinese titles
- Progress display during download
- Support for direct URL input

## Requirements

- Python 3.9+
- zbar system library

## Installation

1. Install the zbar system library:
```bash
brew install zbar
```

2. Create virtual environment and install dependencies:
```bash
cd xhs_video_downloader
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Usage

### From Screenshot (QR Code)

```bash
./venv/bin/python video_downloader.py /path/to/screenshot.png
```

The video will be saved in the same folder as the screenshot.

### With Custom Output Directory

```bash
./venv/bin/python video_downloader.py /path/to/screenshot.png -o /path/to/output
```

### Batch Mode

Process multiple screenshots at once:
```bash
./venv/bin/python video_downloader.py --batch "screenshots/*.PNG"
```

With custom output directory:
```bash
./venv/bin/python video_downloader.py --batch "weibo/*.PNG" -o ./videos
```

### Direct URL Mode

**Xiaohongshu:**
```bash
./venv/bin/python video_downloader.py -u "https://www.xiaohongshu.com/explore/xxx"
```

**Weibo:**
```bash
./venv/bin/python video_downloader.py -u "https://weibo.com/userid/statusid"
```

Or with short URL:
```bash
./venv/bin/python video_downloader.py -u "http://xhslink.com/xxx"
```

## Example Output

```
Reading QR code from: screenshot.png
QR Code content: http://xhslink.com/m/xxx
Platform: Xiaohongshu
Resolved URL: https://www.xiaohongshu.com/discovery/item/xxx
Fetching video information...
Found video: 视频标题
Video URL: http://sns-video-zl.xhscdn.com/stream/xxx.mp4
Downloading video...
Progress: 100.0%
Video saved to: /path/to/视频标题.mp4
Done!
```

## Technical Details

### How It Works

1. **QR Code Reading**: Uses `pyzbar` library with OpenCV fallback for enhanced detection:
   - First attempts with pyzbar on original image
   - Falls back to OpenCV QR detector
   - Tries cropping and scaling detected QR region
   - Last resort: scales entire image 2x

2. **Platform Detection**: Automatically detects platform from URL:
   - `xiaohongshu.com` or `xhslink.com` → Xiaohongshu
   - `weibo.com` or `weibo.cn` → Weibo

3. **Video Extraction**:
   - **Xiaohongshu**: Parses `masterUrl` from embedded page data
   - **Weibo**: Uses mobile API (`m.weibo.cn/statuses/show`) to get video URLs, preferring 720p quality

4. **Download**: Videos are downloaded with streaming to handle large files, showing progress percentage.

### Dependencies

| Package | Purpose |
|---------|---------|
| `requests` | HTTP requests for fetching pages and downloading videos |
| `Pillow` | Image processing for loading screenshots |
| `pyzbar` | QR code decoding (requires zbar system library) |
| `opencv-python` | Enhanced QR code detection and image processing |

### File Structure

```
xhs_video_downloader/
├── video_downloader.py  # Main script (multi-platform)
├── xhs_downloader.py    # Legacy Xiaohongshu-only script
├── requirements.txt     # Python dependencies
├── test/                # Test screenshots
├── venv/                # Virtual environment
└── README.md            # This file
```

### Supported Platforms

| Platform | URL Patterns | Video Source |
|----------|--------------|--------------|
| Xiaohongshu | `xiaohongshu.com`, `xhslink.com` | Page embedded data |
| Weibo | `weibo.com`, `weibo.cn`, `m.weibo.cn` | Mobile API |

### Limitations

- Only works with video posts, not image posts
- Requires the post to be publicly accessible
- QR code must be visible in the screenshot
- Video URLs may expire after some time

## Troubleshooting

### "No QR code found in the image"
- Ensure the QR code is clearly visible and not cropped
- Try a higher resolution screenshot
- The enhanced OpenCV detection should handle most cases

### "Could not find video URL in the page"
- The post might be an image post, not a video
- The post might be private or deleted

### "Unable to find zbar shared library"
- Install zbar: `brew install zbar`

### "This Weibo post does not contain a video"
- The Weibo post is text or image only, not a video post
