# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python CLI tool that downloads videos from Xiaohongshu (小红书), Weibo (微博), and Instagram by scanning QR codes from screenshots or processing direct URLs.

## Commands

### Setup
```bash
brew install zbar  # Required system dependency
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### Run
```bash
# From screenshot
./venv/bin/python video_downloader.py /path/to/screenshot.png

# From URL
./venv/bin/python video_downloader.py -u "https://www.xiaohongshu.com/explore/xxx"

# Batch mode
./venv/bin/python video_downloader.py --batch "screenshots/*.PNG"

# With custom output directory
./venv/bin/python video_downloader.py screenshot.png -o /path/to/output
```

## Architecture

The main script is `video_downloader.py` with a class-based design:

- `BaseDownloader` (ABC): Abstract base class defining the download interface
  - `XiaohongshuDownloader`: Extracts video from embedded `masterUrl` in page HTML
  - `WeiboDownloader`: Uses mobile API (`m.weibo.cn/statuses/show`) to fetch video URLs
  - `InstagramDownloader`: Uses yt-dlp library to extract video URLs

- `read_qrcode()`: Multi-strategy QR detection using pyzbar with OpenCV fallbacks (scaling, cropping, CLAHE enhancement, binary thresholding)

- `detect_platform()`: Routes URLs to correct downloader based on domain patterns

Platform detection rules:
- `xiaohongshu.com`, `xhslink.com` → XiaohongshuDownloader
- `weibo.com`, `weibo.cn` → WeiboDownloader
- `instagram.com` → InstagramDownloader

The `legacy/xhs_downloader.py` file is a deprecated Xiaohongshu-only version kept for reference.
