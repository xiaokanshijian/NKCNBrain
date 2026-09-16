#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
为已创建的场景添加默认文件
使用方法：
1. 将此脚本放在后端目录（与 manage.py 同级）
   - 本地开发：backend/
   - 应用服务器：djangoProject/
2. 将 PDF 文件放在脚本同目录
3. 在该目录下运行：python add_scene_file.py
"""

import os
import sys
import shutil
from pathlib import Path

# 设置 Django 环境
BASE_DIR = Path(__file__).resolve().parent  # 脚本所在目录

# 检查是否在正确的目录（必须有 manage.py）
if not (BASE_DIR / 'manage.py').exists():
    print("❌ 错误：请在包含 manage.py 的目录下运行此脚本！")
    print(f"   当前目录：{BASE_DIR}")
    print(f"   正确位置：backend/ 或 djangoProject/ 目录")
    sys.exit(1)

sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

import django

django.setup()

# 导入必要的模块
from llm_langchain import parse_input

# ========== 配置区域 ==========
SCENE_NAME = "新10k数据集制备"  # 场景名称
PDF_FILE_NAME = "四色语境·群组设计·真实目标各500字深度理解V3.0.pdf"  # PDF 文件名


# ==============================

def add_file_to_scene(scene_name, pdf_file_name):
    """
    为场景添加文件并进行向量化处理

    Args:
        scene_name: 场景名称
        pdf_file_name: PDF 文件名
    """

    # 1. 检查 PDF 文件是否存在
    pdf_source_path = BASE_DIR / pdf_file_name
    if not pdf_source_path.exists():
        print(f"❌ 错误：找不到 PDF 文件：{pdf_source_path}")
        print(f"   请确保 '{pdf_file_name}' 与脚本在同一目录下（backend/）")
        return False

    # 2. 确定场景目录路径
    scene_dir = BASE_DIR / 'received_dir' / 'scene_excel' / scene_name

    # 检查场景目录是否存在
    if not scene_dir.exists():
        print(f"❌ 错误：场景目录不存在：{scene_dir}")
        print(f"   请确认场景名称是否正确：'{scene_name}'")
        return False

    # 3. 复制 PDF 文件到场景目录
    pdf_dest_path = scene_dir / pdf_file_name

    if pdf_dest_path.exists():
        print(f"⚠️  警告：文件已存在：{pdf_dest_path}")
        choice = input("   是否覆盖？(y/n): ").strip().lower()
        if choice != 'y':
            print("   操作已取消")
            return False

    try:
        print(f"\n📋 步骤 1/2：复制文件...")
        print(f"   源文件：{pdf_source_path}")
        print(f"   目标位置：{pdf_dest_path}")
        shutil.copy2(pdf_source_path, pdf_dest_path)
        print(f"✅ 文件复制成功！")
    except Exception as e:
        print(f"❌ 文件复制失败：{e}")
        return False

    # 4. 向量化处理
    try:
        print(f"\n📋 步骤 2/2：向量化处理...")
        print(f"   场景名称：{scene_name}")
        print(f"   文件名称：{pdf_file_name}")
        print(f"   请稍候，这可能需要几分钟...")

        parse_input.get_split_docs_vectors_scene(
            scene_name=scene_name,
            docs_name=pdf_file_name
        )

        print(f"✅ 向量化处理完成！")
        print(f"\n🎉 成功！文件已添加到场景并完成处理")
        print(f"   场景：{scene_name}")
        print(f"   文件：{pdf_file_name}")
        return True

    except Exception as e:
        print(f"❌ 向量化处理失败：{e}")
        print(f"   文件已复制，但未完成向量化")
        print(f"   可能需要手动触发处理或检查错误日志")
        import traceback
        print(f"\n详细错误信息：")
        print(traceback.format_exc())
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("为场景添加默认文件工具")
    print("=" * 60)
    print(f"\n配置信息：")
    print(f"  场景名称：{SCENE_NAME}")
    print(f"  文件名称：{PDF_FILE_NAME}")

    # 安全提示
    print(f"\n⚠️  安全确认：")
    print(f"  - 文件将添加到：received_dir/scene_excel/{SCENE_NAME}/")
    print(f"  - 仅影响场景：{SCENE_NAME}")
    print(f"  - 不会影响其他场景或本子")
    print(f"  - 操作类型：仅添加，不删除或修改现有数据")

    choice = input(f"\n确认继续？(y/n): ").strip().lower()
    if choice != 'y':
        print("\n❌ 操作已取消")
        return

    print(f"\n开始执行...\n")

    success = add_file_to_scene(SCENE_NAME, PDF_FILE_NAME)

    print("\n" + "=" * 60)
    if success:
        print("✅ 操作成功完成！")
    else:
        print("❌ 操作失败，请检查错误信息")
    print("=" * 60)


if __name__ == "__main__":
    main()

