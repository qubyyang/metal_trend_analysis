#!/usr/bin/env python3
"""
重复定义静态检查

背景：项目曾出现同一个类中方法被定义两次的问题（后定义者静默覆盖前者），
导致实际运行的是低质量实现，且难以在代码评审中发现。本脚本在 CI 中阻断此类回归。

用法：
    python scripts/check_duplicates.py [目录...]

退出码：
    0 无重复定义
    1 检测到重复定义
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

DEFAULT_TARGETS = ["src", "scripts"]
FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def find_duplicates(path: Path) -> List[Tuple[str, str, int]]:
    """返回 [(作用域, 名称, 次数)] 形式的重复定义列表"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"::error file={path}::语法错误: {e}")
        return [("<syntax>", str(e), 1)]

    findings = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.Module)):
            continue

        scope = getattr(node, "name", "<module>")

        counts = Counter(
            child.name for child in node.body if isinstance(child, FUNC_NODES)
        )
        findings.extend(
            (scope, name, count) for name, count in counts.items() if count > 1
        )

        # 类属性重复赋值不检查，误报率过高

    return findings


def main(argv: List[str]) -> int:
    targets = argv[1:] or DEFAULT_TARGETS
    total = 0

    for target in targets:
        root = Path(target)
        if not root.exists():
            continue

        files = sorted(root.rglob("*.py")) if root.is_dir() else [root]

        for file in files:
            for scope, name, count in find_duplicates(file):
                total += 1
                print(
                    f"::error file={file}::重复定义 {scope}.{name} "
                    f"出现 {count} 次（后者会静默覆盖前者）"
                )

    if total:
        print(f"\n检测到 {total} 处重复定义，请合并或删除冗余实现。")
        return 1

    print("未检测到重复定义。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
