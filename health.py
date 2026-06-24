"""Health API Blueprint — 系统健康检查。"""

import shutil
from flask import Blueprint, jsonify

from db import get_db, get_health_stats

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.route("/health")
def health():
    """GET /api/health — 系统健康检查。

    Returns:
        null_ratio_1h: 最近1小时空值比例 (None = 无数据)
        consecutive_failures: 最近连续失败次数
        disk_usage_pct: 输出目录磁盘使用率
        last_snapshot_age_s: 距上次成功快照的秒数
        status: "ok" | "warning" | "critical"
    """
    conn = get_db()
    stats = get_health_stats(conn, camera_id=1)

    # 磁盘使用率
    try:
        usage = shutil.disk_usage(".")
        disk_pct = round(usage.used / usage.total * 100, 1)
    except Exception:
        disk_pct = None

    # 聚合状态
    status = "ok"
    warnings = []
    if stats["null_ratio_1h"] is not None and stats["null_ratio_1h"] > 0.5:
        status = "critical"
        warnings.append("检测管道可能异常——最近1小时超过半数快照失败")
    if stats["consecutive_failures"] >= 3:
        if status == "ok":
            status = "warning"
        warnings.append(f"连续 {stats['consecutive_failures']} 次快照失败，摄像头可能离线")
    if disk_pct is not None and disk_pct > 80:
        status = "warning"
        warnings.append(f"磁盘使用率 {disk_pct}%，建议清理旧快照")

    return jsonify({
        "status": status,
        "warnings": warnings,
        "null_ratio_1h": stats["null_ratio_1h"],
        "consecutive_failures": stats["consecutive_failures"],
        "disk_usage_pct": disk_pct,
        "last_snapshot_age_s": stats["last_snapshot_age_s"],
        "total_counts": stats["total_counts"],
    })
