"""
批量更新历史卡片的四色和DMT属性
运行方式：
1. 与 manage.py 同级目录下运行：python manage.py shell < batch_update_card_attributes.py
2. 或直接运行：python batch_update_card_attributes.py [用户名] [--force]
   - 用户名：可选，如果指定则只更新该用户的卡片
   - --force：可选，强制重新判定所有卡片（即使已有值也会重新判定）
"""

import os
import sys
import django

# 设置Django环境
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 脚本所在目录（backend/）
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')
django.setup()

from app_chat.models import Card
from app_chat.card_analyzer import analyze_four_color_type, analyze_dmt_level

def batch_update_card_attributes(username=None, force=False):
    """
    批量更新卡片的四色和DMT属性
    
    参数:
    - username: 如果指定，只更新该用户的卡片；如果为None，更新所有卡片
    - force: 如果为True，强制重新判定所有卡片（即使已有值也会重新判定）
    """
    if username:
        cards = Card.objects.filter(username=username)
        print(f"[批量更新] 开始更新用户 {username} 的卡片...")
    else:
        cards = Card.objects.all()
        print(f"[批量更新] 开始更新所有卡片...")
    
    if force:
        print(f"[批量更新] 🔥 强制模式：将重新判定所有卡片（即使已有值）")
    
    total_count = cards.count()
    print(f"[批量更新] 共找到 {total_count} 张卡片")
    
    updated_count = 0
    skipped_count = 0
    
    for i, card in enumerate(cards, 1):
        try:
            # 如果不是强制模式，跳过已有四色和DMT属性的卡片
            if not force:
                if card.four_color_type and card.four_color_type.strip() != '' and card.dmt_level and card.dmt_level.strip() != '':
                    skipped_count += 1
                    if i % 100 == 0:
                        print(f"[批量更新] 进度: {i}/{total_count}, 已更新: {updated_count}, 已跳过: {skipped_count}")
                    continue
            
            # 判定四色和DMT属性
            needs_save = False
            
            # 🔥 强制模式或没有四色属性时，重新判定
            if force or not card.four_color_type or card.four_color_type.strip() == '':
                four_color_type = analyze_four_color_type(card.content or '')
                # 即使返回空字符串，也更新（清除错误的值）
                card.four_color_type = four_color_type
                needs_save = True
                
            # 🔥 强制模式或没有DMT属性时，重新判定
            if force or not card.dmt_level or card.dmt_level.strip() == '':
                dmt_level = analyze_dmt_level(card.content or '')
                # 即使返回空字符串，也更新（清除错误的值）
                card.dmt_level = dmt_level
                needs_save = True
            
            # 如果有更新，保存
            if needs_save:
                card.save()
                updated_count += 1
            
            if i % 100 == 0:
                print(f"[批量更新] 进度: {i}/{total_count}, 已更新: {updated_count}, 已跳过: {skipped_count}")
                
        except Exception as e:
            print(f"[批量更新] 更新卡片 {card.cid} 失败: {e}")
            continue
    
    print(f"[批量更新] 完成！共更新 {updated_count} 张卡片，跳过 {skipped_count} 张卡片")

if __name__ == '__main__':
    import sys
    
    username = None
    force = False
    
    # 解析命令行参数
    for arg in sys.argv[1:]:
        if arg == '--force' or arg == '-f':
            force = True
        elif not arg.startswith('-'):
            username = arg
    
    if username:
        print(f"[批量更新] 指定用户名: {username}")
    else:
        print(f"[批量更新] 未指定用户名，将更新所有卡片")
    
    if force:
        print(f"[批量更新] 启用强制模式：将重新判定所有卡片")
    
    batch_update_card_attributes(username, force=force)

