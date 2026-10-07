#!/usr/bin/env python3
"""Sample a local video for visual analysis. Requires ffmpeg and ffprobe."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--count', type=int, default=8)
    group.add_argument('--times', help='Comma-separated seconds, e.g. 0.5,2,4.5')
    args = parser.parse_args()
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            parser.error(f'{tool} がありません。スクリーンショット入力に切り替えてください。')
    if not args.video.is_file():
        parser.error('入力動画が見つかりません。')
    if not 1 <= args.count <= 60:
        parser.error('--count は 1〜60 にしてください。')
    if args.output.exists():
        parser.error('上書き防止のため、新しい出力フォルダを指定してください。')
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json',
         str(args.video.resolve())], check=True, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    videos = [s for s in metadata.get('streams', [])
              if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        parser.error('映像ストリームがありません。')
    stream = videos[0]
    duration = float(stream.get('duration') or metadata.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        parser.error('動画の長さを取得できません。')
    if args.times:
        try:
            times = sorted(set(float(t.strip()) for t in args.times.split(',')))
        except ValueError:
            parser.error('--times はカンマ区切りの秒数にしてください。')
        if not 1 <= len(times) <= 60 or any(not math.isfinite(t) or t < 0 or t >= duration for t in times):
            parser.error('時刻は0秒以上・動画の長さ未満で、最大60個にしてください。')
    else:
        times = [duration * (i + 0.5) / args.count for i in range(args.count)]
    args.output.mkdir(parents=True)
    records = []
    for index, seconds in enumerate(times, 1):
        filename = f'frame-{index:03d}-{seconds:.3f}s.jpg'
        target = args.output / filename
        seek_times = [seconds]
        if seconds > duration - 0.5:
            seek_times += [max(0, seconds - 0.1), max(0, seconds - 0.5)]
        for seek_seconds in dict.fromkeys(seek_times):
            if target.exists():
                target.unlink()
            result = subprocess.run(
                ['ffmpeg', '-nostdin', '-v', 'error', '-n', '-ss', str(seek_seconds),
                 '-i', str(args.video.resolve()), '-map', f'0:{stream["index"]}',
                 '-frames:v', '1', '-vf', 'scale=1280:1280:force_original_aspect_ratio=decrease',
                 '-q:v', '2', str(target.resolve())], capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and target.is_file() and target.stat().st_size:
                break
        else:
            raise RuntimeError(f'{seconds:.3f}秒の画像を抽出できませんでした。別の時刻を指定してください。')
        records.append({'file': filename, 'requested_seconds': round(seconds, 6),
                        'seek_seconds': round(seek_seconds, 6),
                        'near_end_fallback': seek_seconds != seconds})
    manifest = {'duration_seconds': duration, 'sampling': 'requested seek times; not shot boundaries',
                'audio_analyzed': False, 'frames': records}
    (args.output / 'frames.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(records)}枚を保存しました: {args.output.resolve()}')
    print('画像を実際に開いて分析してください。動き・音声・全カットの確認は完了していません。')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError, ValueError, OSError) as exc:
        print(f'抽出に失敗しました: {exc}', file=sys.stderr)
        sys.exit(1)
