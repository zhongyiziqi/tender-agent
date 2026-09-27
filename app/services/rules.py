from __future__ import annotations

import re
from typing import Any


PATTERNS = [
    (r"指定品牌|仅限品牌|唯一品牌", "歧视性条款", "high", "避免指定或变相指定品牌"),
    (r"唯一供应商|仅限.*供应商", "歧视性条款", "high", "改为可验证的功能或服务要求"),
    (r"必须具有.*本地|注册地.*本地", "资质门槛", "high", "删除不必要的地域限制"),
    (r"独家授权|原厂授权", "资质门槛", "medium", "说明授权要求的必要性或采用等效证明"),
    (r"专利号|特定专利", "技术参数", "high", "改写为必要的性能或功能指标"),
]


def scan_compliance(text: str, vendor_coverage_count: int | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pattern, category, severity, suggestion in PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 80)
            findings.append(
                {
                    "category": category,
                    "severity": severity,
                    "location": f"字符 {match.start()}-{match.end()}",
                    "original_text": text[start:end],
                    "rule_id": f"RULE-{len(findings) + 1:03d}",
                    "explanation": "条款可能形成不合理限制，需要结合采购必要性复核。",
                    "suggestion": suggestion,
                }
            )
    if vendor_coverage_count is None or vendor_coverage_count < 3:
        findings.append(
            {
                "category": "厂商覆盖性",
                "severity": "high",
                "location": "整体文件",
                "original_text": "未提供至少三家可满足厂商或产品的充分佐证",
                "rule_id": "COVERAGE-003",
                "explanation": "核心要求原则上应由至少三家厂商或产品实质性满足。",
                "suggestion": "补充市场调研佐证，或调整排他参数并提交人工说明。",
            }
        )
    return findings

