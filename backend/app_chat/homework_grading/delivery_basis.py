"""评分绑定实际报告及图片内容，不以卡标证明教学判断准确。"""
import hashlib
from pathlib import Path


def delivery_basis(paths, manifest):
    base = Path(paths['base'])
    files = list((base / 'pass2_report').glob('*_report.json'))
    files += list((base / 'annotated').glob('*.png'))
    return {'run_id': manifest.get('run_id', ''), 'files': {
        p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files) if p.is_file()}}
