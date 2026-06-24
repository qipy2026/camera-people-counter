"""Flask 应用入口 — 定时快照调度 + 仪表盘 + API。

启动: python app.py
环境变量: CAMERA_SOURCE, CAMERA_MODE, SNAPSHOT_INTERVAL_S 等
"""

import time
import sys
import urllib.request
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO
from flask import Flask, render_template, send_file
from apscheduler.schedulers.background import BackgroundScheduler
from cachetools import TTLCache

from config import get_config, SnapshotConfig
from db import get_db, close_db, ensure_camera, insert_count
from startup_check import run_startup_checks
from analytics import analytics_bp
from health import health_bp

# ---- init ----
config = get_config()

# startup validation
print("=" * 50)
print("  摄像头定时快照 + 人数监测系统")
print("=" * 50)
if not run_startup_checks(config):
    close_db()
    sys.exit(1)
print()

# Flask app
app = Flask(__name__)
app.register_blueprint(analytics_bp)
app.register_blueprint(health_bp)

# YOLO model (loaded once at startup)
model = YOLO(config.model_path)

# Dashboard query cache: 5-min TTL
cache = TTLCache(maxsize=32, ttl=config.dashboard_cache_ttl_s)

# Camera ID (ensured in DB)
conn = get_db(config.db_path)
camera_id = ensure_camera(conn, config.camera_name, config.source,
                          config.snapshot_interval_s)

# Seed default schedule (工作日 9/11/14/16) if none exists
from db import seed_default_schedule, get_active_schedule_times
seed_default_schedule(conn, camera_id)

# Consecutive failure counter
failures = {"count": 0}


# ---- snapshot logic ----
def take_snapshot():
    """定时快照：采集帧 → YOLO检测 → 存储 → 缓存失效。"""
    t0 = time.time()
    now = datetime.now(timezone.utc)

    # 1. 采集帧
    frame = _capture_frame()
    if frame is None:
        _record_failure(now)
        return

    # 2. 黑帧检测（红外切换防护）
    mean_brightness = np.mean(frame)
    if mean_brightness < 15:
        print(f"  [{now.strftime('%H:%M:%S')}] ⚠️ 帧过暗 (亮度={mean_brightness:.1f})，"
              f"疑似红外切换，跳过")
        return

    # 3. YOLO 检测
    try:
        results = model(frame, classes=[0], verbose=False)
        boxes = results[0].boxes
        valid_confs = [float(b.conf[0]) for b in boxes
                       if float(b.conf[0]) >= config.confidence_threshold]
        count = len(valid_confs)
        avg_conf = sum(valid_confs) / len(valid_confs) if valid_confs else 0
    except Exception as e:
        print(f"  [{now.strftime('%H:%M:%S')}] ❌ 检测失败: {e}")
        insert_count(conn, camera_id, now.isoformat(), None, "")
        failures["count"] += 1
        return

    # 4. 保存快照
    snap_path = ""
    if config.save_snapshots:
        # 文件名: camera_id + 时间戳(含毫秒) 防碰撞
        snap_name = (f"snap_{config.camera_name}_"
                     f"{now.strftime('%Y%m%d_%H%M%S')}_"
                     f"{now.microsecond // 1000:03d}.jpg")
        snap_path = str(Path(config.output_dir) / snap_name)
        cv2.imwrite(snap_path, frame)

    # 5. 写入 SQLite
    insert_count(conn, camera_id, now.isoformat(), count, snap_path)

    # 6. 缓存失效（新数据到了）
    cache.clear()

    # 7. 输出
    failures["count"] = 0
    conf_str = f", avg conf: {avg_conf:.2f}" if valid_confs else ""
    elapsed_ms = (time.time() - t0) * 1000
    print(f"  [{now.strftime('%H:%M:%S')}] 人数: {count}{conf_str}  "
          f"({elapsed_ms:.0f}ms)")


def _capture_frame():
    """从配置的 source 采集一帧。返回 None 表示失败。"""
    source = config.source
    mode = config.source_mode

    if mode == "http":
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        try:
            urllib.request.urlretrieve(source, tmp.name)
            frame = cv2.imread(tmp.name)
            if frame is None:
                print(f"  ⚠️ HTTP 快照读取失败: {source}")
            return frame
        except Exception as e:
            print(f"  ⚠️ HTTP 快照请求失败: {e}")
            return None
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    else:
        try:
            src = int(source) if source.isdigit() else source
        except ValueError:
            src = source

        cap = cv2.VideoCapture(src)
        if mode == "rtsp":
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10_000)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        ret, frame = cap.read()
        cap.release()

        if not ret:
            print(f"  ⚠️ 视频源读取失败: {source[:60]}...")
            return None
        return frame


def _record_failure(now):
    """记录一次采集/检测失败。"""
    failures["count"] += 1
    insert_count(conn, camera_id, now.isoformat(), None, "")
    msg = f"连续失败 {failures['count']} 次"
    if failures["count"] >= 3:
        msg += " — 摄像头可能离线"
    print(f"  [{now.strftime('%H:%M:%S')}] ⚠️ {msg}")


# ---- routes ----
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/snapshots/<filename>")
def serve_snapshot(filename):
    """Serve snapshot images from output directory."""
    import os
    full_path = os.path.join(os.path.abspath(config.output_dir), filename)
    return send_file(full_path)


# ---- scheduler (CronTrigger, 按时间点) ----
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler(daemon=True)


def _build_jobs():
    """根据数据库中的调度时间点重建所有 cron job。"""
    # 清除现有 snapshot jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("snap_"):
            scheduler.remove_job(job.id)

    times = get_active_schedule_times(conn, camera_id)
    schedule_desc = []
    for t in times:
        hour, minute = t.split(":")
        job_id = f"snap_{t.replace(':', '')}"
        scheduler.add_job(
            take_snapshot,
            CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri"),
            id=job_id,
            replace_existing=True,
        )
        schedule_desc.append(t)

    print(f"调度时间点 ({len(times)}): {', '.join(schedule_desc)}")
    return times


# 初始构建
schedule_times = _build_jobs()
scheduler.start()

# 注册重载钩子（analytics CRUD 后自动触发）
from analytics import set_scheduler_reload
set_scheduler_reload(_build_jobs)

print(f"摄像头: {config.camera_name} ({config.source[:60]}...)")
print(f"仪表盘: http://localhost:{config.flask_port}")
print("Ctrl+C 停止\n")

# ---- graceful shutdown ----
import atexit
@atexit.register
def _cleanup():
    scheduler.shutdown(wait=False)
    close_db()
    print("\n已停止。")


if __name__ == "__main__":
    app.run(host=config.flask_host, port=config.flask_port, debug=False)
