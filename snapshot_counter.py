#!/usr/bin/env python3
"""
摄像头定时快照 + YOLO 人数检测
支持 RTSP/RTMP/HTTP 快照 URL / USB 摄像头 / 本地视频文件

用法:
    python snapshot_counter.py --source "rtsp://admin:password@192.168.1.100:554/stream"
    python snapshot_counter.py --source "http://192.168.1.100/snapshot.jpg" --mode http
    python snapshot_counter.py --source 0 --mode webcam
    python snapshot_counter.py --source video.mp4 --mode video --interval 5
"""

import argparse, csv, time, urllib.request, tempfile
from datetime import datetime, timezone
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO


def parse_args():
    p = argparse.ArgumentParser(description="摄像头定时快照 + YOLO 人数检测")
    p.add_argument("--source", "-s", required=True, help="视频源 URL/路径/摄像头索引")
    p.add_argument("--mode", "-m", choices=["rtsp", "http", "webcam", "video"], default="rtsp")
    p.add_argument("--interval", "-i", type=int, default=300, help="快照间隔(秒), 默认300=5分钟")
    p.add_argument("--model", default="yolo11n.pt", help="YOLO 模型")
    p.add_argument("--output", "-o", default="./snapshot_data", help="输出目录")
    p.add_argument("--confidence", "-c", type=float, default=0.5, help="置信度阈值")
    p.add_argument("--no-save-snapshots", action="store_true", help="不保存快照图片")
    return p.parse_args()


def count_people(model, frame, conf_threshold):
    results = model(frame, classes=[0], verbose=False)
    boxes = results[0].boxes
    valid = [(float(b.conf[0]), b) for b in boxes if float(b.conf[0]) >= conf_threshold]
    return len(valid), [v[1] for v in valid], [v[0] for v in valid]


def main():
    args = parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"加载模型: {args.model}")
    model = YOLO(args.model)

    # 确定 source 类型
    if args.source.isdigit():
        source = int(args.source)
        is_live = True
    elif args.source.startswith("rtsp://") or args.source.startswith("rtmp://"):
        source = args.source
        is_live = True
    elif args.source.startswith("http"):
        source = args.source
        is_live = True
    else:
        source = args.source
        is_live = False

    # CSV
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"counts_{ts}.csv"
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "camera_id", "person_count", "snapshot_path"])

        print(f"快照间隔: {args.interval}s ({args.interval/60:.1f}min)")
        print(f"输出: {csv_path}")
        print("Ctrl+C 停止\n")

        cap = None if args.source.startswith("http") else cv2.VideoCapture(source)
        count = 0

        try:
            while True:
                t0 = time.time()
                now = datetime.now(timezone.utc)
                count += 1

                # 获取帧
                if args.source.startswith("http"):
                    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    try:
                        urllib.request.urlretrieve(source, tmp.name)
                        frame = cv2.imread(tmp.name)
                    finally:
                        Path(tmp.name).unlink(missing_ok=True)
                else:
                    ret, frame = cap.read()
                    if not ret:
                        print(f"  [{now.isoformat()}] ⚠️ 读取失败")
                        elapsed = time.time() - t0
                        if elapsed < args.interval:
                            time.sleep(args.interval - elapsed)
                        continue

                # 检测
                n, _, confs = count_people(model, frame, args.confidence)
                avg = sum(confs)/len(confs) if confs else 0

                # 保存快照
                snap = ""
                if not args.no_save_snapshots:
                    # camera_id + 时间戳(含毫秒) 防碰撞
                    snap = str(output_dir / (
                        f"snap_camera1_"
                        f"{now.strftime('%Y%m%d_%H%M%S')}_"
                        f"{now.microsecond // 1000:03d}.jpg"
                    ))
                    cv2.imwrite(snap, frame)

                writer.writerow([now.isoformat(), "camera_1", n, snap])
                f.flush()
                cstr = f", avg conf: {avg:.2f}" if confs else ""
                print(f"  [{now.strftime('%H:%M:%S')}] #{count} | 人数: {n}{cstr}")

                elapsed = time.time() - t0
                if elapsed < args.interval:
                    time.sleep(args.interval - elapsed)

        except KeyboardInterrupt:
            print(f"\n停止。共 {count} 个快照 → {csv_path}")

    if cap:
        cap.release()


if __name__ == "__main__":
    main()
