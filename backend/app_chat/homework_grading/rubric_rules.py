"""Rule constants for homework grading source locks."""
from __future__ import annotations

import re

LISTENING_PATTERN = re.compile(
    r'\bListen(?:ing)?\b|听\s*(?:力|录音|短文|对话|一听|一听录音|材料)|录音',
    re.IGNORECASE,
)

SOURCE_PRESENT_PATTERN = re.compile(
    r'听力原文|录音原文|听力材料|录音材料|听力文本|原文如下|Transcript|Tapescript|audio\s+transcript',
    re.IGNORECASE,
)

SOURCE_MISSING_PATTERN = re.compile(
    r'(?:缺少|没有|无|未提供|无法看到|不在图像中|不可见|missing|without|not\s+provided)'
    r'.{0,16}(?:音频|录音|听力原文|原文|听力材料|transcript|audio)'
    r'|(?:音频|录音|听力原文|原文|听力材料|transcript|audio).{0,16}'
    r'(?:缺失|缺少|没有|无|未提供|不可见|missing|not\s+provided)',
    re.IGNORECASE,
)

