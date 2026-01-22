#!/usr/bin/env python3
"""
Xiaohongshu (XHS) Video Downloader
Reads QR code from screenshot, extracts link, and downloads video from the post.
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

import requests
from PIL import Image
from pyzbar.pyzbar import decode


class XHSDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def read_qrcode(self, image_path: str) -> str:
        """Read QR code from an image and return the decoded URL."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        image = Image.open(image_path)
        decoded_objects = decode(image)

        if not decoded_objects:
            raise ValueError("No QR code found in the image")

        # Get the first QR code's data
        qr_data = decoded_objects[0].data.decode('utf-8')
        print(f"QR Code content: {qr_data}")
        return qr_data

    def resolve_short_url(self, url: str) -> str:
        """Follow redirects to get the final URL."""
        try:
            response = self.session.get(url, allow_redirects=True, timeout=10)
            final_url = response.url
            print(f"Resolved URL: {final_url}")
            return final_url
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to resolve URL: {e}")

    def extract_note_id(self, url: str) -> str:
        """Extract the note ID from a Xiaohongshu URL."""
        # Match patterns like /explore/xxx or /discovery/item/xxx
        patterns = [
            r'/explore/([a-zA-Z0-9]+)',
            r'/discovery/item/([a-zA-Z0-9]+)',
            r'/item/([a-zA-Z0-9]+)',
            r'xhslink\.com/([a-zA-Z0-9]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        raise ValueError(f"Could not extract note ID from URL: {url}")

    def get_video_url(self, page_url: str) -> tuple[str, str]:
        """Fetch the page and extract video URL and title."""
        try:
            response = self.session.get(page_url, timeout=15)
            response.raise_for_status()
            html = response.text

            # Try to find video URL in the page's JSON data
            # XHS embeds data in a script tag with __INITIAL_STATE__
            state_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?})</script>', html, re.DOTALL)

            if state_match:
                try:
                    # Clean up the JSON (XHS uses undefined which isn't valid JSON)
                    json_str = state_match.group(1)
                    json_str = re.sub(r':undefined', ':null', json_str)
                    data = json.loads(json_str)

                    # Navigate to find video URL
                    note_data = data.get('note', {}).get('noteDetailMap', {})
                    for note_id, note_info in note_data.items():
                        note = note_info.get('note', {})
                        video = note.get('video', {})

                        # Get title
                        title = note.get('title', 'xhs_video')

                        # Try different video URL locations
                        media_url = video.get('media', {}).get('stream', {}).get('h264', [{}])[0].get('masterUrl')
                        if not media_url:
                            media_url = video.get('url')
                        if not media_url:
                            # Try consumer.originVideoKey
                            origin_key = video.get('consumer', {}).get('originVideoKey')
                            if origin_key:
                                media_url = f"https://sns-video-bd.xhscdn.com/{origin_key}"

                        if media_url:
                            return media_url, self._sanitize_filename(title)
                except json.JSONDecodeError:
                    pass

            # Fallback: Try to find video URL directly in HTML
            # URLs may be escaped with \u002F instead of /
            video_patterns = [
                r'"masterUrl"\s*:\s*"(http[^"]+)"',
                r'"backupUrls"\s*:\s*\["(http[^"]+)"',
            ]

            for pattern in video_patterns:
                match = re.search(pattern, html)
                if match:
                    video_url = match.group(1)
                    # Decode unicode escapes (for URLs with \u002F)
                    video_url = video_url.encode('utf-8').decode('unicode_escape')

                    # Try to get title from the page
                    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', html)
                    title = 'xhs_video'
                    if title_match:
                        # Title is already UTF-8, just sanitize it
                        title = self._sanitize_filename(title_match.group(1))

                    return video_url, title

            raise ValueError("Could not find video URL in the page. This might be an image post.")

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch page: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename."""
        # Remove emojis and special characters
        filename = re.sub(r'[<>:"/\\|?*\n\r]', '', filename)
        filename = filename.strip()[:50]  # Limit length
        return filename if filename else 'xhs_video'

    def download_video(self, video_url: str, output_path: str) -> str:
        """Download video from URL to the specified path."""
        try:
            print(f"Video URL: {video_url}")
            print(f"Downloading video...")

            # Update headers for video download
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                'Referer': 'https://www.xiaohongshu.com/',
            }

            response = self.session.get(video_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()

            # Get total size for progress
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

            print(f"\nVideo saved to: {output_path}")
            return output_path

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to download video: {e}")

    def download_from_screenshot(self, screenshot_path: str, output_dir: str = None) -> str:
        """Main method: Read QR code from screenshot and download the video."""
        # Step 1: Read QR code
        print(f"Reading QR code from: {screenshot_path}")
        qr_url = self.read_qrcode(screenshot_path)

        # Step 2: Resolve short URL if needed
        if 'xhslink.com' in qr_url or len(qr_url) < 50:
            page_url = self.resolve_short_url(qr_url)
        else:
            page_url = qr_url

        # Step 3: Get video URL
        print("Fetching video information...")
        video_url, title = self.get_video_url(page_url)
        print(f"Found video: {title}")

        # Step 4: Download video
        if output_dir is None:
            # Save to the same folder as the screenshot
            output_dir = os.path.dirname(os.path.abspath(screenshot_path))

        output_path = os.path.join(output_dir, f"{title}.mp4")

        # Avoid overwriting
        counter = 1
        base_path = output_path
        while os.path.exists(output_path):
            name, ext = os.path.splitext(base_path)
            output_path = f"{name}_{counter}{ext}"
            counter += 1

        return self.download_video(video_url, output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Download Xiaohongshu videos from QR code screenshots'
    )
    parser.add_argument(
        'screenshot',
        help='Path to the screenshot image containing the QR code'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory for the downloaded video (default: current directory)',
        default=None
    )
    parser.add_argument(
        '-u', '--url',
        action='store_true',
        help='Treat input as URL instead of screenshot path'
    )

    args = parser.parse_args()

    downloader = XHSDownloader()

    try:
        if args.url:
            # Direct URL mode
            print(f"Processing URL: {args.screenshot}")
            if 'xhslink.com' in args.screenshot:
                page_url = downloader.resolve_short_url(args.screenshot)
            else:
                page_url = args.screenshot

            video_url, title = downloader.get_video_url(page_url)
            output_dir = args.output or os.getcwd()
            output_path = os.path.join(output_dir, f"{title}.mp4")
            downloader.download_video(video_url, output_path)
        else:
            # Screenshot mode
            downloader.download_from_screenshot(args.screenshot, args.output)

        print("Done!")

    except Exception as e:
        print(f"\033[91mError: {e}\033[0m", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
