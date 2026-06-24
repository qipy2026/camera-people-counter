"""数据库模块单元测试 — 自包含 fixtures。"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import (
    get_db, close_db, ensure_camera, insert_count,
    get_latest_count, get_timeseries, export_csv_rows,
    count_rows, get_health_stats,
)


@pytest.fixture
def db_conn():
    """临时 SQLite 数据库连接。"""
    import db as db_module
    db_module._local.connection = None
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db_module.get_db(path)
    yield conn
    conn.close()
    db_module._local.connection = None
    Path(path).unlink(missing_ok=True)


class TestCameraOps:
    def test_ensure_camera_creates(self, db_conn):
        cid = ensure_camera(db_conn, "cam1", "rtsp://x", 300)
        assert cid == 1
        row = db_conn.execute(
            "SELECT * FROM cameras WHERE id=?", (cid,)).fetchone()
        assert row["name"] == "cam1"

    def test_ensure_camera_updates_existing(self, db_conn):
        cid1 = ensure_camera(db_conn, "cam1", "rtsp://a", 300)
        cid2 = ensure_camera(db_conn, "cam1-v2", "rtsp://a", 600)
        assert cid1 == cid2


class TestCountOps:
    def test_insert_and_latest(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        insert_count(db_conn, cid, "2026-06-24T10:00:00+08:00", 3, "/t.jpg")
        latest = get_latest_count(db_conn, cid)
        assert latest["person_count"] == 3

    def test_latest_skips_nulls(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        insert_count(db_conn, cid, "2026-06-24T10:00:00+08:00", None, "")
        insert_count(db_conn, cid, "2026-06-24T10:05:00+08:00", 5, "/t.jpg")
        assert get_latest_count(db_conn, cid)["person_count"] == 5

    def test_latest_none_when_empty(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        assert get_latest_count(db_conn, cid) is None


class TestTimeseries:
    def test_aggregation(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        insert_count(db_conn, cid, "2026-06-24T10:00:00+08:00", 3, "")
        insert_count(db_conn, cid, "2026-06-24T10:05:00+08:00", 5, "")
        insert_count(db_conn, cid, "2026-06-24T11:00:00+08:00", 7, "")
        rows = get_timeseries(db_conn, cid, bucket="1h")
        assert len(rows) == 2
        assert rows[0]["avg_count"] == 4.0

    def test_empty_range(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        rows = get_timeseries(db_conn, cid,
                              from_ts="2099-01-01", to_ts="2099-01-02")
        assert rows == []


class TestCSVExport:
    def test_export_and_count(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        for i in range(5):
            insert_count(db_conn, cid,
                         f"2026-06-24T1{i}:00:00+08:00", i, f"/t{i}.jpg")
        assert count_rows(db_conn, cid) == 5
        assert len(export_csv_rows(db_conn, cid)) == 5


class TestHealthStats:
    def test_basic(self, db_conn):
        cid = ensure_camera(db_conn, "c1", "rtsp://x", 300)
        insert_count(db_conn, cid, "2026-06-24T10:00:00+08:00", 3, "")
        insert_count(db_conn, cid, "2026-06-24T10:05:00+08:00", None, "")
        stats = get_health_stats(db_conn, cid)
        assert stats["total_counts"] == 2
