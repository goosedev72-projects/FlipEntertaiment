#!/usr/bin/env python3
import argparse
import subprocess
import os
from pathlib import Path
import ffmpeg
import shutil

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
        print(f"Downloading video from {url}...")
        subprocess.run(cmd, check=True)
        
        # Handle vertical videos if requested
        if vertical:
            temp_path = output_path.with_suffix('.temp.mp4')
            os.rename(output_path, temp_path)
            
            # Rotate video to portrait orientation
            print("Rotating video to vertical orientation...")
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

def extract_frames(input_path, frames_dir, width, height, fps):
    """Extract and convert frames to BMP format"""
    print(f"Extracting frames to {frames_dir}...")
    
    # Create frames directory if it doesn't exist
    frames_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear existing frames
    for f in frames_dir.glob("frame*.bmp"):
        f.unlink()
    
    # FFmpeg command to extract frames
    frame_pattern = str(frames_dir / "frame%07d.bmp")
    
    try:
        (
            ffmpeg
            .input(str(input_path))
            .filter('fps', fps=fps)
            .filter('scale', width, height)
            .filter('format', 'gray')
            .output(frame_pattern)
            .run(overwrite_output=True)
        )
        return True
    except ffmpeg.Error as e:
        print(f"Error extracting frames: {e}")
        return False

def extract_audio(input_path, audio_path, sample_rate=44100):
    """Extract audio to WAV format"""
    print(f"Extracting audio to {audio_path}...")
    
    try:
        (
            ffmpeg
            .input(str(input_path))
            .audio
            .filter('aformat', sample_rates=sample_rate)
            .filter('volume', 1.0)
            .output(str(audio_path))
            .run(overwrite_output=True)
        )
        return True
    except ffmpeg.Error as e:
        print(f"Error extracting audio: {e}")
        return False

def create_bundle(frames_dir, audio_path, output_path, width, height, fps, sample_rate=44100):
    """Create bundle file from frames and audio"""
    print(f"Creating bundle file {output_path}...")
    
    try:
        # Calculate audio chunk size
        audio_chunk_size = sample_rate // fps
        
        # Open files
        audio_data = open(audio_path, 'rb').read()
        audio_pos = 0
        
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as bundle:
            # Write header
            bundle.write(b'BND!VID')  # Signature
            bundle.write(struct.pack('<B', 1))  # Version
            
            # Count frames
            frame_files = sorted(frames_dir.glob("frame*.bmp"))
            num_frames = len(frame_files)
            bundle.write(struct.pack('<I', num_frames))  # Frame count
            
            # Write audio chunk size
            bundle.write(struct.pack('<H', audio_chunk_size))
            
            # Write sample rate
            bundle.write(struct.pack('<H', sample_rate))
            
            # Write frame dimensions
            bundle.write(struct.pack('<B', height))
            bundle.write(struct.pack('<B', width))
            
            # Process each frame
            for i, frame_file in enumerate(frame_files):
                print(f"Processing frame {i+1}/{num_frames}")
                
                # Load image
                img = Image.open(frame_file).convert('1')  # Convert to black & white
                pixels = list(img.getdata())
                
                # Create byte data
                byte_data = bytearray()
                for j in range(0, height * width, 8):
                    byte = 0
                    for k in range(8):
                        if j + k < len(pixels) and pixels[j + k] == 0:
                            byte |= 1 << k
                    byte_data.append(byte)
                
                # Write frame data
                bundle.write(byte_data)
                
                # Write corresponding audio chunk
                chunk_end = audio_pos + audio_chunk_size
                if chunk_end > len(audio_data):
                    chunk_end = len(audio_data)
                bundle.write(audio_data[audio_pos:chunk_end])
                audio_pos = chunk_end
            
        return True
    except Exception as e:
        print(f"Error creating bundle: {e}")
        return False

def process_link_file(file_path, platform, output_dir, width, height, fps, sample_rate, vertical):
    """Process all links from a text file"""
    try:
        with open(file_path, 'r') as f:
            links = [line.strip() for line in f if line.strip()]
        
        results = []
        for i, link in enumerate(links, 1):
            print(f"\nProcessing link {i}/{len(links)}: {link}")
            
            # Generate output filename from URL
            filename = link.split('/')[-1][:20]  # Take last part of URL
            output_dir.mkdir(parents=True, exist_ok=True)
            video_path = output_dir / f"{filename}.mp4"
            temp_dir = Path("temp") / filename
            output_bundle = output_dir / f"{filename}.bnd"
            
            # Download video
            if download_video(link, video_path, platform, vertical):
                # Process video
                if process_video(video_path, temp_dir, output_bundle, width, height, fps, sample_rate):
                    results.append((link, True))
                else:
                    results.append((link, False))
            else:
                results.append((link, False))
        
        return results
    except Exception as e:
        print(f"Error processing link file: {e}")
        return []

def process_video(video_path, temp_dir, output_path, width, height, fps, sample_rate):
    """Process downloaded video to create bundle file"""
    print(f"\nProcessing video {video_path}...")
    
    # Create temporary directory
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract frames
    frames_dir = temp_dir / "frames"
    if not extract_frames(video_path, frames_dir, width, height, fps):
        return False
    
    # Extract audio
    audio_path = temp_dir / "audio.wav"
    if not extract_audio(video_path, audio_path, sample_rate):
        return False
    
    # Create bundle
    if not create_bundle(frames_dir, audio_path, output_path, width, height, fps, sample_rate):
        return False
    
    # Clean up temporary files
    for f in temp_dir.glob("frames/*.bmp"):
        f.unlink()
    if audio_path.exists():
        audio_path.unlink()
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Media processing utility for Flipper Zero')
    
    # Operation mode group
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--download-youtube', action='store_true', help='Download a YouTube video or playlist')
    mode_group.add_argument('--download-tiktok', action='store_true', help='Download a TikTok video')
    
    # Input options
    parser.add_argument('url_or_path', nargs='?', help='URL to download or path to file to convert')
    parser.add_argument('--input-list', type=Path, help='Path to TXT file containing list of URLs')
    
    # Output options
    parser.add_argument('--output-dir', type=Path, default=Path("output"), help='Output directory for processed files')
    
    # Video conversion options
    parser.add_argument('--width', type=int, default=128, help='Video width (max 128)')
    parser.add_argument('--height', type=int, default=64, help='Video height (max 64)')
    parser.add_argument('--fps', type=int, default=24, help='Video frame rate')
    parser.add_argument('--sample-rate', type=int, default=44100, help='Audio sample rate (Hz)')
    
    # Platform-specific options
    parser.add_argument('--vertical', action='store_true', help='Download and process video in vertical orientation')
    
    args = parser.parse_args()
    
    # Validate input/output options based on mode
    if args.download_youtube or args.download_tiktok:
        if not args.input_list and not args.url_or_path:
            parser.error("Either URL or --input-list must be provided for download operations")
            
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process according to operation mode
    if args.download_youtube or args.download_tiktok:
        platform = 'youtube' if args.download_youtube else 'tiktok'
        
        if args.input_list:
            # Process all links from the list
            results = process_link_file(
                args.input_list, 
                platform, 
                args.output_dir,
                args.width,
                args.height,
                args.fps,
                args.sample_rate,
                args.vertical
            )
            
            if results:
                print("\nDownload & Conversion Results:")
                for link, success in results:
                    print(f"{link}: {'Success' if success else 'Failed'}")
        else:
            # Single video download
            print(f"Downloading {platform} video from {args.url_or_path}")
            filename = args.url_or_path.split('/')[-1][:20]
            video_path = args.output_dir / f"{filename}.mp4"
            temp_dir = Path("temp") / filename
            output_bundle = args.output_dir / f"{filename}.bnd"
            
            if download_video(args.url_or_path, video_path, platform, args.vertical):
                if process_video(video_path, temp_dir, output_bundle, args.width, args.height, args.fps, args.sample_rate):
                    print(f"✅ Conversion successful: {output_bundle}")
                else:
                    print("❌ Conversion failed")
            else:
                print("❌ Download failed")

if __name__ == "__main__":
    import struct
    from PIL import Image
    main()
                      
