# app_chat/ci/index_manager.py
# Phase 2.1 产物：从 continuous_image_service.py 抽取索引管理类
# 来源映射：continuous_image_service.py L182-300
# 规则：类体与原始定义完全一致，不做任何行为修改

import datetime
import os
import shutil
import threading as _threading_ci
from app_chat.ci.file_io import FileLock, atomic_json
from typing import Any, Dict, List, Optional

from app_chat.ci._utils import (
    _ci_index_path,
    _safe_json_load,
    _safe_json_dump,
    _ci_dmt_root,
)


# ─── 索引文件锁 ───────────────────────────────────────────────────────────────
# from continuous_image_service.py L186

_ci_index_lock = _threading_ci.Lock()


# ─── CIIndexManager ───────────────────────────────────────────────────────────
# from continuous_image_service.py L198-300

class CIIndexManager:
    """管理 continuous_image_dmt/index.json 的线程安全读写。"""

    @staticmethod
    def _load_raw(username: str) -> Dict[str, Any]:
        path = _ci_index_path(username)
        if not os.path.exists(path):
            return {'version': 1, 'analyses': []}
        try:
            data = _safe_json_load(path)
            if not isinstance(data, dict) or not isinstance(data.get('analyses'), list):
                raise ValueError('索引结构无效')
            return data
        except Exception as exc:
            raise ValueError('分析索引损坏，已保留原文件，请先修复索引') from exc

    @staticmethod
    def _save_raw(username: str, data: Dict[str, Any]) -> None:
        path = _ci_index_path(username)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_json(path, data)

    @staticmethod
    def load(username: str) -> List[Dict[str, Any]]:
        with _ci_index_lock, FileLock(_ci_index_path(username) + '.lock', timeout=15):
            return CIIndexManager._load_raw(username).get('analyses', [])

    @staticmethod
    def find_by_id(username: str, analysis_id: str) -> Optional[Dict[str, Any]]:
        for rec in CIIndexManager.load(username):
            if rec.get('analysis_id') == analysis_id:
                return rec
        return None

    @staticmethod
    def find_singles_for_file(username: str, filename: str) -> List[Dict[str, Any]]:
        return [r for r in CIIndexManager.load(username)
                if r.get('mode') == 'single' and filename in r.get('files', [])]

    @staticmethod
    def find_groups_for_files(username: str, files: List[str]) -> List[Dict[str, Any]]:
        file_set = set(files)
        return [r for r in CIIndexManager.load(username)
                if r.get('mode') == 'group' and set(r.get('files', [])) & file_set]

    @staticmethod
    def find_superset_group(username: str, files: List[str]) -> Optional[Dict[str, Any]]:
        """返回 files ⊆ record.files 的最小超集多图组（status=completed only）。"""
        file_set = set(files)
        candidates = [
            r for r in CIIndexManager.load(username)
            if r.get('mode') == 'group'
            and r.get('status') == 'completed'
            and file_set.issubset(set(r.get('files', [])))
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda r: len(r.get('files', [])))

    @staticmethod
    def add_or_update(username: str, record: Dict[str, Any]) -> None:
        with _ci_index_lock, FileLock(_ci_index_path(username) + '.lock', timeout=15):
            data = CIIndexManager._load_raw(username)
            analyses = data.get('analyses', [])
            new_analyses = [a for a in analyses if a.get('analysis_id') != record['analysis_id']]
            new_analyses.append(record)
            data['analyses'] = new_analyses
            CIIndexManager._save_raw(username, data)

    @staticmethod
    def update_status(username: str, analysis_id: str, status: str) -> None:
        with _ci_index_lock, FileLock(_ci_index_path(username) + '.lock', timeout=15):
            data = CIIndexManager._load_raw(username)
            for rec in data.get('analyses', []):
                if rec.get('analysis_id') == analysis_id:
                    rec['status'] = status
                    rec['updated_at'] = datetime.datetime.now().isoformat()
                    break
            CIIndexManager._save_raw(username, data)

    @staticmethod
    def restore_record(username: str, analysis_id: str, record) -> None:
        """仅恢复启动事务涉及的一条记录，保留并发更新的其他文档。"""
        if record is not None and record.get('analysis_id') != analysis_id:
            raise ValueError('索引恢复身份不一致')
        with _ci_index_lock, FileLock(_ci_index_path(username) + '.lock', timeout=15):
            data = CIIndexManager._load_raw(username)
            data['analyses'] = [item for item in data['analyses'] if item.get('analysis_id') != analysis_id]
            if record is not None:
                data['analyses'].append(record)
            CIIndexManager._save_raw(username, data)

    @staticmethod
    def remove_subset_groups(username: str, new_files: List[str]) -> None:
        """多图完成后移除所有文件集合是 new_files 严格子集的旧多图记录（并删除目录）。"""
        new_set = set(new_files)
        with _ci_index_lock, FileLock(_ci_index_path(username) + '.lock', timeout=15):
            data = CIIndexManager._load_raw(username)
            to_remove = []
            to_keep = []
            for rec in data.get('analyses', []):
                if rec.get('mode') == 'group':
                    rec_set = set(rec.get('files', []))
                    if rec_set and rec_set < new_set:
                        to_remove.append(rec)
                    else:
                        to_keep.append(rec)
                else:
                    to_keep.append(rec)
            data['analyses'] = to_keep
            CIIndexManager._save_raw(username, data)

        dmt_root = _ci_dmt_root(username)
        for rec in to_remove:
            folder = os.path.join(dmt_root, rec.get('analysis_id', ''))
            if os.path.isdir(folder):
                shutil.rmtree(folder, ignore_errors=True)
