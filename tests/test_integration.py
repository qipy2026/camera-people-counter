"""集成测试 — 端到端管道：采集 → 检测 → 存储 → 查询 → 导出。

使用测试视频 /tmp/people-detection.mp4（需提前下载）。"""

import os
import sys
import tempfile
import io
import csv
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def integration_env():
    """设置集成测试环境：临时 DB + 测试视频。"""
    import db as db_module
    db_module._local.connection = None

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    out_dir = tempfile.mkdtemp()

    # 使用测试视频（如果存在）
    test_video = "/tmp/people-detection.mp4"
    if not Path(test_video).exists():
        pytest.skip(f"测试视频不存在: {test_video}，请先下载")

    os.environ["CAMERA_SOURCE"] = test_video
    os.environ["CAMERA_MODE"] = "video"
    os.environ["SNAPSHOT_INTERVAL_S"] = "2"
    os.environ["OUTPUT_DIR"] = out_dir
    os.environ["CONFIDENCE_THRESHOLD"] = "0.3"  # 宽松阈值确保检出

    # 重载 config + db
    import config
    config._config = None
    cfg = config.get_config()
    cfg.db_path = db_path

    conn = db_module.get_db(db_path)

    yield {"config": cfg, "db_conn": conn, "output_dir": out_dir}

    conn.close()
    db_module._local.connection = None
    Path(db_path).unlink(missing_ok=True)


class TestEndToEnd:
    def test_full_pipeline_with_test_video(self, integration_env):
        """端到端：测试视频 → YOLO → SQLite → API查询 → CSV导出。

        这个测试跑实际 YOLO 推理——会加载模型并处理多帧。"""
        from ultralytics import YOLO
        import cv2
        from db import (
            get_latest_count, get_timeseries, export_csv_rows, count_rows,
            ensure_camera, insert_count, get_health_stats,
        )
        from config import get_config

        cfg = get_config()
        conn = integration_env["db_conn"]

        # 1. 确保摄像头存在
        cid = ensure_camera(conn, "test_cam", cfg.source, cfg.snapshot_interval_s)

        # 2. 加载模型
        model = YOLO(cfg.model_path)

        # 3. 模拟定时快照：从视频采集3帧
        cap = cv2.VideoCapture(cfg.source)
        sample_count = 0
        frame_idx = 0

        while sample_count < 3:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

            # 每10帧采样一次（模拟快照间隔）
            if frame_idx % 10 != 0:
                continue

            ts = f"2026-06-24T12:{sample_count:02d}:00+08:00"
            results = model(frame, classes=[0], verbose=False)
            boxes = results[0].boxes
            count = len([b for b in boxes
                        if float(b.conf[0]) >= cfg.confidence_threshold])

            # 保存快照
            snap_name = (f"snap_test_cam_20260624_120{sample_count}_"
                        f"{sample_count:03d}.jpg")
            snap_path = str(Path(cfg.output_dir) / snap_name)
            cv2.imwrite(snap_path, frame)

            insert_count(conn, cid, ts, count, snap_path)
            sample_count += 1

        cap.release()

        assert sample_count >= 1, "至少应采集到一帧"

        # 4. 验证数据存储
        latest = get_latest_count(conn, cid)
        assert latest is not None
        assert isinstance(latest["person_count"], int)

        # 5. 验证时序查询
        rows = get_timeseries(conn, cid, bucket="1h")
        assert len(rows) >= 1
        assert "avg_count" in rows[0]

        # 6. 验证计数
        total = count_rows(conn, cid)
        assert total == sample_count

        # 7. 验证 CSV 导出
        export_rows = export_csv_rows(conn, cid)
        assert len(export_rows) == sample_count
        for r in export_rows:
            assert "timestamp" in r
            assert "person_count" in r

        # 8. 验证健康统计
        stats = get_health_stats(conn, cid)
        assert stats["total_counts"] == sample_count
        assert stats["last_snapshot_age_s"] is not None

        print(f"\n✅ E2E pipeline: {sample_count} snapshots processed")
        print(f"   Latest count: {latest['person_count']}")
        print(f"   Timeseries rows: {len(rows)}")
        print(f"   CSV rows: {len(export_rows)}")
