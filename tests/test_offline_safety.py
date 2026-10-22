# -*- coding: utf-8 -*-
"""离线安全测试：bitcoin_pow/ 与 cuda/ 不含任何网络调用路径。"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 网络客户端关键字（word 边界匹配，排除注释中的说明文字）
NETWORK_PATTERNS = [
    r"\bsocket\b",
    r"\burllib\b",
    r"\brequests\b",
    r"\bhttpx\b",
    r"\bhttp\.client\b",
    r"\bstratum\b",
    r"\bgrpc\b",
    r"\bcurl_\w+",
    r"\bconnect\(",
    r"https?://",   # URL 字面量
]

SCAN_DIRS = ["bitcoin_pow", "cuda"]


class TestOfflineSafety(unittest.TestCase):
    def test_no_network_code_paths(self):
        violations = []
        for d in SCAN_DIRS:
            base = REPO / d
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.suffix not in (".py", ".cu", ".cuh", ".h", ".hpp", ".cpp"):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for line_no, line in enumerate(text.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue  # 纯注释行中的说明文字不算代码路径
                    for pat in NETWORK_PATTERNS:
                        if re.search(pat, line):
                            violations.append("%s:%d %s" % (path, line_no, pat))
        self.assertEqual(violations, [], "发现疑似网络调用:\n" + "\n".join(violations))

    def test_no_private_key_terms(self):
        """核心代码不出现钱包/私钥处理痕迹。"""
        bad = ["wallet.dat", "private_key", "WIF", "seed_phrase"]
        for d in SCAN_DIRS:
            base = REPO / d
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="replace").lower()
                for term in bad:
                    self.assertNotIn(term.lower(), text,
                                     "%s 出现敏感术语 %s" % (path, term))

    def test_legacy_simulator_untouched(self):
        """原收益模拟器文件仍存在且可导入。"""
        import simulator  # noqa: F401
        self.assertTrue((REPO / "simulator.py").exists())
        self.assertTrue((REPO / "test_simulator.py").exists())


if __name__ == "__main__":
    unittest.main()
