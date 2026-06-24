"""Analytics API Blueprint — 时序查询 + CSV 导出 + 调度管理。"""

import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, Response

from db import (
    get_db, get_latest_count, get_timeseries, count_rows, export_csv_rows,
    get_schedule, add_schedule_time, update_schedule_time, delete_schedule_time,
    get_active_schedule_times,
)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api")

# ---- schedule endpoints ----


@analytics_bp.route("/schedule")
def schedule_list():
    """GET /api/schedule?camera_id=1 — 获取调度时间点列表。"""
    conn = get_db()
    camera_id = request.args.get("camera_id", 1, type=int)
    rows = get_schedule(conn, camera_id)
    return jsonify({"camera_id": camera_id, "schedule": rows})


@analytics_bp.route("/schedule", methods=["POST"])
def schedule_add():
    """POST /api/schedule — 添加时间点。body: {camera_id, time_of_day, day_of_week?}"""
    data = request.get_json(force=True)
    camera_id = data.get("camera_id", 1)
    time_of_day = data["time_of_day"]
    day_of_week = data.get("day_of_week", "")
    conn = get_db()
    sid = add_schedule_time(conn, camera_id, time_of_day, day_of_week)
    _reload_scheduler()
    return jsonify({"id": sid, "time_of_day": time_of_day}), 201


@analytics_bp.route("/schedule/<int:schedule_id>", methods=["PUT"])
def schedule_update(schedule_id):
    """PUT /api/schedule/<id> — 更新时间点。body: {time_of_day?, day_of_week?, enabled?}"""
    data = request.get_json(force=True)
    conn = get_db()
    ok = update_schedule_time(conn, schedule_id, **data)
    if not ok:
        return jsonify({"error": "无可更新的字段"}), 400
    _reload_scheduler()
    return jsonify({"ok": True})


@analytics_bp.route("/schedule/<int:schedule_id>", methods=["DELETE"])
def schedule_delete(schedule_id):
    """DELETE /api/schedule/<id> — 删除时间点。"""
    conn = get_db()
    ok = delete_schedule_time(conn, schedule_id)
    if not ok:
        return jsonify({"error": "时间点不存在"}), 404
    _reload_scheduler()
    return jsonify({"ok": True})


# ---- existing endpoints ----


@analytics_bp.route("/counts/latest")
def counts_latest():
    conn = get_db()
    camera_id = request.args.get("camera_id", 1, type=int)
    row = get_latest_count(conn, camera_id)
    if row is None:
        return jsonify({"camera_id": camera_id, "count": None,
                        "message": "暂无数据"})
    return jsonify({"camera_id": camera_id, **row})


@analytics_bp.route("/counts/timeseries")
def counts_timeseries():
    conn = get_db()
    camera_id = request.args.get("camera_id", 1, type=int)
    from_ts = request.args.get("from")
    to_ts = request.args.get("to")
    bucket = request.args.get("bucket", "1h")
    if bucket not in ("5m", "1h", "1d", "raw"):
        return jsonify({"error": f"不支持的 bucket: {bucket}"}), 400
    # raw = no aggregation, return individual data points (for scatter chart)
    if bucket == "raw":
        rows = export_csv_rows(conn, camera_id, from_ts, to_ts, limit=2000)
        return jsonify({"camera_id": camera_id, "bucket": "raw", "data": rows})
    rows = get_timeseries(conn, camera_id, from_ts, to_ts, bucket)
    return jsonify({"camera_id": camera_id, "bucket": bucket, "data": rows})


@analytics_bp.route("/export/csv")
def export_csv():
    conn = get_db()
    camera_id = request.args.get("camera_id", 1, type=int)
    from_ts = request.args.get("from")
    to_ts = request.args.get("to")
    total = count_rows(conn, camera_id, from_ts, to_ts)
    if total > 100_000:
        return jsonify({
            "error": f"数据量过大 ({total} 行)，请缩小日期范围。单次最多 100,000 行。"
        }), 413
    rows = export_csv_rows(conn, camera_id, from_ts, to_ts)
    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output)
    writer.writerow(["timestamp", "person_count", "snapshot_path"])
    for r in rows:
        writer.writerow([r["timestamp"], r["person_count"], r["snapshot_path"]])
    content = output.getvalue()
    output.close()
    return Response(content, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             f"attachment; filename=counts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"})


# ---- scheduler reload hook ----
_scheduler_reload_fn = None


def set_scheduler_reload(fn):
    """由 app.py 注册，供 schedule CRUD 后触发调度器重载。"""
    global _scheduler_reload_fn
    _scheduler_reload_fn = fn


def _reload_scheduler():
    if _scheduler_reload_fn:
        _scheduler_reload_fn()
