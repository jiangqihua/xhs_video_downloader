#!/usr/bin/env python3
"""
Video Downloader for Xiaohongshu, Weibo, and Instagram
Reads QR code from screenshot, auto-detects platform, and downloads video from the post.
"""

import argparse
import glob
import json
import os
import random
import re
import sys
import time
from abc import ABC, abstractmethod

import cv2
import requests
import yt_dlp
from PIL import Image
from pyzbar.pyzbar import decode


def read_qrcode(image_path: str) -> str:
    """Read QR code from an image with enhanced detection."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Try pyzbar first with original image
    image = Image.open(image_path)
    decoded_objects = decode(image)

    if decoded_objects:
        qr_data = decoded_objects[0].data.decode('utf-8')
        return qr_data

    # If failed, try with OpenCV
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")

    # Use OpenCV QR detector to locate QR code position
    detector = cv2.QRCodeDetector()
    data, vertices, _ = detector.detectAndDecode(img)

    # If OpenCV decoded it directly, return
    if data:
        return data

    # If QR code located but not decoded, crop and scale that region
    if vertices is not None and len(vertices) > 0:
        pts = vertices[0].astype(int)
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)

        # Add padding
        padding = 50
        h, w = img.shape[:2]
        x_min = max(0, x_min - padding)
        y_min = max(0, y_min - padding)
        x_max = min(w, x_max + padding)
        y_max = min(h, y_max + padding)

        # Crop and scale
        qr_region = img[y_min:y_max, x_min:x_max]
        scaled = cv2.resize(qr_region, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

        # Try pyzbar on scaled crop
        scaled_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        scaled_pil = Image.fromarray(scaled_rgb)
        decoded_objects = decode(scaled_pil)

        if decoded_objects:
            qr_data = decoded_objects[0].data.decode('utf-8')
            return qr_data

    # Try scanning bottom portion of image (common QR code location)
    h, w = img.shape[:2]
    bottom_region = img[int(h * 0.6):, :]  # Bottom 40% of image

    # Try multiple scale factors on bottom region
    for scale in [2, 3, 4]:
        scaled = cv2.resize(bottom_region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        scaled_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        scaled_pil = Image.fromarray(scaled_rgb)
        decoded_objects = decode(scaled_pil)
        if decoded_objects:
            qr_data = decoded_objects[0].data.decode('utf-8')
            return qr_data

    # Try with grayscale and contrast enhancement
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    for scale in [2, 3]:
        scaled = cv2.resize(enhanced, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        scaled_pil = Image.fromarray(scaled)
        decoded_objects = decode(scaled_pil)
        if decoded_objects:
            qr_data = decoded_objects[0].data.decode('utf-8')
            return qr_data

    # Try binary thresholding
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    scaled = cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    scaled_pil = Image.fromarray(scaled)
    decoded_objects = decode(scaled_pil)
    if decoded_objects:
        qr_data = decoded_objects[0].data.decode('utf-8')
        return qr_data

    # Last resort: scale entire image with different factors
    for scale in [2, 3]:
        scaled = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        scaled_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        scaled_pil = Image.fromarray(scaled_rgb)
        decoded_objects = decode(scaled_pil)
        if decoded_objects:
            qr_data = decoded_objects[0].data.decode('utf-8')
            return qr_data

    raise ValueError("No QR code found in the image")


def detect_platform(url: str) -> str:
    """Detect which platform the URL belongs to."""
    url_lower = url.lower()
    if 'weibo.com' in url_lower or 'weibo.cn' in url_lower:
        return 'weibo'
    elif 'xiaohongshu.com' in url_lower or 'xhslink.com' in url_lower:
        return 'xiaohongshu'
    elif 'instagram.com' in url_lower:
        return 'instagram'
    else:
        raise ValueError(f"Unknown platform for URL: {url}")


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename."""
    # Remove HTML tags
    filename = re.sub(r'<[^>]+>', '', filename)
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*\n\r]', '', filename)
    filename = filename.strip()[:50]
    return filename if filename else 'video'


class BaseDownloader(ABC):
    """Base class for video downloaders."""

    def __init__(self):
        self.session = requests.Session()

    @abstractmethod
    def get_video_info(self, url: str) -> tuple[str, str]:
        """Get video URL and title from page URL."""
        pass

    def download_video(self, video_url: str, output_path: str, referer: str = None) -> str:
        """Download video from URL to the specified path."""
        print(f"Video URL: {video_url}")
        print(f"Downloading video...")

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
        }
        if referer:
            headers['Referer'] = referer

        response = self.session.get(video_url, headers=headers, stream=True, timeout=120)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.1f}%", end='', flush=True)

        file_size = os.path.getsize(output_path)
        if file_size >= 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{file_size / 1024:.1f} KB"
        print(f"\nVideo saved to: {output_path} ({size_str})")
        return output_path


class XiaohongshuDownloader(BaseDownloader):
    """Downloader for Xiaohongshu videos."""

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def resolve_short_url(self, url: str) -> str:
        """Follow redirects to get the final URL."""
        response = self.session.get(url, allow_redirects=True, timeout=10)
        return response.url

    def get_video_info(self, url: str) -> tuple[str, str]:
        """Fetch the page and extract video URL and title."""
        # Resolve short URL if needed
        if 'xhslink.com' in url:
            url = self.resolve_short_url(url)
            print(f"Resolved URL: {url}")

        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        html = response.text

        # Try to find video URL directly in HTML
        video_patterns = [
            r'"masterUrl"\s*:\s*"(http[^"]+)"',
            r'"backupUrls"\s*:\s*\["(http[^"]+)"',
        ]

        for pattern in video_patterns:
            match = re.search(pattern, html)
            if match:
                video_url = match.group(1)
                video_url = video_url.encode('utf-8').decode('unicode_escape')

                # Try to get title
                title_match = re.search(r'"title"\s*:\s*"([^"]+)"', html)
                title = 'xhs_video'
                if title_match:
                    title = sanitize_filename(title_match.group(1))

                return video_url, title

        raise ValueError("Could not find video URL. This might be an image post.")

    def download(self, url: str, output_dir: str) -> str:
        """Download video from Xiaohongshu URL."""
        print("Platform: Xiaohongshu")
        print("Fetching video information...")

        video_url, title = self.get_video_info(url)
        print(f"Found video: {title}")

        output_path = os.path.join(output_dir, f"{title}.mp4")
        output_path = get_unique_path(output_path)

        return self.download_video(video_url, output_path, referer='https://www.xiaohongshu.com/')


class WeiboDownloader(BaseDownloader):
    """Downloader for Weibo videos."""

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://m.weibo.cn/',
            'X-Requested-With': 'XMLHttpRequest',
        })

    def extract_status_id(self, url: str) -> str:
        """Extract status ID from Weibo URL."""
        # Pattern: weibo.com/userid/statusid or m.weibo.cn/status/statusid
        patterns = [
            r'weibo\.com/\d+/(\d+)',
            r'weibo\.cn/status/(\d+)',
            r'/(\d{16,})',  # Status IDs are typically 16+ digits
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        raise ValueError(f"Could not extract status ID from URL: {url}")

    def get_video_info(self, url: str) -> tuple[str, str]:
        """Get video URL and title from Weibo API."""
        status_id = self.extract_status_id(url)
        api_url = f'https://m.weibo.cn/statuses/show?id={status_id}'

        response = self.session.get(api_url, timeout=15)
        response.raise_for_status()

        data = response.json()
        if data.get('ok') != 1:
            raise ValueError(f"Failed to get Weibo status: {data.get('msg', 'Unknown error')}")

        status = data.get('data', {})
        page_info = status.get('page_info', {})

        if page_info.get('type') != 'video':
            raise ValueError("This Weibo post does not contain a video.")

        # Get video URLs (prefer highest quality)
        urls = page_info.get('urls', {})
        video_url = urls.get('mp4_720p_mp4') or urls.get('mp4_hd_mp4') or urls.get('mp4_ld_mp4')

        if not video_url:
            # Try media_info as fallback
            media_info = page_info.get('media_info', {})
            video_url = media_info.get('stream_url_hd') or media_info.get('stream_url')

        if not video_url:
            raise ValueError("Could not find video URL in Weibo response.")

        # Get title from text or user name
        text = status.get('text', '')
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        user_name = status.get('user', {}).get('screen_name', 'weibo')

        title = sanitize_filename(text) if text else f"weibo_{user_name}"

        return video_url, title

    def download(self, url: str, output_dir: str) -> str:
        """Download video from Weibo URL."""
        print("Platform: Weibo")
        print("Fetching video information...")

        video_url, title = self.get_video_info(url)
        print(f"Found video: {title}")

        output_path = os.path.join(output_dir, f"{title}.mp4")
        output_path = get_unique_path(output_path)

        return self.download_video(video_url, output_path, referer='https://m.weibo.cn/')


class InstagramDownloader(BaseDownloader):
    """Downloader for Instagram videos using yt-dlp."""

    def __init__(self, cookies_from_browser: str = None, cookies_file: str = None):
        super().__init__()
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file

    def _build_ydl_opts(self, use_cookies: bool = False) -> dict:
        """Build yt-dlp options dict."""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        if use_cookies:
            if self.cookies_file:
                opts['cookiefile'] = self.cookies_file
            elif self.cookies_from_browser:
                opts['cookiesfrombrowser'] = (self.cookies_from_browser,)
            else:
                # Default to chrome when retrying with cookies
                opts['cookiesfrombrowser'] = ('chrome',)
        return opts

    def _extract_info(self, url: str, ydl_opts: dict) -> dict:
        """Extract video info using yt-dlp."""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def _parse_video_info(self, info: dict) -> tuple[str, str]:
        """Parse video URL and title from extracted info."""
        if not info:
            raise ValueError("Could not extract video information from Instagram.")

        # Get the best format with video (prefer progressive mp4)
        formats = info.get('formats', [])
        video_url = None

        # First try to find a progressive format (has both video and audio)
        for fmt in formats:
            if fmt.get('ext') == 'mp4' and fmt.get('acodec') != 'none' and fmt.get('vcodec') != 'none':
                video_url = fmt.get('url')
                break

        # Fallback to the default URL
        if not video_url:
            video_url = info.get('url')

        if not video_url:
            raise ValueError("Could not find video URL in Instagram response.")

        # Get title from description or channel
        title = info.get('description', '')
        if title:
            title = sanitize_filename(title)
        if not title:
            title = f"instagram_{info.get('channel', info.get('id', 'video'))}"

        return video_url, title

    def get_video_info(self, url: str) -> tuple[str, str]:
        """Get video URL and title using yt-dlp, with cookie fallback on rate limit."""
        # First attempt: without cookies
        try:
            info = self._extract_info(url, self._build_ydl_opts(use_cookies=False))
            return self._parse_video_info(info)
        except Exception as e:
            error_msg = str(e).lower()
            if 'rate-limit' in error_msg or 'login required' in error_msg or 'requested content is not available' in error_msg:
                cookie_source = self.cookies_file or self.cookies_from_browser or 'chrome'
                print(f"Rate limited without cookies, retrying with cookies from {cookie_source}...")
                info = self._extract_info(url, self._build_ydl_opts(use_cookies=True))
                return self._parse_video_info(info)
            raise

    def download(self, url: str, output_dir: str) -> str:
        """Download video from Instagram URL."""
        print("Platform: Instagram")
        print("Fetching video information...")

        video_url, title = self.get_video_info(url)
        print(f"Found video: {title}")

        output_path = os.path.join(output_dir, f"{title}.mp4")
        output_path = get_unique_path(output_path)

        return self.download_video(video_url, output_path, referer='https://www.instagram.com/')


def get_unique_path(output_path: str) -> str:
    """Get a unique file path to avoid overwriting."""
    if not os.path.exists(output_path):
        return output_path

    counter = 1
    base, ext = os.path.splitext(output_path)
    while os.path.exists(output_path):
        output_path = f"{base}_{counter}{ext}"
        counter += 1
    return output_path


def download_from_screenshot(screenshot_path: str, output_dir: str = None,
                             cookies_from_browser: str = None, cookies_file: str = None) -> tuple[str, str]:
    """Read QR code from screenshot and download video.

    Returns:
        A tuple of (output_path, platform).
    """
    print(f"Reading QR code from: {screenshot_path}")
    qr_url = read_qrcode(screenshot_path)
    print(f"QR Code content: {qr_url}")

    # Detect platform
    platform = detect_platform(qr_url)

    # Set output directory to same folder as screenshot if not specified
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(screenshot_path))

    # Use appropriate downloader
    if platform == 'weibo':
        downloader = WeiboDownloader()
    elif platform == 'instagram':
        downloader = InstagramDownloader(cookies_from_browser, cookies_file)
    else:
        downloader = XiaohongshuDownloader()

    return downloader.download(qr_url, output_dir), platform


def download_from_url(url: str, output_dir: str = None,
                      cookies_from_browser: str = None, cookies_file: str = None) -> str:
    """Download video directly from URL."""
    print(f"Processing URL: {url}")

    platform = detect_platform(url)

    if output_dir is None:
        output_dir = os.getcwd()

    if platform == 'weibo':
        downloader = WeiboDownloader()
    elif platform == 'instagram':
        downloader = InstagramDownloader(cookies_from_browser, cookies_file)
    else:
        downloader = XiaohongshuDownloader()

    return downloader.download(url, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Download videos from Xiaohongshu, Weibo, or Instagram via QR code screenshots'
    )
    parser.add_argument(
        'input',
        nargs='*',
        help='Path(s) to screenshot image(s) or URL (with -u flag)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory for the downloaded video',
        default=None
    )
    parser.add_argument(
        '-u', '--url',
        action='store_true',
        help='Treat input as URL instead of screenshot path'
    )
    parser.add_argument(
        '-b', '--batch',
        action='store_true',
        help='Batch mode: process multiple screenshots'
    )
    parser.add_argument(
        '--cookies-from-browser',
        help='Browser to extract cookies from for Instagram (e.g. chrome, firefox, safari)',
        default=None
    )
    parser.add_argument(
        '--cookies',
        help='Path to Netscape-format cookies file for Instagram',
        default=None
    )

    args = parser.parse_args()

    if not args.input:
        parser.error("input is required")

    if len(args.input) > 1 and not args.batch:
        parser.error("multiple inputs require --batch flag")

    # Batch mode
    if args.batch:
        print(f"Found {len(args.input)} file(s) to process\n")
        success = 0
        failed = 0

        for i, filepath in enumerate(args.input, 1):
            print(f"[{i}/{len(args.input)}] Processing: {filepath}")
            print("-" * 50)
            try:
                _, platform = download_from_screenshot(filepath, args.output,
                                                       args.cookies_from_browser, args.cookies)
                success += 1
                # Delay between Instagram downloads to avoid rate limiting
                if platform == 'instagram' and i < len(args.input):
                    delay = random.uniform(3, 6)
                    print(f"Waiting {delay:.1f}s to avoid Instagram rate limiting...")
                    time.sleep(delay)
                print()
            except Exception as e:
                print(f"\033[91mError: {e}\033[0m\n", file=sys.stderr)
                failed += 1

        print("=" * 50)
        print(f"Batch complete: {success} succeeded, {failed} failed")
        sys.exit(0 if failed == 0 else 1)

    # Single file mode
    try:
        if args.url:
            download_from_url(args.input[0], args.output,
                              args.cookies_from_browser, args.cookies)
        else:
            download_from_screenshot(args.input[0], args.output,
                                     args.cookies_from_browser, args.cookies)

        print("Done!")

    except Exception as e:
        print(f"\033[91mError: {e}\033[0m", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
