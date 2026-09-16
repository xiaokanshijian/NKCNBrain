import base64
from pathlib import Path
import re
import sys
import os
import time
import numpy as np
import pandas as pd
import json
import cv2
from PIL import Image, ImageOps
from concurrent.futures import ThreadPoolExecutor, as_completed
from app_chat import gemini_api
from app_chat import qwen_vl_api
from .dmt_prompts import *
import io

# 全局变量：当前分割图片目录（在analyze_dmt_region中设置）
# CURRENT_SPLIT_IMG_DIR = "split_img"  # 移除全局变量，避免并发竞争条件

# 除乘加三块大区域的百分比坐标
T1_coords = {
    'M1': {
        'tl': [0.58, 0.603],  # 左上
        'br': [0.80, 0.75],  # 右下
        'angle': 15,  # 旋转角度
        'D1': {
            'tl': [0.035, 0.165],  # 左上
            'br': [0.485, 0.835],  # 右下
        },
        'D2': {
            'tl': [0.485, 0.066],  # 左上
            'br': [0.790, 0.685],  # 右下
        }
    },
    'M2': {
        'tl': [0.55, 0.735],  # 左上
        'br': [0.785, 0.90],  # 右下
        'angle': -17,  # 旋转角度
        'D1': {
            'tl': [0.15, 0.303],  # 左上
            'br': [0.60, 1.0],  # 右下
        },
        'D2': {
            'tl': [0.23, 0.04],  # 左上
            'br': [0.55, 0.25],  # 右下
        }
    },
    'M3': {
        'tl': [0.652, 0.68],  # 左上
        'br': [1.0, 0.865],  # 右下
        'angle': 25,  # 旋转角度
        'D1': {
            'tl': [0.255, 0.0],  # 左上
            'br': [1.0, 0.45],  # 右下
        },
        'D2': {
            'tl': [0.115, 0.45],  # 左上
            'br': [1.0, 0.68],  # 右下
        }
    }
}


def get_image_info(image_path):
    """
    获取图片文件的详细信息

    Args:
        image_path (str): 图片文件路径

    Returns:
        dict: 包含图片信息的字典
    """
    try:
        # 文件大小
        file_size = os.path.getsize(image_path)
        file_size_mb = file_size / (1024 * 1024)

        # 图片尺寸
        with Image.open(image_path) as img:
            width, height = img.size
            format_name = img.format
            mode = img.mode

        return {
            'file_path': image_path,
            'file_size_bytes': file_size,
            'file_size_mb': round(file_size_mb, 2),
            'width': width,
            'height': height,
            'format': format_name,
            'mode': mode,
            'needs_compression': file_size_mb > 10
        }
    except Exception as e:
        print(f"获取图片信息时发生错误: {e}")
        return None


def compress_image_if_needed(image_path, max_size_mb=10, quality=85, max_dimension=2048):
    """
    如果图片文件大小超过指定限制，则压缩图片

    Args:
        image_path (str): 图片文件路径
        max_size_mb (int): 最大文件大小限制（MB）
        quality (int): JPEG压缩质量（1-100）
        max_dimension (int): 最大尺寸限制（像素）

    Returns:
        bytes: 压缩后的图片二进制数据
    """
    # 获取文件大小
    file_size_mb = os.path.getsize(image_path) / (1024 * 1024)

    # 如果文件小于限制大小，直接返回原文件数据
    if file_size_mb <= max_size_mb:
        with open(image_path, "rb") as f:
            return f.read()

    print(f"图片文件大小 {file_size_mb:.2f}MB 超过限制 {max_size_mb}MB，正在压缩...")

    # 使用PIL打开并压缩图片
    with Image.open(image_path) as img:
        # 转换RGBA为RGB（避免PNG透明通道问题）
        if img.mode in ('RGBA', 'LA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # 自动旋转（基于EXIF数据）
        img = ImageOps.exif_transpose(img)

        # 计算新尺寸
        width, height = img.size
        if width > max_dimension or height > max_dimension:
            # 按比例缩放
            ratio = min(max_dimension / width, max_dimension / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"图片尺寸从 {width}x{height} 调整为 {new_width}x{new_height}")

        # 多次尝试压缩，直到文件大小满足要求
        current_quality = quality
        while current_quality > 10:
            # 保存到内存缓冲区
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=current_quality, optimize=True)
            compressed_data = buffer.getvalue()
            compressed_size_mb = len(compressed_data) / (1024 * 1024)

            print(f"压缩质量 {current_quality}%，文件大小 {compressed_size_mb:.2f}MB")

            # 如果压缩后大小满足要求，返回压缩数据
            if compressed_size_mb <= max_size_mb:
                print(f"压缩完成：{file_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB")
                return compressed_data

            # 降低质量继续压缩
            current_quality -= 10

        # 如果仍然太大，进一步缩小尺寸
        if compressed_size_mb > max_size_mb:
            print("进一步缩小图片尺寸...")
            current_max_dim = max_dimension
            while current_max_dim > 512 and compressed_size_mb > max_size_mb:
                current_max_dim = int(current_max_dim * 0.8)
                width, height = img.size
                ratio = min(current_max_dim / width, current_max_dim / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                resized_img.save(buffer, format='JPEG', quality=75, optimize=True)
                compressed_data = buffer.getvalue()
                compressed_size_mb = len(compressed_data) / (1024 * 1024)

                print(f"尺寸调整为 {new_width}x{new_height}，文件大小 {compressed_size_mb:.2f}MB")

                if compressed_size_mb <= max_size_mb:
                    print(f"最终压缩完成：{file_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB")
                    return compressed_data

        print(f"最终压缩结果：{file_size_mb:.2f}MB -> {compressed_size_mb:.2f}MB")
        return compressed_data


def encode_image_to_base64(image_path, max_size_mb=10):
    """
    将图片文件编码为base64字符串，如果文件大小超过限制则先压缩

    Args:
        image_path (str): 图片文件路径
        max_size_mb (int): 最大文件大小限制（MB），超过此大小会自动压缩

    Returns:
        str: base64编码的字符串
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(image_path):
            print(f"错误: 文件 '{image_path}' 不存在")
            return None

        # 获取压缩后的图片数据
        image_data = compress_image_if_needed(image_path, max_size_mb)

        # 编码为base64
        base64_encoded = base64.b64encode(image_data).decode('utf-8')
        return base64_encoded

    except Exception as e:
        print(f"编码过程中发生错误: {e}")
        return None


def get_image_base64_with_mime(image_path, max_size_mb=4):
    """
    获取图片的base64编码，包含MIME类型前缀，如果文件过大会自动压缩

    Args:
        image_path (str): 图片文件路径
        max_size_mb (int): 最大文件大小限制（MB）

    Returns:
        str: 包含MIME类型的完整base64字符串
    """
    # 获取文件扩展名
    file_extension = Path(image_path).suffix.lower()

    # 定义MIME类型映射
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
        '.tiff': 'image/tiff',
        '.svg': 'image/svg+xml'
    }

    # 获取MIME类型，如果压缩了图片，使用jpeg格式
    file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
    if file_size_mb > max_size_mb and file_extension not in ['.svg']:
        # 压缩后的图片使用JPEG格式
        mime_type = 'image/jpeg'
    else:
        mime_type = mime_types.get(file_extension, 'image/jpeg')

    # 获取base64编码
    base64_string = encode_image_to_base64(image_path, max_size_mb)

    if base64_string:
        # 返回完整的data URL格式
        return f"data:{mime_type};base64,{base64_string}"
    else:
        return None


def convert_value2str(value):
    """转换数值为字符串，空值返回空字符串"""
    if pd.isna(value):
        return ""
    # 如果是整数类型，转换为整数字符串
    if isinstance(value, (int, float)) and value == int(value):
        return str(int(value))
    return str(value)


def convert_str2value(value):
    """将字符串转换为数值类型"""
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value  # 如果无法转换为数字，则返回原字符串


def extract_excel_to_json(file_path, output_json_path, sheet_name='Sheet1'):
    """
    从Excel文件提取指定字段并保存为JSON文件

    Args:
        file_path (str): Excel文件路径
        output_json_path (str): 输出JSON文件路径
        sheet_name (str): 工作表名称，默认为'Sheet1'
    """
    # 定义列名（根据实际数据调整）
    columns = [
        '序号', 'T级编号', 'T级描述', 'M级编号', 'M级区域描述', 'D级编号', 'D级区域描述',
        '机制结构位置及评价标准', '预置内容',
        '左上（实际尺寸）x', '左上（实际尺寸）y',
        '左下（实际尺寸）x', '左下（实际尺寸）y',
        '右上（实际尺寸）x', '右上（实际尺寸）y',
        '右下（实际尺寸）x', '右下（实际尺寸）y',
        '左上(百分比)x', '左上(百分比)y',
        '左下(百分比)x', '左下(百分比)y',
        '右上(百分比)x', '右上(百分比)y',
        '右下(百分比)x', '右下(百分比)y'
    ]

    # 读取Excel文件
    df = pd.read_excel(file_path, sheet_name='Sheet1', header=None, skiprows=3, names=columns)
    # 初始化数据结构
    json_data = {}
    current_T_id = None
    current_M_id = None

    for _, row in df.iterrows():
        # 处理T级
        T_id = convert_value2str(row['T级编号'])
        if T_id:
            current_T_id = T_id
            if T_id not in json_data:
                json_data[T_id] = {
                    'T级描述': convert_value2str(row['T级描述']),
                }
            # 重置M级
            current_M_id = None

        # 处理M级
        M_id = convert_value2str(row['M级编号'])
        current_T_node = json_data.get(current_T_id, {}) if current_T_id else {}

        if M_id:
            current_M_id = M_id
            if M_id not in current_T_node:
                current_T_node[M_id] = {
                    'M级区域描述': convert_value2str(row['M级区域描述']),
                }
            # 确保引用正确
            json_data[current_T_id] = current_T_node

        # 处理D级
        D_id = convert_value2str(row['D级编号'])
        if D_id:
            # 构建D级数据
            d_data = {
                'D级区域描述': convert_value2str(row['D级区域描述']),
                '机制结构位置及评价标准': convert_value2str(row['机制结构位置及评价标准']),
                '预置内容': convert_value2str(row['预置内容']),
                '左上（实际尺寸）': {
                    'x': convert_value2str(row['左上（实际尺寸）x']),
                    'y': convert_value2str(row['左上（实际尺寸）y'])
                },
                '左下（实际尺寸）': {
                    'x': convert_value2str(row['左下（实际尺寸）x']),
                    'y': convert_value2str(row['左下（实际尺寸）y'])
                },
                '右上（实际尺寸）': {
                    'x': convert_value2str(row['右上（实际尺寸）x']),
                    'y': convert_value2str(row['右上（实际尺寸）y'])
                },
                '右下（实际尺寸）': {
                    'x': convert_value2str(row['右下（实际尺寸）x']),
                    'y': convert_value2str(row['右下（实际尺寸）y'])
                },
                '左上(百分比)': {
                    'x': convert_value2str(row['左上(百分比)x']),
                    'y': convert_value2str(row['左上(百分比)y'])
                },
                '左下(百分比)': {
                    'x': convert_value2str(row['左下(百分比)x']),
                    'y': convert_value2str(row['左下(百分比)y'])
                },
                '右上(百分比)': {
                    'x': convert_value2str(row['右上(百分比)x']),
                    'y': convert_value2str(row['右上(百分比)y'])
                },
                '右下(百分比)': {
                    'x': convert_value2str(row['右下(百分比)x']),
                    'y': convert_value2str(row['右下(百分比)y'])
                }
            }

            # 确定插入位置
            if current_T_id:
                target = current_T_node
                if current_M_id:
                    if current_M_id not in current_T_node:
                        current_T_node[current_M_id] = {
                            'M级区域描述': convert_value2str(row['M级区域描述'])
                        }
                    target = current_T_node[current_M_id]

                # 插入D级数据
                if D_id not in target:
                    target[D_id] = d_data
                else:
                    # 如果D级已存在，合并数据（以最新数据为准）
                    target[D_id].update(d_data)

    # 保存为JSON文件
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)

    print(f"JSON文件已生成：{output_json_path}")


def crop_image_by_percent(image_path, percent_coords, output_path):
    """
    根据百分比坐标裁剪图片并保存

    Args:
        image_path (str): 原始图片路径
        percent_coords (dict): 左上角和右下角顶点的百分比坐标，格式为
            {
                'tl': [x, y],  # 左上
                'br': [x, y],  # 右下
            }
        output_path (str): 裁剪后图片的保存路径
    """
    # 使用支持中文路径的方式读取图片
    try:
        # 先用二进制方式读取文件
        with open(image_path, 'rb') as f:
            img_data = f.read()
        # 使用cv2.imdecode从内存中解码图片
        img_array = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        raise FileNotFoundError(f"无法读取图片文件：{image_path}，错误：{str(e)}")

    if img is None:
        raise FileNotFoundError(f"无法解析图片文件：{image_path}")

    height, width = img.shape[0], img.shape[1]
    tl = percent_coords['tl']
    br = percent_coords['br']

    top_left = (int(tl[0] * width), int(tl[1] * height))
    bottom_right = (int(br[0] * width), int(br[1] * height))
    # 在原先大小的基础上适当扩大裁剪区域
    top_left = (max(0, top_left[0] - 5), max(0, top_left[1] - 5))
    bottom_right = (min(width, bottom_right[0] + 5), min(height, bottom_right[1] + 5))

    # 裁剪图片（假设为矩形区域）
    cropped_img = img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]

    # 使用支持中文路径的方式保存图片
    try:
        # 编码图片到内存
        success, encoded_img = cv2.imencode('.png', cropped_img)
        if success:
            # 写入文件
            with open(output_path, 'wb') as f:
                f.write(encoded_img.tobytes())
            print(f"裁剪后的图片已保存到：{output_path}")
        else:
            raise Exception("图片编码失败")
    except Exception as e:
        raise Exception(f"无法保存图片文件：{output_path}，错误：{str(e)}")


def rotate_image(image_path, angle, output_path):
    """
    读取图像并按指定角度旋转后保存

    Args:
        image_path (str): 输入图片路径
        angle (float): 旋转角度（度）
        output_path (str): 输出图片路径

    Returns:
        numpy.ndarray: 旋转后的图像
    """
    # 使用支持中文路径的方式读取图片
    try:
        # 先用二进制方式读取文件
        with open(image_path, 'rb') as f:
            img_data = f.read()
        # 使用cv2.imdecode从内存中解码图片
        img_array = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        raise FileNotFoundError(f"无法读取图片文件：{image_path}，错误：{str(e)}")

    if img is None:
        raise FileNotFoundError(f"无法解析图片文件：{image_path}")

    h, w = img.shape[:2]

    # rows, cols = img.shape[:2]
    # M = cv2.getRotationMatrix2D((cols / 2, rows / 2), angle, 1)
    # rotated_img = cv2.warpAffine(img, M, (cols, rows))
    # cv2.imwrite(output_path, rotated_img)
    # return rotated_img

    # # #######获取没有裁剪的旋转图像#########
    # 定义空矩阵
    M = np.zeros((2, 3), dtype=np.float32)
    # 设定旋转角度
    alpha = np.cos(angle * np.pi / 180.0)
    beta = np.sin(angle * np.pi / 180.0)
    # 初始化旋转矩阵
    M[0, 0] = alpha
    M[1, 1] = alpha
    M[0, 1] = beta
    M[1, 0] = -beta
    # 图片中心点坐标
    cx = w / 2
    cy = h / 2

    # 变化的宽高
    tx = (1 - alpha) * cx - beta * cy
    ty = beta * cx + (1 - alpha) * cy
    M[0, 2] = tx
    M[1, 2] = ty

    # 旋转后的图像高、宽
    rotated_w = int(h * np.abs(beta) + w * np.abs(alpha))
    rotated_h = int(h * np.abs(alpha) + w * np.abs(beta))

    # 移动后的中心位置
    M[0, 2] += rotated_w / 2 - cx
    M[1, 2] += rotated_h / 2 - cy

    result = cv2.warpAffine(img, M, (rotated_w, rotated_h))

    # 使用支持中文路径的方式保存图片
    try:
        # 编码图片到内存
        success, encoded_img = cv2.imencode('.png', result)
        if success:
            # 写入文件
            with open(output_path, 'wb') as f:
                f.write(encoded_img.tobytes())
            print(f"旋转后的图片已保存到：{output_path}")
        else:
            raise Exception("图片编码失败")
    except Exception as e:
        raise Exception(f"无法保存图片文件：{output_path}，错误：{str(e)}")

    return result


def batch_crop_images_from_json(json_file, img_path, output_dir):
    """
    根据JSON文件中的百分比坐标批量裁剪图片并保存

    Args:
        json_file (str): JSON文件路径
        img_path (str): 原始图片路径
        output_dir (str): 裁剪后图片保存目录
    """
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for T_no in data:
            x1_t, y1_t = sys.maxsize, sys.maxsize
            x2_t, y2_t = 0, 0
            # if T_no == 'T1':
            #     for M_no, coords in T1_coords.items():
            #         output_path = f"{output_dir}/crop_T1_{M_no}.png"
            #         crop_image_by_percent(
            #             img_path,
            #             coords,
            #             output_path
            #         )
            #         x1_t, y1_t = min(x1_t, coords['tl'][0]), min(y1_t, coords['tl'][1])
            #         x2_t, y2_t = max(x2_t, coords['br'][0]), max(y2_t, coords['br'][1])
            #         rotated_path = f"{output_dir}/rotated_T1_{M_no}.png"
            #         rotate_image(output_path, coords['angle'], rotated_path)
            #         for D_no, d_coords in coords.items():
            #             if not D_no.startswith('D'):
            #                 continue
            #             output_path = f"{output_dir}/crop_T1_{M_no}_{D_no}.png"
            #             crop_image_by_percent(
            #                 rotated_path,
            #                 d_coords,
            #                 output_path
            #             )
            #     if x1_t == sys.maxsize or y1_t == sys.maxsize or x2_t == 0 or y2_t == 0:
            #         continue
            #     crop_image_by_percent(
            #         img_path,
            #         {
            #             'tl': [x1_t, y1_t],  # 左上
            #             'br': [x2_t, y2_t]   # 右下
            #         },
            #         f"{output_dir}/crop_{T_no}.png"
            #     )
            # else:
            T_item = data[T_no]
            if 'M1' in T_item:
                for M_no in T_item:
                    if not M_no.startswith('M'):
                        continue
                    M_item = T_item[M_no]
                    x1_m, y1_m = sys.maxsize, sys.maxsize
                    x2_m, y2_m = 0, 0
                    for D_no in M_item:
                        if not D_no.startswith('D'):
                            continue
                        D_item = M_item[D_no]
                        x1 = convert_str2value(D_item["左上(百分比)"]["x"])
                        y1 = convert_str2value(D_item["左上(百分比)"]["y"])
                        x2 = convert_str2value(D_item["右下(百分比)"]["x"])
                        y2 = convert_str2value(D_item["右下(百分比)"]["y"])
                        if x1 == '' or x1 == 0 or y1 == '' or y1 == 0 or x2 == '' or x2 == 0 or y2 == '' or y2 == 0:
                            continue
                        crop_image_by_percent(
                            img_path,
                            {
                                'tl': [x1, y1],  # 左上
                                'br': [x2, y2]   # 右下
                            },
                            f"{output_dir}/crop_{T_no}_{M_no}_{D_no}.png"
                        )
                        x1_m, y1_m = min(x1_m, x1), min(y1_m, y1)
                        x2_m, y2_m = max(x2_m, x2), max(y2_m, y2)
                    if x1_m == sys.maxsize or y1_m == sys.maxsize or x2_m == 0 or y2_m == 0:
                        continue
                    crop_image_by_percent(
                        img_path,
                        {
                            'tl': [x1_m, y1_m],  # 左上
                            'br': [x2_m, y2_m]   # 右下
                        },
                        f"{output_dir}/crop_{T_no}_{M_no}.png"
                    )
                    x1_t, y1_t = min(x1_t, x1_m), min(y1_t, y1_m)
                    x2_t, y2_t = max(x2_t, x2_m), max(y2_t, y2_m)
            elif 'D1' in T_item:
                for D_no in T_item:
                    if not D_no.startswith('D'):
                        continue
                    D_item = T_item[D_no]
                    x1 = convert_str2value(D_item["左上(百分比)"]["x"])
                    y1 = convert_str2value(D_item["左上(百分比)"]["y"])
                    x2 = convert_str2value(D_item["右下(百分比)"]["x"])
                    y2 = convert_str2value(D_item["右下(百分比)"]["y"])
                    if x1 == '' or x1 == 0 or y1 == '' or y1 == 0 or x2 == '' or x2 == 0 or y2 == '' or y2 == 0:
                        continue
                    crop_image_by_percent(
                        img_path,
                        {
                            'tl': [x1, y1],  # 左上
                            'br': [x2, y2]   # 右下
                        },
                        f"{output_dir}/crop_{T_no}_{D_no}.png"
                    )
                    x1_t, y1_t = min(x1_t, x1), min(y1_t, y1)
                    x2_t, y2_t = max(x2_t, x2), max(y2_t, y2)
            if x1_t == sys.maxsize or y1_t == sys.maxsize or x2_t == 0 or y2_t == 0:
                continue
            if T_no == 'T0':
                x1_t, y1_t = 0, 0
                x2_t, y2_t = 1, 1
            crop_image_by_percent(
                img_path,
                {
                    'tl': [x1_t, y1_t],  # 左上
                    'br': [x2_t, y2_t]  # 右下
                },
                f"{output_dir}/crop_{T_no}.png"
            )


def extract_json_str(json_str: str):
    """
    从JSON字符串中提取数据，处理可能的解析错误

    Args:
        json_str (str): JSON格式的字符串

    Returns:
        dict: 解析后的字典对象
    """
    # 提取```json```标记内的内容
    json_str = json_str.strip()
    if '```json' in json_str:
        json_str = json_str.split('```json')[1].split('```')[0].strip()
    elif '```' in json_str:
        json_str = json_str.split('```')[1].strip()
    # 尝试解析JSON字符串
    data = json.loads(json_str)
    return data


def analyze_d_panel(task_info):
    """
    分析D版面的函数，用于并发执行

    Args:
        task_info: 包含分析所需信息的字典

    Returns:
        tuple: (T_no, M_no, D_no, result) 或 (T_no, D_no, None, result)
    """
    T_no = task_info['T_no']
    M_no = task_info.get('M_no')
    D_no = task_info['D_no']
    img_path = task_info['img_path']
    base_prompt = task_info['base_prompt']
    figure_prompt = task_info['figure_prompt']
    D_item = task_info['D_item']
    D_prompt = task_info['D_prompt']
    handwritten_prompt = task_info['handwritten_prompt']
    printed_prompt = task_info['printed_prompt']
    group_prompt = task_info['group_prompt']

    print(f"\n-------处理D版面: {img_path}-------")

    try:
        # if D_item['预置内容'] != "":
        #     result = {"content_text": f"印刷内容: {D_item['预置内容']}"}
        #     figure_prompt += get_panel_type_prompt('preset_content', preset_content=D_item['预置内容'])
        #     if T_no == 'T0' and D_no == 'D2':
        #         json_str = qwen_vl_api.generate(
        #             image_urls=[get_image_base64_with_mime(img_path)],
        #             user_prompt=base_prompt + figure_prompt + group_prompt
        #         )
        #     else:
        #         json_str = qwen_vl_api.generate(
        #             image_urls=[get_image_base64_with_mime(img_path)],
        #             user_prompt=base_prompt + figure_prompt + printed_prompt
        #         )
        #     try:
        #         res = extract_json_str(json_str)
        #         print(res)
        #         result.update(res)
        #     except json.JSONDecodeError:
        #         print(f"JSON解析错误，尝试重新生成: {json_str}")
        #         # 重试一次，添加更明确的格式要求
        #         retry_prompt = get_retry_prompt(base_prompt + figure_prompt + handwritten_prompt)
        #         try:
        #             json_str_retry = qwen_vl_api.generate(
        #                 image_urls=[get_image_base64_with_mime(img_path)],
        #                 user_prompt=retry_prompt
        #             )
        #             res = extract_json_str(json_str_retry)
        #             print(f"重试成功: {res}")
        #             result.update(res)
        #         except json.JSONDecodeError:
        #             print(f"重试后仍然JSON解析错误，返回原始内容: {json_str_retry if 'json_str_retry' in locals() else json_str}")
        #             result.update({"error": "JSON解析错误", "content": json_str_retry if 'json_str_retry' in locals() else json_str})
        #         except Exception as e:
        #             print(f"重试时发生错误: {e}")
        #             result.update({"error": "重试失败", "content": json_str})
        # else:
        #     figure_prompt += get_panel_type_prompt('handwritten_area')
        #     json_str = qwen_vl_api.generate(
        #         image_urls=[get_image_base64_with_mime(img_path)],
        #         user_prompt=base_prompt + figure_prompt + handwritten_prompt
        #     )
        #     try:
        #         result = extract_json_str(json_str)
        #         print(result)
        #     except json.JSONDecodeError:
        #         print(f"JSON解析错误，尝试重新生成: {json_str}")
        #         # 重试一次，添加更明确的格式要求
        #         retry_prompt = get_retry_prompt(base_prompt + figure_prompt + handwritten_prompt)
        #         try:
        #             json_str_retry = qwen_vl_api.generate(
        #                 image_urls=[get_image_base64_with_mime(img_path)],
        #                 user_prompt=retry_prompt
        #             )
        #             result = extract_json_str(json_str_retry)
        #             print(f"重试成功: {result}")
        #         except json.JSONDecodeError:
        #             print(f"重试后仍然JSON解析错误，返回原始内容: {json_str_retry if 'json_str_retry' in locals() else json_str}")
        #             result = {"error": "JSON解析错误", "content": json_str_retry if 'json_str_retry' in locals() else json_str}
        #         except Exception as e:
        #             print(f"重试时发生错误: {e}")
        #             result = {"error": "重试失败", "content": json_str}
        if D_item['预置内容'] != "":
            figure_prompt += get_panel_type_prompt('preset_content', preset_content=D_item['预置内容'])
        else:
            figure_prompt += get_panel_type_prompt('handwritten_area')
        json_str = qwen_vl_api.generate(
            image_urls=[get_image_base64_with_mime(img_path)],
            user_prompt=base_prompt + figure_prompt + D_prompt
        )
        try:
            result = extract_json_str(json_str)
            print(result)
        except json.JSONDecodeError:
            print(f"JSON解析错误，尝试重新生成: {json_str}")
            # 重试一次，添加更明确的格式要求
            retry_prompt = get_retry_prompt(base_prompt + figure_prompt + D_prompt)
            try:
                json_str_retry = qwen_vl_api.generate(
                    image_urls=[get_image_base64_with_mime(img_path)],
                    user_prompt=retry_prompt
                )
                result = extract_json_str(json_str_retry)
                print(f"重试成功: {result}")
            except json.JSONDecodeError:
                print(f"重试后仍然JSON解析错误，返回原始内容: {json_str_retry if 'json_str_retry' in locals() else json_str}")
                result = {"error": "JSON解析错误", "content": json_str_retry if 'json_str_retry' in locals() else json_str}
            except Exception as e:
                print(f"重试时发生错误: {e}")
                result = {"error": "重试失败", "content": json_str}
        result['D级区域描述'] = D_item['D级区域描述']
        result['机制结构位置及评价标准'] = D_item['机制结构位置及评价标准']
        if M_no:
            return (T_no, M_no, D_no, result)
        else:
            return (T_no, D_no, None, result)

    except Exception as e:
        print(f"处理D版面 {img_path} 时发生错误: {e}")
        if M_no:
            return (T_no, M_no, D_no, {"error": str(e)})
        else:
            return (T_no, D_no, None, {"error": str(e)})


def analyze_m_panel(task_info):
    """
    分析M版面的函数，用于并发执行

    Args:
        task_info: 包含分析所需信息的字典

    Returns:
        tuple: (T_no, M_no, result)
    """
    T_no = task_info['T_no']
    M_no = task_info['M_no']
    img_path = task_info['img_path']
    base_prompt = task_info['base_prompt']
    figure_prompt = task_info['figure_prompt']
    M_prompt = task_info['M_prompt']
    img_urls = task_info['img_urls']
    img_prompts = task_info['img_prompts']
    M_item = task_info['M_item']

    print(f"\n-------处理M版面: {img_path}-------")

    try:
        json_str = qwen_vl_api.generate(
            image_urls=img_urls,
            user_prompt=base_prompt + figure_prompt + M_prompt,
            image_prompts=img_prompts
        )
        try:
            result = extract_json_str(json_str)
            print(result)
            result['M级区域描述'] = M_item['M级区域描述']
            return (T_no, M_no, result)
        except json.JSONDecodeError:
            print(f"JSON解析错误，尝试重新生成: {json_str}")
            # 重试一次，添加更明确的格式要求
            retry_prompt = get_retry_prompt(base_prompt + figure_prompt + M_prompt)
            try:
                json_str_retry = qwen_vl_api.generate(
                    image_urls=img_urls,
                    user_prompt=retry_prompt,
                    image_prompts=img_prompts
                )
                result = extract_json_str(json_str_retry)
                print(f"重试成功: {result}")
                result['M级区域描述'] = M_item['M级区域描述']
                return (T_no, M_no, result)
            except json.JSONDecodeError:
                print(f"重试后仍然JSON解析错误，返回原始内容: {json_str_retry if 'json_str_retry' in locals() else json_str}")
                return (T_no, M_no, {"error": "JSON解析错误", "content": json_str_retry if 'json_str_retry' in locals() else json_str})
            except Exception as e:
                print(f"重试时发生错误: {e}")
                return (T_no, M_no, {"error": "重试失败", "content": json_str})

    except Exception as e:
        print(f"处理M版面 {img_path} 时发生错误: {e}")
        return (T_no, M_no, {"error": str(e)})


def analyze_t_panel(task_info):
    """
    分析T版面的函数，用于并发执行

    Args:
        task_info: 包含分析所需信息的字典

    Returns:
        tuple: (T_no, result)
    """
    T_no = task_info['T_no']
    img_path = task_info['img_path']
    base_prompt = task_info['base_prompt']
    figure_prompt = task_info['figure_prompt']
    T_prompt = task_info['T_prompt']
    img_urls = task_info['img_urls']
    img_prompts = task_info['img_prompts']
    T_item = task_info['T_item']

    print(f"\n-------处理T版面: {img_path}-------")

    try:
        json_str = qwen_vl_api.generate(
            image_urls=img_urls,
            user_prompt=base_prompt + figure_prompt + T_prompt,
            image_prompts=img_prompts
        )
        try:
            result = extract_json_str(json_str)
            print(result)
            result['T级描述'] = T_item['T级描述']
            return (T_no, result)
        except json.JSONDecodeError:
            print(f"JSON解析错误，尝试重新生成: {json_str}")
            # 重试一次，添加更明确的格式要求
            retry_prompt = get_retry_prompt(base_prompt + figure_prompt + T_prompt)
            try:
                json_str_retry = qwen_vl_api.generate(
                    image_urls=img_urls,
                    user_prompt=retry_prompt,
                    image_prompts=img_prompts
                )
                result = extract_json_str(json_str_retry)
                print(f"重试成功: {result}")
                result['T级描述'] = T_item['T级描述']
                return (T_no, result)
            except json.JSONDecodeError:
                print(f"重试后仍然JSON解析错误，返回原始内容: {json_str_retry if 'json_str_retry' in locals() else json_str}")
                return (T_no, {"error": "JSON解析错误", "content": json_str_retry if 'json_str_retry' in locals() else json_str})
            except Exception as e:
                print(f"重试时发生错误: {e}")
                return (T_no, {"error": "重试失败", "content": json_str})

    except Exception as e:
        print(f"处理T版面 {img_path} 时发生错误: {e}")
        return (T_no, {"error": str(e)})


def analyze_d_regions(json_file, progress_callback=None, start_progress=0, end_progress=100, split_img_dir=None, max_workers=5):
    """
    分析所有D版面

    Args:
        json_file: JSON配置文件路径
        progress_callback: 进度回调函数，接收 (progress, stage) 参数
        split_img_dir: 分割图片目录路径

    Returns:
        dict: 分析结果字典
    """
    D_prompt = get_prompt('D', 'analysis')
    handwritten_prompt = get_prompt('D', 'handwritten')
    printed_prompt = get_prompt('D', 'printed')
    group_prompt = get_prompt('D', 'group')

    res = {}
    d_start_time = time.time()
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if 'M1' in data['T0']:
            base_prompt = get_base_prompt('D', data['T0']['M1']['D1']['预置内容'])
        else:
            base_prompt = get_base_prompt('D', data['T0']['D1']['预置内容'])
        if '梯子火种·堤坝洪流筛分框架说明图' in base_prompt:
            base_prompt += """其中可能涉及的概念包括：
- 码释：代码和注释的合称
- 蛙鸣：指代小组同学涌现出的创新创造
- 组型：小组类型，依据小组水平进行划分，水平从低到高依次为：萝卜+、苹果-、苹果
- ÷×＋：“除乘加”三法则，嵌入式系统课程的核心理论
- xxx：指代模板中的待填部分
- 实验箱：车联I、车联II、纸联III三个课设主题所使用的实验装置
- 实验盒：体联IV课设主题所使用的实验装置
- 问解通道：问题解决通道，用于学生向TA（助教）或其他同学发问求助"""

        # 收集所有D版面任务
        d_tasks = []

        for T_no, T_item in data.items():
            res[T_no] = {}
            T_base_prompt = base_prompt + f"该版面所在的层级结构是：{data[T_no]['T级描述']}"

            if 'M1' in T_item:
                # 三级结构：T->M->D
                for M_no, M_item in T_item.items():
                    if not M_no.startswith('M'):
                        continue
                    res[T_no][M_no] = {}
                    M_base_prompt = T_base_prompt + f"->{data[T_no][M_no]['M级区域描述']}"

                    for D_no, D_item in M_item.items():
                        if not D_no.startswith('D'):
                            continue
                        res[T_no][M_no][D_no] = {}
                        img_path = f"{split_img_dir}/crop_{T_no}_{M_no}_{D_no}.png"

                        if not os.path.exists(img_path):
                            continue

                        figure_prompt = f"->{data[T_no][M_no][D_no]['D级区域描述']}\n"

                        task_info = {
                            'T_no': T_no,
                            'M_no': M_no,
                            'D_no': D_no,
                            'img_path': img_path,
                            'base_prompt': M_base_prompt,
                            'figure_prompt': figure_prompt,
                            'D_item': D_item,
                            'handwritten_prompt': handwritten_prompt,
                            'printed_prompt': printed_prompt,
                            'group_prompt': group_prompt,
                            'D_prompt': D_prompt
                        }
                        d_tasks.append(task_info)

            elif 'D1' in T_item:
                # 二级结构：T->D
                for D_no, D_item in T_item.items():
                    if not D_no.startswith('D'):
                        continue
                    res[T_no][D_no] = {}
                    img_path = f"{split_img_dir}/crop_{T_no}_{D_no}.png"

                    if not os.path.exists(img_path):
                        continue

                    figure_prompt = f"->{data[T_no][D_no]['D级区域描述']}\n"

                    task_info = {
                        'T_no': T_no,
                        'M_no': None,
                        'D_no': D_no,
                        'img_path': img_path,
                        'base_prompt': T_base_prompt,
                        'figure_prompt': figure_prompt,
                        'D_item': D_item,
                        'handwritten_prompt': handwritten_prompt,
                        'printed_prompt': printed_prompt,
                        'group_prompt': group_prompt,
                        'D_prompt': D_prompt
                    }
                    d_tasks.append(task_info)

        total_d_panels = len(d_tasks)
        print(f"总共需要处理 {total_d_panels} 个D版面，使用{max_workers}个并发执行")

        if progress_callback:
            progress_callback(start_progress, f"正在分析D版面：0/{total_d_panels}")

        # 使用并发处理器并行处理D版面
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {executor.submit(analyze_d_panel, task): task for task in d_tasks}

            # 处理结果
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result_tuple = future.result()
                    T_no, M_no_or_D_no, D_no_or_None, result = result_tuple

                    # 根据返回值确定是三级还是二级结构
                    if D_no_or_None is not None:
                        # 三级结构：T->M->D
                        M_no = M_no_or_D_no
                        D_no = D_no_or_None
                        res[T_no][M_no][D_no] = result
                    else:
                        # 二级结构：T->D
                        D_no = M_no_or_D_no
                        res[T_no][D_no] = result

                    completed_count += 1
                    print(f"已完成D版面分析: {task['img_path']} ({completed_count}/{total_d_panels})")

                    # 更新进度
                    if progress_callback and total_d_panels > 0:
                        progress = start_progress + (end_progress - start_progress) * completed_count / total_d_panels
                        progress_callback(int(progress), f"正在分析D版面：{completed_count}/{total_d_panels}")

                except Exception as e:
                    print(f"任务执行失败 {task['img_path']}: {e}")
                    # 记录错误信息到结果中
                    if task['M_no']:
                        res[task['T_no']][task['M_no']][task['D_no']] = {"error": str(e)}
                    else:
                        res[task['T_no']][task['D_no']] = {"error": str(e)}

                    completed_count += 1
                    if progress_callback and total_d_panels > 0:
                        progress = start_progress + (end_progress - start_progress) * completed_count / total_d_panels
                        progress_callback(int(progress), f"正在分析D版面：{completed_count}/{total_d_panels}")

        print("所有D版面分析完成！")
        print(f"D版面分析耗时: {time.time() - d_start_time:.2f}秒")

    return res


def analyze_m_regions(json_file, d_results, progress_callback=None, start_progress=0, end_progress=100,
                      split_img_dir=None, max_workers=5):
    """
    分析所有M版面

    Args:
        json_file: JSON配置文件路径
        d_results: D版面分析结果
        progress_callback: 进度回调函数，接收 (progress, stage) 参数
        split_img_dir: 分割图片目录路径

    Returns:
        dict: 更新后的分析结果字典
    """
    M_prompt = get_prompt('M', 'analysis')

    res = d_results.copy()
    m_start_time = time.time()

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if 'M1' in data['T0']:
            base_prompt = get_base_prompt('M', data['T0']['M1']['D1']['预置内容'])
        else:
            base_prompt = get_base_prompt('M', data['T0']['D1']['预置内容'])

        # 收集所有M版面任务
        m_tasks = []

        for T_no, T_item in data.items():
            if T_no == 'T0':
                continue  # 跳过T0版面
            if 'M1' in T_item:
                for M_no, M_item in T_item.items():
                    if not M_no.startswith('M'):
                        continue

                    M_base_prompt = base_prompt + f"该版面所在的层级结构是：{data[T_no]['T级描述']}->{data[T_no][M_no]['M级区域描述']}\n"

                    # if T_no == 'T1':
                    #     img_path = f"{split_img_dir}/rotated_{T_no}_{M_no}.png"
                    # else:
                    #     img_path = f"{split_img_dir}/crop_{T_no}_{M_no}.png"
                    img_path = f"{split_img_dir}/crop_{T_no}_{M_no}.png"

                    if not os.path.exists(img_path):
                        continue

                    # 准备D版面的图片和提示信息
                    img_urls, img_prompts = [], []
                    for D_no, D_item in res[T_no][M_no].items():
                        if D_item == {}:
                            continue
                        D_img_path = f"{split_img_dir}/crop_{T_no}_{M_no}_{D_no}.png"
                        img_urls.append(get_image_base64_with_mime(D_img_path, max_size_mb=9/len(res[T_no][M_no])))

                        # 使用模板生成图片描述
                        if 'format_evaluation' in D_item and 'confidence' in D_item:
                            img_prompt = get_image_description('D_panel_with_evaluation',
                                                               panel_id=M_item[D_no]['D级区域描述'],
                                                               content_text=D_item.get('content_text', ''),
                                                               otcl_analysis=D_item.get('otcl_analysis', ''),
                                                               format_evaluation=D_item['format_evaluation'],
                                                               confidence=D_item['confidence']
                                                               )
                        else:
                            img_prompt = get_image_description('D_panel',
                                                               panel_id=M_item[D_no]['D级区域描述'],
                                                               content_text=D_item.get('content_text', ''),
                                                               otcl_analysis=D_item.get('otcl_analysis', '')
                                                               )

                        img_prompts.append(img_prompt)

                    img_urls.append(get_image_base64_with_mime(img_path, max_size_mb=1))
                    figure_prompt = get_panel_type_prompt('contains_d_panels')

                    task_info = {
                        'T_no': T_no,
                        'M_no': M_no,
                        'img_path': img_path,
                        'base_prompt': M_base_prompt,
                        'figure_prompt': figure_prompt,
                        'M_prompt': M_prompt,
                        'img_urls': img_urls,
                        'img_prompts': img_prompts,
                        'M_item': M_item
                    }
                    m_tasks.append(task_info)

        total_m_panels = len(m_tasks)
        print(f"总共需要处理 {total_m_panels} 个M版面，使用{max_workers}个并发执行")

        if progress_callback:
            progress_callback(start_progress, f"正在分析M版面：0/{total_m_panels}")

        # 使用并发处理器并行处理M版面
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {executor.submit(analyze_m_panel, task): task for task in m_tasks}

            # 处理结果
            for future in as_completed(futures):
                task = futures[future]
                try:
                    T_no, M_no, result = future.result()
                    res[T_no][M_no].update(result)

                    completed_count += 1
                    print(f"已完成M版面分析: {task['img_path']} ({completed_count}/{total_m_panels})")

                    # 更新进度
                    if progress_callback and total_m_panels > 0:
                        progress = start_progress + (end_progress - start_progress) * completed_count / total_m_panels
                        progress_callback(int(progress), f"正在分析M版面：{completed_count}/{total_m_panels}")

                except Exception as e:
                    print(f"M版面任务执行失败 {task['img_path']}: {e}")
                    res[task['T_no']][task['M_no']]['error'] = str(e)

                    completed_count += 1
                    if progress_callback and total_m_panels > 0:
                        progress = start_progress + (end_progress - start_progress) * completed_count / total_m_panels
                        progress_callback(int(progress), f"正在分析M版面：{completed_count}/{total_m_panels}")

        print("所有M版面分析完成！")
        print(f"M版面分析耗时: {time.time() - m_start_time:.2f}秒")

    return res


def analyze_t_regions(json_file, dm_results, progress_callback=None, start_progress=0, end_progress=100,
                      split_img_dir=None, max_workers=5):
    """
    分析所有T版面

    Args:
        json_file: JSON配置文件路径
        dm_results: D和M版面分析结果
        progress_callback: 进度回调函数，接收 (progress, stage) 参数
        split_img_dir: 分割图片目录路径

    Returns:
        dict: 最终的分析结果字典
    """
    T_prompt = get_prompt('T', 'analysis')

    res = dm_results.copy()
    t_start_time = time.time()

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if 'M1' in data['T0']:
            base_prompt = get_base_prompt('T', data['T0']['M1']['D1']['预置内容'])
        else:
            base_prompt = get_base_prompt('T', data['T0']['D1']['预置内容'])

        # 收集所有T版面任务
        t_tasks = []

        for T_no, T_item in data.items():
            if T_no == 'T0':
                continue  # 跳过T0版面
            img_path = f"{split_img_dir}/crop_{T_no}.png"

            if not os.path.exists(img_path):
                continue

            T_base_prompt = base_prompt + f"该版面所在的层级结构是：{data[T_no]['T级描述']}\n"

            # 准备M版面或D版面的图片和提示信息
            img_urls, img_prompts = [], []

            if 'M1' in T_item:
                # 有M版面的情况
                for M_no, M_item in res[T_no].items():
                    if M_item == {}:
                        continue

                    # if T_no == 'T1':
                    #     M_img_path = f"{split_img_dir}/rotated_{T_no}_{M_no}.png"
                    # else:
                    #     M_img_path = f"{split_img_dir}/crop_{T_no}_{M_no}.png"
                    M_img_path = f"{split_img_dir}/crop_{T_no}_{M_no}.png"

                    if os.path.exists(M_img_path):
                        img_urls.append(get_image_base64_with_mime(M_img_path, max_size_mb=9/len(res[T_no])))
                        img_prompt = get_image_description('M_panel',
                                                           panel_id=T_item[M_no]['M级区域描述'],
                                                           content_text=M_item.get('content_text', ''),
                                                           context_analysis=M_item.get('context_analysis', ''),
                                                           deficiency_detection=M_item.get('deficiency_detection', '')
                                                           )
                        img_prompts.append(img_prompt)
            # elif 'D1' in T_item:
            #     # 没有M版面的情况，直接处理D版面
            #     for D_no, D_item in res[T_no].items():
            #         if D_item == {}:
            #             continue

            #         D_img_path = f"{split_img_dir}/crop_{T_no}_{D_no}.png"

            #         if os.path.exists(D_img_path):
            #             img_urls.append(get_image_base64_with_mime(D_img_path))

            #             # 使用模板生成图片描述
            #             if 'format_evaluation' in D_item and 'confidence' in D_item:
            #                 img_prompt = get_image_description('D_panel_with_evaluation',
            #                                                    panel_id=T_item[D_no]['D级区域描述'],
            #                                                    content_text=D_item.get('content_text', ''),
            #                                                    otcl_analysis=D_item.get('otcl_analysis', ''),
            #                                                    format_evaluation=D_item['format_evaluation'],
            #                                                    confidence=D_item['confidence']
            #                                                    )
            #             else:
            #                 img_prompt = get_image_description('D_panel',
            #                                                    panel_id=T_item[D_no]['D级区域描述'],
            #                                                    content_text=D_item.get('content_text', ''),
            #                                                    otcl_analysis=D_item.get('otcl_analysis', '')
            #                                                    )

            #             img_prompts.append(img_prompt)

            if len(img_urls) > 0:  # 只有当有子版面图片时才添加T版面任务
                img_urls.append(get_image_base64_with_mime(img_path, max_size_mb=1))
                figure_prompt = get_panel_type_prompt('contains_m_panels')

                task_info = {
                    'T_no': T_no,
                    'img_path': img_path,
                    'base_prompt': T_base_prompt,
                    'figure_prompt': figure_prompt,
                    'T_prompt': T_prompt,
                    'img_urls': img_urls,
                    'img_prompts': img_prompts,
                    'T_item': T_item
                }
                t_tasks.append(task_info)

        total_t_panels = len(t_tasks)
        print(f"总共需要处理 {total_t_panels} 个T版面，使用{max_workers}个并发执行")

        if progress_callback:
            progress_callback(start_progress, f"正在分析T版面：0/{total_t_panels}")

        # 使用并发处理器并行处理T版面
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {executor.submit(analyze_t_panel, task): task for task in t_tasks}

            # 处理结果
            for future in as_completed(futures):
                task = futures[future]
                try:
                    T_no, result = future.result()
                    res[T_no].update(result)

                    completed_count += 1
                    print(f"已完成T版面分析: {task['img_path']} ({completed_count}/{total_t_panels})")

                    # 更新进度
                    if progress_callback and total_t_panels > 0:
                        progress = start_progress + (end_progress - start_progress) * completed_count / total_t_panels
                        progress_callback(int(progress), f"正在分析T版面：{completed_count}/{total_t_panels}")

                except Exception as e:
                    print(f"T版面任务执行失败 {task['img_path']}: {e}")
                    res[task['T_no']]['error'] = str(e)

                    completed_count += 1
                    if progress_callback and total_t_panels > 0:
                        progress = start_progress + (end_progress - start_progress) * completed_count / total_t_panels
                        progress_callback(int(progress), f"正在分析T版面：{completed_count}/{total_t_panels}")

        print("所有T版面（除T0）分析完成！")
        print(f"T版面（除T0）分析耗时: {time.time() - t_start_time:.2f}秒")

    return res


def analyze_t0_region(json_file, dmt_results, progress_callback=None, start_progress=0, end_progress=100,
                      split_img_dir=None, HL_suggestion=""):
    """
    分析整个DMT版面（T0）
    Args:
        json_file: JSON配置文件路径
        dmt_results: D、M和T版面分析结果
        progress_callback: 进度回调函数，接收 (progress, stage) 参数
        split_img_dir: 分割图片目录路径
        HL_suggestion: 红蓝卡标建议内容
    Returns:
        dict: 最终的DMT分析结果字典
    """
    T0_prompt = get_prompt('T0', 'analysis')
    res = dmt_results.copy()
    t0_start_time = time.time()
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if 'M1' in data['T0']:
            base_prompt = get_base_prompt('T0', data['T0']['M1']['D1']['预置内容'])
        else:
            base_prompt = get_base_prompt('T0', data['T0']['D1']['预置内容'])

        if '梯子火种·堤坝洪流筛分框架说明图' in base_prompt:
            T0_prompt += "你需要在底图层的分析中包含：包括：根据版面底色区分课设主题（黄色是“车联I”，蓝色是“车联II”，绿色是“纸联III“，紫色是“体联IV”），以及堤坝洪流意象感知（左堤坝、洪流、右堤坝、枢纽鱼嘴、枢纽飞沙堰、枢纽宝瓶口）。\n"
            T0_prompt += "你尤其要在手写层的分析中列举出**每周**的代码注释行数和对应的TA评分（5分制）。"
        if HL_suggestion != "":
            T0_prompt += f"\n\n请你参考以下建议来完善你的分析：{HL_suggestion}"

        # 准备T0版面的图片和提示信息
        img_path = f"{split_img_dir}/crop_T0.png"
        if not os.path.exists(img_path):
            print(f"T0版面图片不存在: {img_path}")
            return res


        img_urls, img_prompts = [], []
        # 准备T0版面的子版面图片和提示信息
        T_item = res['T0']
        if 'M1' in T_item:
            # 有M版面的情况
            for M_no, M_item in T_item.items():
                if M_item == {}:
                    continue
                for D_no, D_item in M_item.items():
                    if D_item == {}:
                        continue

                    D_img_path = f"{split_img_dir}/crop_T0_{M_no}_{D_no}.png"

                    if not os.path.exists(D_img_path):
                        continue
                    img_urls.append(get_image_base64_with_mime(D_img_path, max_size_mb=1))

                    # 使用模板生成图片描述
                    if 'format_evaluation' in D_item and 'confidence' in D_item:
                        img_prompt = get_image_description('D_panel_with_evaluation',
                                                            panel_id=T_item[M_no][D_no]['D级区域描述'],
                                                            content_text=D_item.get('content_text', ''),
                                                            otcl_analysis=D_item.get('otcl_analysis', ''),
                                                            format_evaluation=D_item['format_evaluation'],
                                                            confidence=D_item['confidence']
                                                            )
                    else:
                        img_prompt = get_image_description('D_panel',
                                                            panel_id=T_item[M_no][D_no]['D级区域描述'],
                                                            content_text=D_item.get('content_text', ''),
                                                            otcl_analysis=D_item.get('otcl_analysis', '')
                                                            )

                    img_prompts.append(img_prompt)
        else:
            for D_no, D_item in T_item.items():
                if D_item == {}:
                    continue

                D_img_path = f"{split_img_dir}/crop_T0_{D_no}.png"

                if not os.path.exists(D_img_path):
                    continue
                img_urls.append(get_image_base64_with_mime(D_img_path, max_size_mb=1))

                # 使用模板生成图片描述
                if 'format_evaluation' in D_item and 'confidence' in D_item:
                    img_prompt = get_image_description('D_panel_with_evaluation',
                                                        panel_id=T_item[D_no]['D级区域描述'],
                                                        content_text=D_item.get('content_text', ''),
                                                        otcl_analysis=D_item.get('otcl_analysis', ''),
                                                        format_evaluation=D_item['format_evaluation'],
                                                        confidence=D_item['confidence']
                                                        )
                else:
                    img_prompt = get_image_description('D_panel',
                                                        panel_id=T_item[D_no]['D级区域描述'],
                                                        content_text=D_item.get('content_text', ''),
                                                        otcl_analysis=D_item.get('otcl_analysis', '')
                                                        )

                img_prompts.append(img_prompt)
        # 准备其他T版面的图片和提示信息
        for T_no, T_item in res.items():
            if T_no == 'T0':
                continue
            # else:
            T_img_path = f"{split_img_dir}/crop_{T_no}.png"
            if not os.path.exists(T_img_path):
                continue
            img_urls.append(get_image_base64_with_mime(T_img_path, max_size_mb=1))
            # 将T_item转字符串
            contained_panels_info = str(T_item)
            contained_panels_info = contained_panels_info.replace('content_text', '具体内容') \
                .replace('otcl_analysis', 'OTCL分析').replace('abnormality_eval', '异常评估') \
                .replace('format_evaluation', '书写规范').replace('confidence', '手写识别置信度') \
                .replace('context_analysis', '裂变分析').replace('deficiency_detection', '聚变分析')

            img_prompt = get_image_description('T_panel',
                                            panel_id=T_item['T级描述'],
                                            contained_panels_info=contained_panels_info
                                            )
            img_prompts.append(img_prompt)
        img_urls.append(get_image_base64_with_mime(img_path))
        figure_prompt = get_panel_type_prompt('contains_t_panels')

        # 只有一个T0版面，添加超时处理机制
        if progress_callback:
            progress_callback(start_progress, f"正在分析T0版面：0/1")
        from concurrent.futures import ThreadPoolExecutor, TimeoutError

        def call_gemini_api():
            """调用Gemini API的函数"""
            return gemini_api.generate(
                image_urls=img_urls,
                user_prompt=base_prompt + figure_prompt + T0_prompt,
                image_prompts=img_prompts
            )

        def call_qwen_api():
            """调用Qwen API的函数"""
            return qwen_vl_api.generate(
                image_urls=img_urls,
                user_prompt=base_prompt + figure_prompt + T0_prompt,
                image_prompts=img_prompts
            )

        # 尝试使用Gemini API，设置超时处理机制
        try:
            print("正在调用Gemini API进行T0版面分析...")
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_gemini_api)
                try:
                    final_explanation = future.result(timeout=150)  # 2分30秒超时
                    print("Gemini API调用成功")

                    # 提取<think></think>标签外的内容
                    # 使用正则表达式移除<think>...</think>标签及其内容
                    final_explanation = re.sub(r'<think>.*?</think>', '', final_explanation, flags=re.DOTALL)
                    # 清理多余的空行和空格
                    final_explanation = re.sub(r'\n\s*\n', '\n', final_explanation.strip())
                    # 移除Gemini的提示信息
                    if '温馨提示：如要解锁所有应用的完整功能' in final_explanation:
                        final_explanation = final_explanation[:final_explanation.find('温馨提示：如要解锁所有应用的完整功能')].strip()

                    result = {
                        'final_explanation': final_explanation,
                        'T级描述': data['T0']['T级描述'],
                    }
                    res['T0'].update(result)
                    print(f"T0版面分析结果: {result}")

                except TimeoutError:
                    print("Gemini API调用超时（3分钟），切换到备用的Qwen API...")
                    raise Exception("Gemini API超时")

        except Exception as e:
            print(f"Gemini API调用失败: {e}")
            # 调用qwen_vl_api作为备用
            try:
                print("正在调用备用的Qwen API进行T0版面分析...")
                final_explanation = call_qwen_api()
                print("Qwen API调用成功")

                result = {
                    'final_explanation': final_explanation,
                    'T级描述': data['T0']['T级描述'],
                }
                res['T0'].update(result)
                print(f"T0版面分析结果（备用API）: {result}")

            except Exception as backup_e:
                print(f"备用处理T0版面 {img_path} 时发生错误: {backup_e}")
                result = {"error": str(backup_e), "content": "无法生成T0版面分析结果"}
                res['T0']['error'] = result

        if progress_callback:
            progress = start_progress + (end_progress - start_progress)
            progress_callback(int(progress), "正在分析T0版面：1/1")
        print("T0版面分析完成！")
        print(f"T0版面分析耗时: {time.time() - t0_start_time:.2f}秒")
        return res


def analyze_dmt_region(img_path, file_path, json_file, split_img_dir, output_file, progress_callback=None):
    """
    完整的DMT版面分析函数
    按D->M->T的顺序进行层级分析

    Args:
        img_path: 梯子图图片路径
        file_path: Excel配置文件路径
        json_file: JSON配置文件路径
        split_img_dir: 分割图片输出目录
        output_file: 输出结果文件路径
        progress_callback: 进度回调函数，接收 (progress, stage) 参数

    Returns:
        dict: 完整的DMT分析结果
    """
    # 设置全局输出目录以供其他函数使用
    # global CURRENT_SPLIT_IMG_DIR # 移除全局变量，避免并发竞争条件
    # CURRENT_SPLIT_IMG_DIR = split_img_dir # 移除全局变量，避免并发竞争条件

    if progress_callback:
        progress_callback(10, "提取Excel数据到JSON")

    # 提取Excel数据到JSON
    extract_excel_to_json(file_path, json_file)

    if progress_callback:
        progress_callback(20, "正在分割图片...")

    # 分割图片
    batch_crop_images_from_json(
        json_file=json_file,
        img_path=img_path,
        output_dir=split_img_dir,
    )
    total_start_time = time.time()
    print("开始DMT版面分析...")

    # 1. 分析D版面（底层）
    print("\n=== 第一阶段：分析D版面 ===")
    if progress_callback:
        progress_callback(30, "开始分析D版面...")

    d_results = analyze_d_regions(json_file, progress_callback, 30, 60, split_img_dir, max_workers=5)

    # 保存D版面结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(d_results, f, ensure_ascii=False, indent=4)
        print(f"D版面结果已保存到 {output_file}")

    # 2. 分析M版面（中间层）
    print("\n=== 第二阶段：分析M版面 ===")
    if progress_callback:
        progress_callback(60, "开始分析M版面...")

    dm_results = analyze_m_regions(json_file, d_results, progress_callback, 60, 80, split_img_dir, max_workers=5)

    # 保存DM版面结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(dm_results, f, ensure_ascii=False, indent=4)
        print(f"DM版面结果已保存到 {output_file}")

    # 3. 分析T版面（顶层）
    print("\n=== 第三阶段：分析T版面 ===")
    if progress_callback:
        progress_callback(80, "开始分析T版面...")

    dmt_results = analyze_t_regions(json_file, dm_results, progress_callback, 80, 90, split_img_dir, max_workers=5)

    # 4. 分析整个DMT版面（最终结果）
    print("\n=== 第四阶段：分析整个DMT版面 ===")
    if progress_callback:
        progress_callback(90, "开始分析T0版面...")
    final_results = analyze_t0_region(json_file, dmt_results, progress_callback, 90, 95, split_img_dir)

    # 保存最终结果
    if progress_callback:
        progress_callback(95, "保存最终结果...")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=4)
        print(f"最终结果已保存到 {output_file}")

    print(f"整体DMT分析耗时: {time.time() - total_start_time:.2f}秒")

    if progress_callback:
        progress_callback(100, "DMT分析完成")

    return final_results


def reanalyze_dmt_region(json_file, split_img_dir, output_file, HL_suggestion="", progress_callback=None):
    """
    重新分析DMT版面，使用新的分割图片目录

    Args:
        img_path: 梯子图图片路径
        file_path: Excel配置文件路径
        json_file: JSON配置文件路径
        split_img_dir: 分割图片输出目录
        output_file: 输出结果文件路径
        card_score_threshold: 红蓝卡标闭环控制阈值
        HL_suggestion: 红蓝卡标建议内容
        progress_callback: 进度回调函数，接收 (progress, stage) 参数

    Returns:
        dict: 完整的DMT分析结果
    """
    total_start_time = time.time()
    with open(output_file, 'r', encoding='utf-8') as f:
        dmt_results = json.load(f)

    if progress_callback:
        progress_callback(0, "重新分析DMT版面...")
    final_results = analyze_t0_region(json_file, dmt_results, progress_callback, 0, 95, split_img_dir, HL_suggestion)

    # 保存最终结果
    if progress_callback:
        progress_callback(95, "保存最终结果...")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=4)
        print(f"最终结果已保存到 {output_file}")

    print(f"重新分析DMT版面耗时: {time.time() - total_start_time:.2f}秒")

    if progress_callback:
        progress_callback(100, "DMT重新分析完成")

    return final_results
