#!/usr/bin/env python3
import argparse
import subprocess
import os
from pathlib import Path
import ffmpeg

def download_video(url, output_path, platform, vertical=False):
    """Download video from YouTube or TikTok using yt-dlp"""
    try:
        # Base command for yt-dlp
        cmd = ['yt-dlp', '-f', 'best', '-o', str(output_path)]
        
        # Add platform-specific options if needed
        if platform == 'tiktok':
            cmd.extend(['--user-agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Mobile/15E148 Safari/604.1'])
        
        # Add URL to command
        cmd.append(url)
        
        # Execute download
        subprocess.run(cmd, check=True)
        
        # Handle vertical videos if requested
        if vertical:
            temp_path = output_path.with_suffix('.temp.mp4')
            os.rename(output_path, temp_path)
            
            # Rotate video to portrait orientation
            (
                ffmpeg
                .input(str(temp_path))
                .filter('scale', 720, 1280)
                .filter('rotate', 0)
                .output(str(output_path))
                .run(overwrite_output=True)
            )
            os.remove(temp_path)
            
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error downloading video: {e}")
        return False

def convert_for_flipper(input_path, output_path, args):
    """Convert video for Flipper Zero (simplified version)"""
    try:
        # Basic video conversion pipeline
        video = (
            ffmpeg
            .input(str(input_path))
            .filter('scale', args.width, args.height)
            .filter('fps', fps=args.fps)
            .filter('format', 'gray')
        )
        
        # Add dithering if requested
        if args.dither:
            video = video.filter('dither', args.dither_type)
        
        # Basic audio conversion
        audio = (
            ffmpeg
            .input(str(input_path))
            .audio
            .filter('aformat', sample_rates=args.sample_rate)
            .filter('volume', 1.0)
        )
        
        # Complex output command
        output = (
            ffmpeg
            .output(video, audio, str(output_path), format='mp4')
            .overwrite_output()
        )
        
        # Run the command
        output.run()
        return True
    except ffmpeg.Error as e:
        print(f"Error converting video: {e}")
        return False

def convert_to_wav(input_path, output_path):
    """Convert audio file to WAV format"""
    try:
        (
            ffmpeg
            .input(str(input_path))
            .output(str(output_path), format='wav')
            .overwrite_output()
            .run()
        )
        return True
    except ffmpeg.Error as e:
        print(f"Error converting audio: {e}")
        return False

def process_link_file(file_path, platform, output_dir, vertical=False):
    """Process all links from a text file"""
    try:
        with open(file_path, 'r') as f:
            links = [line.strip() for line in f if line.strip()]
        
        results = []
        for i, link in enumerate(links, 1):
            print(f"Processing link {i}/{len(links)}: {link}")
            
            # Generate output filename from URL
            filename = link.split('/')[-1][:20]  # Take last part of URL
            output_path = output_dir / f"{filename}.mp4"
            
            success = download_video(link, output_path, platform, vertical)
            results.append((link, success))
        
        return results
    except Exception as e:
        print(f"Error processing link file: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Media processing utility')
    
    # Operation mode group
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--download-youtube', action='store_true', help='Download a YouTube video or playlist')
    mode_group.add_argument('--download-tiktok', action='store_true', help='Download a TikTok video')
    mode_group.add_argument('--convert-video', action='store_true', help='Convert video for Flipper Zero')
    mode_group.add_argument('--convert-music', action='store_true', help='Convert audio to WAV format')
    
    # Input options
    parser.add_argument('url_or_path', nargs='?', help='URL to download or path to file to convert')
    parser.add_argument('--input-list', type=Path, help='Path to TXT file containing list of URLs')
    
    # Output options
    parser.add_argument('--set-output', type=Path, help='Path to output file')
    parser.add_argument('--output-dir', type=Path, help='Output directory for multiple files')
    
    # Video conversion options
    parser.add_argument('--width', type=int, default=128, help='Video width (max 128)')
    parser.add_argument('--height', type=int, default=64, help='Video height (max 64)')
    parser.add_argument('--fps', type=int, default=10, help='Video frame rate')
    parser.add_argument('--dither', action='store_true', help='Apply dithering to video')
    parser.add_argument('--dither-type', default='floyd_steinberg', help='Type of dithering to apply')
    parser.add_argument('--sample-rate', type=int, default=8000, help='Audio sample rate (Hz)')
    
    # Platform-specific options
    parser.add_argument('--vertical', action='store_true', help='Download and process video in vertical orientation')
    
    args = parser.parse_args()
    
    # Validate input/output options based on mode
    if args.download_youtube or args.download_tiktok:
        if not args.input_list and not args.url_or_path:
            parser.error("Either URL or --input-list must be provided for download operations")
            
        if args.input_list:
            if not args.output_dir:
                parser.error("--output-dir must be specified when using --input-list")
            args.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            if not args.set_output:
                parser.error("--set-output must be specified for single video download")
            args.set_output.parent.mkdir(parents=True, exist_ok=True)
            
    elif args.convert_video or args.convert_music:
        if not args.url_or_path or not args.set_output:
            parser.error("Both input path and output path must be specified for conversion operations")
        args.set_output.parent.mkdir(parents=True, exist_ok=True)
    
    # Process according to operation mode
    if args.download_youtube or args.download_tiktok:
        platform = 'youtube' if args.download_youtube else 'tiktok'
        
        if args.input_list:
            # Process all links from the list
            results = process_link_file(args.input_list, platform, args.output_dir, args.vertical)
            
            if results:
                print("\nDownload Results:")
                for link, success in results:
                    print(f"{link}: {'Success' if success else 'Failed'}")
        else:
            # Single video download
            print(f"Downloading {platform} video from {args.url_or_path}")
            success = download_video(args.url_or_path, args.set_output, platform, args.vertical)
            print(f"Download {'successful' if success else 'failed'}: {args.set_output}")
            
    elif args.convert_video:
        print(f"Converting video {args.url_or_path} for Flipper Zero")
        success = convert_for_flipper(Path(args.url_or_path), args.set_output, args)
        print(f"Video conversion {'successful' if success else 'failed'}: {args.set_output}")
            
    elif args.convert_music:
        print(f"Converting audio {args.url_or_path} to WAV format")
        success = convert_to_wav(Path(args.url_or_path), args.set_output)
        print(f"Audio conversion {'successful' if success else 'failed'}: {args.set_output}")

if __name__ == "__main__":
    main()
