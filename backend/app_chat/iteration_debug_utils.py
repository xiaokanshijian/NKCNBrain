"""
迭代调试工具：用于检测和记录迭代过程中的异常情况
"""
import re
import os
from datetime import datetime


def detect_and_log_anomalies(content, old_content, section_name=None, section_type=None):
    """
    🔥 检测内容中的异常情况并记录
    
    异常情况包括：
    1. 删除标签（如 <第xx次修改内容> 或 </第xx次修改内容> 被删除）
    2. 乱改引用标记（如 [xxx] 被修改或删除）
    3. 标签格式错误（如 </第xx次修改内容> 中的 / 被去掉）
    4. 出现 ***xxx*** 标记
    """
    try:
        anomalies = []
        
        # 1. 检测标签格式错误（缺少 / 的收尾标签）
        pattern_start = r'<第(\d+)次修改内容>'
        pattern_end = r'</第(\d+)次修改内容>'
        start_tags = {int(m.group(1)): m for m in re.finditer(pattern_start, content)}
        end_tags = {int(m.group(1)): m for m in re.finditer(pattern_end, content)}
        
        for tag_num in start_tags:
            if tag_num not in end_tags:
                anomalies.append(f"❌ 标签格式错误：第{tag_num}次修改内容的收尾标签缺少 `/` 或标签不匹配")
        
        # 检查是否有错误的收尾标签（缺少 /）
        wrong_end_pattern = r'<第(\d+)次修改内容>(?!</)'
        for match in re.finditer(wrong_end_pattern, content):
            tag_num = match.group(1)
            after_match = content[match.end():]
            # 检查后面是否有对应的正确结束标签
            if not re.search(rf'</第{tag_num}次修改内容>', after_match):
                # 检查是否有错误的格式（缺少/）
                if re.search(rf'<第{tag_num}次修改内容>', after_match):
                    anomalies.append(f"❌ 标签格式错误：第{tag_num}次修改内容的收尾标签缺少 `/`")
        
        # 2. 检测引用标记异常（如果旧内容有引用标记，新内容应该保留）
        if old_content:
            old_citations = re.findall(r'\[[^\]]+\]', old_content)
            new_citations = re.findall(r'\[[^\]]+\]', content)
            # 检查是否有引用标记被删除或修改
            for old_cite in old_citations:
                if old_cite not in content:
                    anomalies.append(f"❌ 引用标记被删除或修改：{old_cite}")
        
        # 3. 检测 ***xxx*** 标记
        user_edit_pattern = r'\*\*\*.*?\*\*\*'
        user_edit_matches = re.findall(user_edit_pattern, content)
        if user_edit_matches:
            anomalies.append(f"⚠️ 检测到 {len(user_edit_matches)} 个 ***xxx*** 标记")
            for i, match in enumerate(user_edit_matches[:3], 1):  # 只显示前3个
                anomalies.append(f"   - {i}. {match[:100]}...")
        
        # 4. 检测标签被删除（如果旧内容有标签，新内容应该保留）
        if old_content:
            old_tags = re.findall(r'<第\d+次修改内容>|</第\d+次修改内容>', old_content)
            for old_tag in old_tags:
                if old_tag not in content:
                    anomalies.append(f"❌ 标签被删除：{old_tag}")
        
        # 如果有异常，记录到文件
        if anomalies:
            try:
                current_file_dir = os.path.dirname(os.path.abspath(__file__))
                backend_dir = os.path.dirname(current_file_dir)
                output_dir = os.path.join(backend_dir, "预分析结果")
                os.makedirs(output_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                section_label = (section_name or "未知章节").replace('/', '_').replace('\\', '_')[:50]
                output_file = os.path.join(output_dir, f"异常检测_{section_label}_{timestamp}.txt")
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"异常检测报告 - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(f"章节: {section_label}\n")
                    f.write(f"类型: {section_type or '未知'}\n\n")
                    f.write("检测到的异常情况：\n")
                    f.write("-" * 80 + "\n")
                    for anomaly in anomalies:
                        f.write(f"{anomaly}\n")
                    f.write("\n" + "=" * 80 + "\n\n")
                    f.write("当前内容：\n")
                    f.write("-" * 80 + "\n")
                    f.write(content)
                    f.write("\n\n" + "=" * 80 + "\n\n")
                    if old_content:
                        f.write("旧内容（用于对比）：\n")
                        f.write("-" * 80 + "\n")
                        f.write(old_content)
                
                print(f"[detect_and_log_anomalies] ⚠️ 检测到{len(anomalies)}个异常情况，已保存到: {output_file}")
            except Exception as e:
                print(f"[detect_and_log_anomalies] ⚠️ 保存异常检测结果失败: {e}")
        
    except Exception as e:
        print(f"[detect_and_log_anomalies] 异常检测失败: {e}")
        import traceback
        traceback.print_exc()


def save_iteration_debug_output(content, section_name, section_type, stage_name, old_content=None):
    """
    🔥 保存迭代调试输出到文件
    
    参数:
        content: 要保存的内容
        section_name: 章节名
        section_type: 章节类型
        stage_name: 阶段名称（如"模型迭代完成原始输出"、"后处理后输出"等）
        old_content: 旧内容（用于对比）
    """
    try:
        # 检测是否有异常情况
        has_anomalies = False
        anomaly_details = []
        
        # 检测 ***xxx*** 标记
        if '***' in content:
            user_edit_matches = re.findall(r'\*\*\*.*?\*\*\*', content)
            if user_edit_matches:
                has_anomalies = True
                anomaly_details.append(f"⚠️ 包含 {len(user_edit_matches)} 个 ***xxx*** 标记")
        
        # 检测标签格式错误
        start_tags = re.findall(r'<第(\d+)次修改内容>', content)
        end_tags = re.findall(r'</第(\d+)次修改内容>', content)
        for tag_num in set(start_tags):
            if start_tags.count(tag_num) != end_tags.count(tag_num):
                has_anomalies = True
                anomaly_details.append(f"❌ 标签不匹配：第{tag_num}次修改内容的开始和结束标签数量不一致")
        
        # 检测错误的收尾标签（缺少 /）
        wrong_end_tags = re.findall(r'<第\d+次修改内容>(?!</)', content)
        if wrong_end_tags:
            has_anomalies = True
            anomaly_details.append(f"❌ 检测到错误的收尾标签格式（缺少 /）")
        
        # 只在有异常或特定阶段时保存
        if has_anomalies or stage_name in ["模型迭代完成原始输出", "后处理后输出", "二类后处理后输出"]:
            current_file_dir = os.path.dirname(os.path.abspath(__file__))
            backend_dir = os.path.dirname(current_file_dir)
            output_dir = os.path.join(backend_dir, "预分析结果")
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            section_label = (section_name or "未知章节").replace('/', '_').replace('\\', '_')[:50]
            stage_label = stage_name.replace('/', '_').replace('\\', '_')
            output_file = os.path.join(output_dir, f"迭代调试_{section_label}_{stage_label}_{timestamp}.txt")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"迭代调试输出 - {stage_name}\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"章节: {section_name or '未知'}\n")
                f.write(f"类型: {section_type or '未知'}\n")
                f.write(f"阶段: {stage_name}\n\n")
                
                if anomaly_details:
                    f.write("⚠️ 检测到的异常情况：\n")
                    f.write("-" * 80 + "\n")
                    for detail in anomaly_details:
                        f.write(f"{detail}\n")
                    f.write("\n" + "=" * 80 + "\n\n")
                
                f.write("当前内容：\n")
                f.write("-" * 80 + "\n")
                f.write(content)
                f.write("\n\n" + "=" * 80 + "\n\n")
                
                if old_content:
                    f.write("旧内容（用于对比）：\n")
                    f.write("-" * 80 + "\n")
                    f.write(old_content)
                    f.write("\n\n" + "=" * 80 + "\n")
            
            if has_anomalies:
                print(f"[save_iteration_debug_output] ⚠️ {stage_name}检测到异常，已保存到: {output_file}")
            else:
                print(f"[save_iteration_debug_output] ✅ {stage_name}已保存到: {output_file}")
                
    except Exception as e:
        print(f"[save_iteration_debug_output] ⚠️ 保存调试输出失败: {e}")

