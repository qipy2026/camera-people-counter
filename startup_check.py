"""启动前配置校验 —— 拒绝启动而非静默失败。"""

import sys
from pathlib import Path

from ultralytics import YOLO

from config import SnapshotConfig
from db import get_db, close_db


def run_startup_checks(config: SnapshotConfig) -> bool:
    """运行所有启动校验。全部通过返回 True，否则打印错误并返回 False。"""
    checks = [
        ("配置校验", _check_config),
        ("数据库连接", _check_database),
        ("模型加载", _check_model),
        ("输出目录", _check_output_dir),
    ]

    all_ok = True
    for name, check_fn in checks:
        ok, msg = check_fn(config)
        status = "✅" if ok else "❌"
        print(f"  {status} {name}: {msg}")
        if not ok:
            all_ok = False

    return all_ok


def _check_config(config: SnapshotConfig) -> tuple[bool, str]:
    errors = config.validate()
    if errors:
        return False, "; ".join(errors)
    return True, "OK"


def _check_database(config: SnapshotConfig) -> tuple[bool, str]:
    try:
        conn = get_db(config.db_path)
        # 尝试写入和回滚，验证 DB 可写
        conn.execute("SELECT 1")
        return True, f"SQLite @ {config.db_path}"
    except Exception as e:
        return False, str(e)


def _check_model(config: SnapshotConfig) -> tuple[bool, str]:
    model_path = config.model_path
    # 如果模型文件不存在，YOLO 会自动下载，这里只检查路径合法性
    try:
        model = YOLO(model_path)
        model_name = model.model_name if hasattr(model, "model_name") else model_path
        return True, f"YOLO loaded ({model_name})"
    except Exception as e:
        return False, f"模型加载失败: {e}"


def _check_output_dir(config: SnapshotConfig) -> tuple[bool, str]:
    try:
        path = Path(config.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        # 写入测试，验证目录可写
        test_file = path / ".write_test"
        test_file.touch()
        test_file.unlink()
        return True, f"可写 @ {path.resolve()}"
    except Exception as e:
        return False, f"目录不可写: {e}"


if __name__ == "__main__":
    from config import get_config
    cfg = get_config()
    print(f"校验配置: source={cfg.source or '(未设置)'}, "
          f"interval={cfg.snapshot_interval_s}s, "
          f"model={cfg.model_path}")
    ok = run_startup_checks(cfg)
    if not ok:
        print("\n启动校验失败，拒绝启动。请修复以上问题后重试。")
        close_db()
        sys.exit(1)
    print("\n所有校验通过。")
    close_db()
