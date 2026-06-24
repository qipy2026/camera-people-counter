"""SQLite 数据库模块 — 人数计数存储与查询。

每天 ~288 行数据，SQLite 在单机场景下足够使用十年以上。
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

# 线程本地连接，避免多线程竞争
_local = threading.local()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    snapshot_interval_s INTEGER NOT NULL DEFAULT 300,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES cameras(id),
    recorded_at TEXT NOT NULL,          -- ISO 8601 timestamptz
    person_count INTEGER,               -- NULL = detection failed
    snapshot_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_counts_camera_time
    ON counts(camera_id, recorded_at);

CREATE INDEX IF NOT EXISTS idx_counts_recorded_at
    ON counts(recorded_at);

CREATE TABLE IF NOT EXISTS snapshot_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES cameras(id),
    time_of_day TEXT NOT NULL,          -- HH:MM 格式
    day_of_week TEXT DEFAULT '',        -- 空=每天, '1,2,3,4,5'=工作日
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_schedule_camera
    ON snapshot_schedule(camera_id);
"""


def get_db(db_path: str = "snapshot_data/counts.db") -> sqlite3.Connection:
    """获取线程本地的数据库连接（自动创建目录和表）。"""
    conn = getattr(_local, "connection", None)
    if conn is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        _local.connection = conn
    return conn


def close_db():
    """关闭当前线程的数据库连接。"""
    conn = getattr(_local, "connection", None)
    if conn is not None:
        conn.close()
        _local.connection = None


# ---- write operations ----


def ensure_camera(conn: sqlite3.Connection, name: str, source_url: str,
                  interval_s: int = 300) -> int:
    """确保摄像头记录存在，返回 camera_id。已存在则更新配置。"""
    row = conn.execute(
        "SELECT id FROM cameras WHERE source_url = ?", (source_url,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE cameras SET name=?, snapshot_interval_s=? WHERE id=?",
            (name, interval_s, row["id"]),
        )
        conn.commit()
        return row["id"]
    cur = conn.execute(
        "INSERT INTO cameras (name, source_url, snapshot_interval_s) VALUES (?, ?, ?)",
        (name, source_url, interval_s),
    )
    conn.commit()
    return cur.lastrowid


def insert_count(conn: sqlite3.Connection, camera_id: int,
                 recorded_at: str, person_count: int | None,
                 snapshot_path: str = "") -> int:
    """插入一条计数记录，返回记录 ID。person_count 为 None 表示检测失败。"""
    cur = conn.execute(
        "INSERT INTO counts (camera_id, recorded_at, person_count, snapshot_path) "
        "VALUES (?, ?, ?, ?)",
        (camera_id, recorded_at, person_count, snapshot_path),
    )
    conn.commit()
    return cur.lastrowid


# ---- read operations ----


def get_latest_count(conn: sqlite3.Connection,
                     camera_id: int) -> dict | None:
    """获取指定摄像头最近一次成功计数。"""
    row = conn.execute(
        "SELECT recorded_at, person_count, snapshot_path "
        "FROM counts "
        "WHERE camera_id = ? AND person_count IS NOT NULL "
        "ORDER BY recorded_at DESC LIMIT 1",
        (camera_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "recorded_at": row["recorded_at"],
        "person_count": row["person_count"],
        "snapshot_path": row["snapshot_path"],
    }


def get_timeseries(conn: sqlite3.Connection, camera_id: int,
                   from_ts: str | None = None, to_ts: str | None = None,
                   bucket: str = "1h") -> list[dict]:
    """返回时序聚合数据。

    bucket: '5m', '1h', '1d' — SQLite 用 strftime 模拟 time_bucket。
    """
    bucket_fmt = {"5m": "%Y-%m-%dT%H:%M", "1h": "%Y-%m-%dT%H",
                  "1d": "%Y-%m-%d"}

    fmt = bucket_fmt.get(bucket, bucket_fmt["1h"])
    # 截断到 bucket 边界
    trunc_expr = f"strftime('{fmt}', recorded_at)"

    params = [camera_id]
    where = "WHERE camera_id = ? AND person_count IS NOT NULL"
    if from_ts:
        where += " AND recorded_at >= ?"
        params.append(from_ts)
    if to_ts:
        where += " AND recorded_at <= ?"
        params.append(to_ts)

    rows = conn.execute(
        f"SELECT {trunc_expr} AS bucket, "
        f"  ROUND(AVG(person_count), 1) AS avg_count, "
        f"  MIN(person_count) AS min_count, "
        f"  MAX(person_count) AS max_count, "
        f"  COUNT(*) AS sample_count "
        f"FROM counts {where} "
        f"GROUP BY bucket ORDER BY bucket",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def export_csv_rows(conn: sqlite3.Connection, camera_id: int,
                    from_ts: str | None = None, to_ts: str | None = None,
                    limit: int = 100_000) -> list[dict]:
    """返回 CSV 导出的原始行。"""
    params = [camera_id]
    where = "WHERE camera_id = ?"
    if from_ts:
        where += " AND recorded_at >= ?"
        params.append(from_ts)
    if to_ts:
        where += " AND recorded_at <= ?"
        params.append(to_ts)

    rows = conn.execute(
        f"SELECT recorded_at AS timestamp, person_count, snapshot_path "
        f"FROM counts {where} "
        f"ORDER BY recorded_at "
        f"LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


def count_rows(conn: sqlite3.Connection, camera_id: int,
               from_ts: str | None = None, to_ts: str | None = None) -> int:
    """返回符合条件的记录总数（用于判断是否触发 413）。"""
    params = [camera_id]
    where = "WHERE camera_id = ?"
    if from_ts:
        where += " AND recorded_at >= ?"
        params.append(from_ts)
    if to_ts:
        where += " AND recorded_at <= ?"
        params.append(to_ts)
    row = conn.execute(f"SELECT COUNT(*) AS n FROM counts {where}", params).fetchone()
    return row["n"]


# ---- health check queries ----


# ---- schedule CRUD ----


def get_schedule(conn: sqlite3.Connection,
                 camera_id: int) -> list[dict]:
    """返回指定摄像头的所有调度时间点（按时间排序）。"""
    rows = conn.execute(
        "SELECT id, camera_id, time_of_day, day_of_week, enabled "
        "FROM snapshot_schedule WHERE camera_id = ? "
        "ORDER BY time_of_day",
        (camera_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_schedule_time(conn: sqlite3.Connection, camera_id: int,
                      time_of_day: str, day_of_week: str = "",
                      enabled: bool = True) -> int:
    """添加一个调度时间点，返回 id。"""
    cur = conn.execute(
        "INSERT INTO snapshot_schedule (camera_id, time_of_day, day_of_week, enabled) "
        "VALUES (?, ?, ?, ?)",
        (camera_id, time_of_day, day_of_week, int(enabled)),
    )
    conn.commit()
    return cur.lastrowid


def update_schedule_time(conn: sqlite3.Connection, schedule_id: int,
                         **kwargs) -> bool:
    """更新调度时间点。kwargs 可以是 time_of_day, day_of_week, enabled。"""
    allowed = {"time_of_day", "day_of_week", "enabled"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [schedule_id]
    conn.execute(
        f"UPDATE snapshot_schedule SET {set_clause} WHERE id=?",
        values,
    )
    conn.commit()
    return True


def delete_schedule_time(conn: sqlite3.Connection, schedule_id: int) -> bool:
    """删除调度时间点。"""
    cur = conn.execute("DELETE FROM snapshot_schedule WHERE id=?", (schedule_id,))
    conn.commit()
    return cur.rowcount > 0


def seed_default_schedule(conn: sqlite3.Connection, camera_id: int):
    """如果该摄像头还没有调度时间点，插入默认值（工作日 9/11/14/16）。"""
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM snapshot_schedule WHERE camera_id=?",
        (camera_id,),
    ).fetchone()
    if existing["n"] > 0:
        return
    defaults = [
        ("09:00", "1,2,3,4,5"),
        ("11:00", "1,2,3,4,5"),
        ("14:00", "1,2,3,4,5"),
        ("16:00", "1,2,3,4,5"),
    ]
    for time_of_day, day_of_week in defaults:
        add_schedule_time(conn, camera_id, time_of_day, day_of_week)
    conn.commit()


def get_active_schedule_times(conn: sqlite3.Connection,
                              camera_id: int) -> list[str]:
    """返回当前启用的时间点列表（仅时间字符串 HH:MM），供调度器使用。"""
    rows = conn.execute(
        "SELECT time_of_day FROM snapshot_schedule "
        "WHERE camera_id=? AND enabled=1 ORDER BY time_of_day",
        (camera_id,),
    ).fetchall()
    return [r["time_of_day"] for r in rows]


def get_health_stats(conn: sqlite3.Connection,
                     camera_id: int) -> dict:
    """返回健康检查所需的所有统计指标。

    Returns:
        null_ratio_1h: 最近1小时空值比例 (None = 无数据)
        consecutive_failures: 最近连续失败次数
        last_snapshot_age_s: 距上次成功快照的秒数
    """
    now = datetime.now(timezone.utc).isoformat()

    # null ratio (last 1 hour)
    null_row = conn.execute(
        "SELECT "
        "  COUNT(*) AS total, "
        "  SUM(CASE WHEN person_count IS NULL THEN 1 ELSE 0 END) AS nulls "
        "FROM counts "
        "WHERE camera_id = ? AND recorded_at >= datetime('now', '-1 hour')",
        (camera_id,),
    ).fetchone()
    null_ratio = (null_row["nulls"] / null_row["total"]
                  if null_row["total"] > 0 else None)

    # consecutive failures (most recent rows until first success)
    fail_row = conn.execute(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT person_count FROM counts "
        "  WHERE camera_id = ? "
        "  ORDER BY recorded_at DESC"
        ") WHERE person_count IS NULL "
        "  OR person_count = (SELECT person_count FROM counts "
        "    WHERE camera_id = ? ORDER BY recorded_at DESC LIMIT 1)",
        (camera_id, camera_id),
    ).fetchone()
    consecutive = fail_row["n"] if fail_row else 0

    # last snapshot age
    age_row = conn.execute(
        "SELECT (strftime('%s', 'now') - strftime('%s', recorded_at)) AS age_s "
        "FROM counts WHERE camera_id = ? AND person_count IS NOT NULL "
        "ORDER BY recorded_at DESC LIMIT 1",
        (camera_id,),
    ).fetchone()
    last_age_s = age_row["age_s"] if age_row else None

    # total counts (for disk estimation)
    total_row = conn.execute(
        "SELECT COUNT(*) AS n FROM counts WHERE camera_id = ?", (camera_id,)
    ).fetchone()
    total_counts = total_row["n"]

    return {
        "null_ratio_1h": round(null_ratio, 3) if null_ratio is not None else None,
        "consecutive_failures": consecutive,
        "last_snapshot_age_s": last_age_s,
        "total_counts": total_counts,
    }
