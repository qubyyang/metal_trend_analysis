"""
通知推送模块

支持的渠道：
- 飞书 (Feishu/Lark) Webhook
"""

from .feishu import FeishuNotifier

__all__ = ['FeishuNotifier']
