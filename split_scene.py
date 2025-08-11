#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector


def format_time(milliseconds):
    """Formats time in milliseconds to HH:MM:SS,mmm."""
    total_seconds = int(milliseconds / 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    ms = int(milliseconds % 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def format_timecode(seconds):
    """Convert seconds (float) to SRT timecode HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def get_fps(path):
    """Get video FPS using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    rate = result.stdout.strip()
    if '/' in rate:
        num, den = rate.split('/')
        try:
            return float(num) / float(den)
        except:
            return 0.0
    try:
        return float(rate)
    except:
        return 0.0


def save_scene_durations(scene_list, output_folder, filename="scene_durations.json"):
    """Save scene durations and timestamps to a JSON file."""
    data = {}
    for i, (start_tc, end_tc) in enumerate(scene_list, start=1):
        start_s = start_tc.get_seconds()
        end_s = end_tc.get_seconds()
        data[i] = {
            "duration": end_s - start_s,
            "timestamp": f"{format_timecode(start_s)} --> {format_timecode(end_s)}"
        }
    os.makedirs(output_folder, exist_ok=True)
    out_path = os.path.join(output_folder, filename)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Scene data saved to {out_path}")


def extract_segment(input_video, start, duration, output_path):
    """Run ffmpeg to extract, copy streams to MP4 and disable subtitles."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", input_video,
        "-t", f"{duration:.3f}",
        "-map", "0:v?",
        "-map", "0:a?",
        "-c", "copy",
        "-sn",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def split_video_in_parallel(input_video, scene_list, output_dir, drop_frames=0, max_workers=8):
    """Split into scenes in parallel, always saving as .mp4 and dropping end frames."""
    os.makedirs(output_dir, exist_ok=True)
    total = len(scene_list)
    width = len(str(total))
    base, _ = os.path.splitext(os.path.basename(input_video))
    ext = ".mp4"

    fps = get_fps(input_video)
    drop_time = drop_frames / fps if fps > 0 else 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        for idx, (start_tc, end_tc) in enumerate(scene_list, start=1):
            start = start_tc.get_seconds()
            orig_dur = end_tc.get_seconds() - start
            dur = max(orig_dur - drop_time, 0.0)
            outname = f"{base}-Scene_{idx:0{width}d}{ext}"
            outpath = os.path.join(output_dir, outname)
            futures.append(pool.submit(extract_segment, input_video, start, dur, outpath))
        for f in as_completed(futures):
            f.result()


def split_video_by_scenes(input_video, output_folder, threshold=15.0, drop_frames=0):
    """Detect scenes and split a single video, optionally dropping end frames."""
    print(f"Processing {input_video}  (threshold={threshold}, drop_frames={drop_frames})")
    start_time = time.time()

    vm = VideoManager([input_video])
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold))
    vm.start()
    sm.detect_scenes(frame_source=vm)
    scene_list = sm.get_scene_list(vm.get_base_timecode())
    vm.release()

    print(f"Detected {len(scene_list)} scenes")
    save_scene_durations(scene_list, output_folder)
    split_video_in_parallel(input_video, scene_list, drop_frames=drop_frames, output_dir=output_folder)

    elapsed_ms = (time.time() - start_time) * 1000
    print(f"Processing time: {format_time(elapsed_ms)}")


if __name__ == "__main__":
    input_video_path = input("Enter your video path need to split: ").strip().replace('"','')
    # Normalize path and expand user tilde
    input_video_path = os.path.expanduser(input_video_path)
    input_video_path = os.path.normpath(input_video_path)

    # Verify file exists before processing
    if not os.path.isfile(input_video_path):
        print(f"Error: video file '{input_video_path}' not found.")
        sys.exit(1)

    drop_frames = 3
    output_directory = input("output folder name: ").strip()

    # If MKV, convert/remux to MP4 without subtitles & re-encode video to H.264
    root, ext = os.path.splitext(input_video_path)
    if ext.lower() == '.mkv':
        converted = f"{root}_converted.mp4"
        print(f"Converting MKV to MP4 (H.264): {converted}")
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video_path,
            "-map", "0:v?",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "copy",
            "-sn",
            converted
        ]
        subprocess.run(cmd, check=True)
        input_video_path = converted

    
    
    split_video_by_scenes(input_video_path, output_directory, threshold=15.0, drop_frames=drop_frames)


#pyinstaller --onefile --name scene_splitter split_scene.py
