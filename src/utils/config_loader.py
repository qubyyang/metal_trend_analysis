"""
配置文件加载模块
"""
import os
import yaml
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_dir: str = "config"):
        """
        初始化配置加载器

        Args:
            config_dir: 配置文件目录
        """
        # 加载 .env 文件
        load_dotenv()
        
        self.config_dir = Path(config_dir)
        self.config = {}

    def load_main_config(self, config_file: str = "config.yaml") -> Dict[str, Any]:
        """
        加载主配置文件

        Args:
            config_file: 配置文件名

        Returns:
            配置字典
        """
        config_path = self.config_dir / config_file

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 替换环境变量
        config = self._replace_env_vars(config)

        self.config = config
        return config

    def load_yaml(self, yaml_file: str) -> Dict[str, Any]:
        """
        加载任意 YAML 文件

        Args:
            yaml_file: YAML 文件名

        Returns:
            配置字典
        """
        yaml_path = self.config_dir / yaml_file

        if not yaml_path.exists():
            raise FileNotFoundError(f"YAML 文件不存在: {yaml_path}")

        with open(yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def load_text(self, text_file: str) -> list:
        """
        加载文本文件

        Args:
            text_file: 文本文件名

        Returns:
            文本行列表
        """
        text_path = self.config_dir / text_file

        if not text_path.exists():
            raise FileNotFoundError(f"文本文件不存在: {text_path}")

        with open(text_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        return lines

    def _replace_env_vars(self, config: Any) -> Any:
        """
        递归替换配置中的环境变量

        Args:
            config: 配置对象

        Returns:
            替换后的配置
        """
        if isinstance(config, dict):
            return {k: self._replace_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replace_env_vars(item) for item in config]
        elif isinstance(config, str):
            # 匹配 ${VAR_NAME} 格式
            import re
            match = re.match(r'\$\{([^}]+)\}', config)
            if match:
                var_name = match.group(1)
                return os.getenv(var_name, config)
            return config
        else:
            return config

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项

        Args:
            key: 配置键（支持点号分隔，如 'api.itick.token'）
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def save_config(self, config_file: str = "config.yaml"):
        """
        保存配置到文件

        Args:
            config_file: 配置文件名
        """
        config_path = self.config_dir / config_file

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
