"""快照系统配置管理 — 环境变量 + .env + 命令行参数。"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SnapshotConfig:
    """快照系统配置。

    优先级: CLI 参数 > 环境变量 > 默认值
    """

    # 摄像头
    source: str = ""                    # RTSP/HTTP URL 或摄像头索引
    source_mode: str = "rtsp"           # rtsp | http | webcam | video
    camera_name: str = "camera_1"

    # 快照
    snapshot_interval_s: int = 300      # 默认 5 分钟
    min_interval_s: int = 60            # CPU 模式最小间隔

    # 检测
    model_path: str = "yolo11n.pt"
    confidence_threshold: float = 0.5

    # 存储
    output_dir: str = "./snapshot_data"
    db_path: str = "./snapshot_data/counts.db"
    save_snapshots: bool = True
    snapshot_retention_days: int = 30

    # 仪表盘
    flask_host: str = "0.0.0.0"
    flask_port: int = 5000
    dashboard_cache_ttl_s: int = 300    # 5 分钟

    # 导出限制
    csv_max_rows: int = 100_000

    @classmethod
    def from_env(cls, **overrides) -> "SnapshotConfig":
        """从环境变量加载配置，overrides 为 CLI 最高优先级覆盖。"""
        c = cls()

        # 摄像头
        c.source = overrides.get("source") or os.getenv("CAMERA_SOURCE", "")
        c.source_mode = overrides.get("source_mode") or os.getenv(
            "CAMERA_MODE", "rtsp")
        c.camera_name = overrides.get("camera_name") or os.getenv(
            "CAMERA_NAME", "camera_1")

        # 快照间隔
        _interval = overrides.get("snapshot_interval_s")
        if _interval is None:
            _interval = int(os.getenv("SNAPSHOT_INTERVAL_S", "300"))
        c.snapshot_interval_s = max(_interval, c.min_interval_s)

        # 检测
        c.model_path = overrides.get("model_path") or os.getenv(
            "YOLO_MODEL", "yolo11n.pt")
        c.confidence_threshold = float(
            overrides.get("confidence_threshold")
            or os.getenv("CONFIDENCE_THRESHOLD", "0.5")
        )

        # 存储
        c.output_dir = overrides.get("output_dir") or os.getenv(
            "OUTPUT_DIR", "./snapshot_data")
        c.db_path = str(Path(c.output_dir) / "counts.db")
        c.save_snapshots = not overrides.get("no_save_snapshots", False)

        # Flask
        c.flask_port = int(os.getenv("FLASK_PORT", "5000"))

        return c

    def validate(self) -> list[str]:
        """校验配置合法性，返回错误信息列表。无错误时返回空列表。"""
        errors = []

        if not self.source:
            errors.append("CAMERA_SOURCE 未设置 —— 请提供摄像头 RTSP/HTTP URL 或索引")

        if self.source_mode == "webcam":
            try:
                idx = int(self.source)
                if idx < 0:
                    errors.append(f"摄像头索引不能为负数: {idx}")
            except ValueError:
                errors.append(f"webcam 模式下 source 必须为数字索引，当前: {self.source}")
        elif self.source_mode in ("rtsp", "http"):
            if not (self.source.startswith("rtsp://")
                    or self.source.startswith("rtmp://")
                    or self.source.startswith("http://")
                    or self.source.startswith("https://")):
                errors.append(
                    f"{self.source_mode} 模式下 source 必须以协议头开始，"
                    f"当前: {self.source[:50]}..."
                )
        elif self.source_mode == "video":
            if not Path(self.source).exists():
                errors.append(f"视频文件不存在: {self.source}")

        if self.snapshot_interval_s < self.min_interval_s:
            errors.append(
                f"快照间隔 ({self.snapshot_interval_s}s) 小于最小值 "
                f"({self.min_interval_s}s)，将被 clamp"
            )

        if not 0.1 <= self.confidence_threshold <= 1.0:
            errors.append(
                f"置信度阈值应在 0.1-1.0 之间，当前: {self.confidence_threshold}"
            )

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0


# 全局单例
_config: SnapshotConfig | None = None


def get_config(**overrides) -> SnapshotConfig:
    """获取全局配置实例（懒加载）。"""
    global _config
    if _config is None or overrides:
        _config = SnapshotConfig.from_env(**overrides)
    return _config
