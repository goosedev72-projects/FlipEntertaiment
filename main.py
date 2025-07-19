#!/usr/bin/env python3
import argparse
import shutil
import struct
from pathlib import Path

import ffmpeg
import yt_dlp
from PIL import Image

def download_youtube_video(video_url: str, output_path: Path, vertical: bool = False) -> Path:
    """
    Скачивает видео с YouTube (или другой поддерживаемой платформы) через API yt_dlp.
    Возвращает путь к скачанному MP4-файлу.
    """
    output_path.mkdir(parents=True, exist_ok=True)
    # Шаблон имени: <title>.mp4
    template = str(output_path / '%(title).200s.%(ext)s')

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': template,
        'merge_output_format': 'mp4',
        # Отключим прогресс-бар, чтобы был чище вывод
        'quiet': False,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = ydl.prepare_filename(info)

    # yt_dlp иногда скачивает m4a и mp4 и автоматически мёржит их,
    # но имя может быть без .mp4 — убедимся, что у нас .mp4
    mp4_file = Path(filename)
    if mp4_file.suffix.lower() != '.mp4':
        alt = mp4_file.with_suffix('.mp4')
        if alt.exists():
            mp4_file.unlink()
        mp4_file = mp4_file.with_suffix('.mp4')
    return mp4_file

def extract_audio(input_path: Path, audio_path: Path, sample_rate: int = 44100) -> bool:
    """
    Извлекает аудио в WAV (unsigned 8-bit PCM stereo).
    """
    print(f"Extracting audio to {audio_path} …")
    try:
        (
            ffmpeg
            .input(str(input_path))
            .output(
                str(audio_path),
                vn=None,             # убираем видео
                acodec='pcm_u8',     # u8 PCM
                ac=2,                # stereo
                ar=sample_rate,      # sample rate
                af=f'aresample={sample_rate}',  # фильтр ресэмпл
                format='wav'
            )
            .run(overwrite_output=True, quiet=True)
        )
        return audio_path.exists() and audio_path.stat().st_size > 0
    except ffmpeg.Error as e:
        print("Error extracting audio:", e)
        return False

def extract_frames(input_path: Path, frames_dir: Path, width: int, height: int, fps: int) -> bool:
    """
    Извлекает кадры в оттенках серого BMP.
    """
    print(f"Extracting frames to {frames_dir} …")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in frames_dir.glob("frame*.bmp"):
        f.unlink()
    pattern = str(frames_dir / "frame%07d.bmp")

    try:
        (
            ffmpeg
            .input(str(input_path))
            .filter('fps', fps=fps)
            .filter('scale', width, height)
            .filter('format', 'gray')
            .output(pattern)
            .run(overwrite_output=True, quiet=True)
        )
        return True
    except ffmpeg.Error as e:
        print("Error extracting frames:", e)
        return False

def create_bundle(frames_dir: Path, audio_path: Path, output_path: Path,
                  width: int, height: int, fps: int, sample_rate: int) -> bool:
    """
    Создаёт .bnd, упаковывая чёрно-белые BMP-кадры и звуковые чанки.
    """
    print(f"Creating bundle {output_path} …")
    try:
        audio_data = audio_path.read_bytes()
        audio_pos = 0
        chunk_size = round(sample_rate / fps)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('wb') as bnd:
            bnd.write(b'BND!VID')                   # сигнатура
            bnd.write(struct.pack('<B', 1))         # версия

            frames = sorted(frames_dir.glob("frame*.bmp"))
            n_frames = len(frames)
            bnd.write(struct.pack('<I', n_frames))       # кол-во кадров
            bnd.write(struct.pack('<H', chunk_size))     # размер аудио-чанка
            bnd.write(struct.pack('<H', sample_rate))    # sample rate
            bnd.write(struct.pack('<B', height))         # высота
            bnd.write(struct.pack('<B', width))          # ширина

            for idx, fpath in enumerate(frames, 1):
                print(f" Frame {idx}/{n_frames}")
                img = Image.open(fpath).convert('1')
                pix = list(img.getdata())
                data = bytearray()
                for i in range(0, width * height, 8):
                    byte = 0
                    for bit in range(8):
                        if i + bit < len(pix) and pix[i + bit] == 0:
                            byte |= 1 << bit
                    data.append(byte)
                bnd.write(data)

                end = min(audio_pos + chunk_size, len(audio_data))
                bnd.write(audio_data[audio_pos:end])
                audio_pos = end

        return True
    except Exception as e:
        print("Error creating bundle:", e)
        return False

def process_mp4_to_bnd(src: Path, dst: Path, width:int, height:int, fps:int, sample_rate:int) -> bool:
    """
    Полная обработка: mp4 → BMP-кадры + audio → .bnd.
    """
    tmp = Path("temp") / src.stem
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    frames = tmp / "frames"
    audio = tmp / "audio.wav"

    ok1 = extract_frames(src, frames, width, height, fps)
    ok2 = extract_audio(src, audio, sample_rate) if ok1 else False
    ok3 = create_bundle(frames, audio, dst, width, height, fps, sample_rate) if (ok1 and ok2) else False

    shutil.rmtree(tmp)
    return ok1 and ok2 and ok3

def main():
    parser = argparse.ArgumentParser(description="Media-tool на yt_dlp + ffmpeg-python + .bnd упаковка")
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument('--download', metavar='URL',
                       help='Скачать через yt_dlp и сразу в .bnd')
    group.add_argument('--extract-audio-only', type=Path,
                       help='Локальный MP4 → WAV (u8 stereo)')
    group.add_argument('--mp4-to-bnd-only', type=Path,
                       help='Локальный MP4 → .bnd')

    parser.add_argument('--output-dir', type=Path, default=Path("output"),
                        help='Папка для результатов (по умолчанию ./output)')
    parser.add_argument('--width',  type=int,   default=128, help='Ширина (макс 128)')
    parser.add_argument('--height', type=int,   default=64,  help='Высота (макс 64)')
    parser.add_argument('--fps',    type=int,   default=24,  help='FPS для кадров')
    parser.add_argument('--sample-rate', type=int, default=44100,
                        help='Частота дискретизации аудио')
    parser.add_argument('--vertical', action='store_true',
                        help='Пересобрать видео в вертикальный режим после скачивания')

    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1) yt_dlp → .bnd
    if args.download:
        url = args.download
        print("Downloading via yt_dlp:", url)
        mp4 = download_youtube_video(url, args.output_dir, args.vertical)
        print("Saved MP4 to", mp4)

        bnd = args.output_dir / f"{mp4.stem}.bnd"
        if process_mp4_to_bnd(mp4, bnd,
                              args.width, args.height,
                              args.fps, args.sample_rate):
            print("✅ BND created:", bnd)
        else:
            print("❌ Failed to create BND")

    # 2) Только аудио → WAV
    elif args.extract_audio_only:
        src = args.extract_audio_only
        if not src.exists():
            print("File not found:", src); return
        dst = args.output_dir / f"{src.stem}.wav"
        if extract_audio(src, dst, args.sample_rate):
            print("✅ WAV created:", dst)
        else:
            print("❌ Audio extraction failed")

    # 3) Только MP4 → BND
    elif args.mp4_to_bnd_only:
        src = args.mp4_to_bnd_only
        if not src.exists():
            print("File not found:", src); return
        dst = args.output_dir / f"{src.stem}.bnd"
        if process_mp4_to_bnd(src, dst,
                              args.width, args.height,
                              args.fps, args.sample_rate):
            print("✅ BND created:", dst)
        else:
            print("❌ Conversion to BND failed")

if __name__ == "__main__":
    main()

