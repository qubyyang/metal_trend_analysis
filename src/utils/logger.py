"""
日志工具模块
"""
import sys
from loguru import logger
from pathlib import Path


def setup_logger(
    log_file: str = "output/logs/app.log",
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "30 days"
):
    """
    配置日志系统

    Args:
        log_file: 日志文件路径
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 确保日志目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认的处理器
    logger.remove()

    # 添加控制台输出处理器
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )

    # 添加文件输出处理器
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8"
    )

    # 添加错误日志单独文件
    error_log_file = log_path.parent / "error.log"
    logger.add(
        error_log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation=rotation,
        retention=retention,
        encoding="utf-8"
    )

    return logger


def get_logger(name: str = None):
    """
    获取日志记录器

    Args:
        name: 记录器名称

    Returns:
        日志记录器
    """
    if name:
        return logger.bind(name=name)
    return logger
