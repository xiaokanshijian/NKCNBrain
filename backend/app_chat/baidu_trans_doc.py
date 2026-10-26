from nkcn_public_config import secret
import base64
import hashlib
import hmac
import json
import os
import threading
import time
import requests
import urllib
from collections import OrderedDict

from llm_langchain.pdf_ocr_utils import extract_and_save_images_from_ocr

# 🔥 语言检测相关导入
try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    print("警告：langdetect库未安装，将使用简单的字符检测方法")

class Translate:
    def __init__(self):
        self.appid = secret("BAIDU_TRANS_APPID")
        self.seckey = secret("BAIDU_TRANS_SECKEY")

    def _require_credentials(self):
        # Missing optional translation configuration must not break Django startup.
        if not self.appid or not self.seckey:
            raise ValueError("Baidu document translation requires BAIDU_TRANS_APPID and BAIDU_TRANS_SECKEY")

    def create_quote_job(self, from_lang, to_lang, extend, file_name, file_path):
        self._require_credentials()
        url = 'https://fanyi-api.baidu.com/transapi/doctrans/createjob/quote'
        with open(file_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        input_data = {
            'from': from_lang,
            'to': to_lang,
            'input': {
                'content': content,
                'format': extend,
                'filename': file_name
            }
        }
        timestamp = int(time.time())
        sign = self.create_sign(timestamp, input_data)
        headers = self.create_headers(timestamp, sign)
        response = requests.post(url, headers=headers, json=input_data)
        return response.text

    def query_quote(self, file_id):
        self._require_credentials()
        url = 'https://fanyi-api.baidu.com/transapi/doctrans/query/quote'
        input_data = {'fileId': file_id}
        timestamp = int(time.time())
        sign = self.create_sign(timestamp, input_data)
        headers = self.create_headers(timestamp, sign)
        response = requests.post(url, headers=headers, json=input_data)
        return response.text

    def create_trans_job(self, from_lang, to_lang, extend, file_name, file_path, output=''):
        self._require_credentials()
        url = 'https://fanyi-api.baidu.com/transapi/doctrans/createjob/trans'
        with open(file_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        input_data = {
            'from': from_lang,
            'to': to_lang,
            'input': {
                'content': content,
                'format': extend,
                'filename': file_name
            },
            'output': {
                'format': output
            }
        }
        timestamp = int(time.time())
        sign = self.create_sign(timestamp, input_data)
        headers = self.create_headers(timestamp, sign)
        response = requests.post(url, headers=headers, json=input_data)
        return response.text

    def query_trans(self, request_id):
        self._require_credentials()
        url = 'https://fanyi-api.baidu.com/transapi/doctrans/query/trans'
        input_data = {'requestId': request_id}
        timestamp = int(time.time())
        sign = self.create_sign(timestamp, input_data)
        headers = self.create_headers(timestamp, sign)
        response = requests.post(url, headers=headers, json=input_data)
        return response.text

    def create_sign(self, timestamp, input_data):
        self._require_credentials()
        query_str = json.dumps(input_data)
        sign_str = '{}{}{}'.format(self.appid, timestamp, query_str)
        sign = base64.b64encode(hmac.new(self.seckey.encode('utf-8'), sign_str.encode('utf-8'), digestmod=hashlib.sha256).digest())
        return sign

    def create_headers(self, timestamp, sign):
        return {
            'Content-Type': 'application/json',
            'X-Appid': self.appid,
            'X-Sign': sign,
            'X-Timestamp': str(timestamp),
        }

    def url_encoder(self, params):
        return urllib.parse.urlencode(params)


from_lang = 'en'
to_lang = 'zh'
extend = 'pdf'
output = 'pdf'


# 🔥 检测PDF文档的语言
def detect_pdf_language(file_path):
    """
    检测PDF文档的语言
    返回: 'zh' (中文) 或 'en' (英文)
    如果检测失败，默认返回 'en'
    """
    try:
        # 使用PyPDF2提取PDF文本
        # 🔥 修复：PyPDF2 3.0.0+ 使用 PdfReader 替代已废弃的 PdfFileReader
        try:
            # 尝试使用新版本 API (PyPDF2 >= 3.0.0)
            from PyPDF2 import PdfReader
            use_new_api = True
        except ImportError:
            # 兼容旧版本 PyPDF2 (< 3.0.0)
            try:
                from PyPDF2 import PdfFileReader as PdfReader
                use_new_api = False
            except ImportError:
                print("无法导入PyPDF2，语言检测将使用默认值")
                return 'en'

        with open(file_path, "rb") as file:
            pdf = PdfReader(file)
            content = ""

            # 根据PyPDF2版本选择不同的API
            if use_new_api:
                # PyPDF2 3.0.0+ 新API
                num_pages = min(len(pdf.pages), 5)  # 只检测前5页以提高速度
                for i in range(num_pages):
                    try:
                        page = pdf.pages[i]
                        extracted_text = page.extract_text()
                        content += extracted_text + "\n"
                    except:
                        continue
            else:
                # PyPDF2 < 3.0.0 旧API
                num_pages = min(pdf.getNumPages(), 5)  # 只检测前5页以提高速度
                for i in range(num_pages):
                    try:
                        extracted_text = pdf.getPage(i).extractText()
                        content += extracted_text + "\n"
                    except:
                        continue

        if not content.strip():
            print("无法从PDF提取文本，默认使用英文")
            return 'en'

        # 使用langdetect库检测语言
        # if LANGDETECT_AVAILABLE:
        #     try:
        #         detected_lang = detect(content)
        #         print(f"检测到的语言: {detected_lang}")
        #         if detected_lang.startswith('zh'):
        #             return 'zh'
        #         else:
        #             return 'en'
        #     except LangDetectException:
        #         print("langdetect检测失败，使用字符检测方法")

        # 简单的字符检测方法（备用）
        # 如果中文字符比例超过30%，认为是中文
        chinese_char_count = sum(1 for char in content if '\u4e00' <= char <= '\u9fff')
        total_char_count = len([c for c in content if c.isalpha()])

        if total_char_count > 0:
            chinese_ratio = chinese_char_count / total_char_count
            print(f"中文字符比例: {chinese_ratio:.2%}")
            if chinese_ratio > 0.3:
                return 'zh'

        return 'en'
    except Exception as e:
        print(f"语言检测出错: {e}，默认使用英文")
        return 'en'
# 下面这些都要随文件请求不同而更改；前面的暂时不用变，因为暂无别的需求
file_path = './测试.pdf'
file_name = 'ceshi.pdf'
# 下面这两个是之前所有翻译请求都只能串行，只要当前任务没结束，所有请求都自动拒绝，无并发，改并发之后不用了
# (此API默认最大并发量为5，扩充需邮箱联系管理，API文档网址https://api.fanyi.baidu.com/product/151)
# request_id = 3651137
# isFail = False
translation_requests = {}


trans_obj = Translate()

# 创建报价服务
# quote_ret = trans_obj.create_quote_job(from_lang, to_lang, extend, file_name, file_path)
# print(quote_ret)

# 查询报价结果
# file_id = '71d969e04f62cac86d7d16f6cc6b9413'
# query_quote_ret = trans_obj.query_quote(file_id)
# print(query_quote_ret)

# 创建翻译服务
def translate(fileName, filePath, new_pdf_path, request_key):
    # 🔥 检查文件是否存在，如果存在也需要检测是否是错误的中译中文档
    if os.path.exists(new_pdf_path):
        # 检测原文档和翻译文档的语言
        original_lang = detect_pdf_language(filePath)
        translated_lang = detect_pdf_language(new_pdf_path)

        if original_lang == 'zh' and translated_lang == 'zh':
            # 原文档是中文，翻译文档也是中文（中译中错误），删除翻译文档并重新翻译
            print(f"[translate] 检测到错误翻译：原文档({original_lang})和翻译文档({translated_lang})都是中文，删除并重新翻译")
            try:
                os.remove(new_pdf_path)
                print(f"[translate] 已删除错误的翻译文档: {new_pdf_path}")
            except Exception as e:
                print(f"[translate] 删除翻译文档失败: {e}")
                return  # 如果删除失败，不继续翻译

        if os.path.exists(new_pdf_path):
            # 翻译文档存在且正确，不需要重新翻译
            print(f"此文件的译文pdf已存在且正确，不需要再重复提交翻译请求浪费钱: {new_pdf_path}")
            return

    # 翻译文档不存在或已被删除，继续翻译流程
    print(f"此文件的译文pdf还不存在或已被删除，准备翻译: {new_pdf_path}")

    # 🔥 检查是否已有正在进行的翻译任务
    global translation_requests
    if request_key in translation_requests:
        translation_request = translation_requests[request_key]
        if not translation_request.get('isFail', False):
            # 任务正在进行中（未失败），不重复提交
            print(f"翻译任务已在进行中，不重复提交: request_key={request_key}, request_id={translation_request.get('request_id')}")
            return
        else:
            # 任务之前失败了，可以重新翻译
            print(f"之前的翻译任务失败，准备重新翻译: request_key={request_key}")

    # 🔥 新增：判断是否为扫描件，如果是，先进行OCR处理（优先复用已有OCR结果）
    actual_file_to_translate = filePath

    try:
        # 导入OCR工具
        import sys
        import os as os_module
        sys.path.append(os_module.path.dirname(os_module.path.dirname(os_module.path.abspath(__file__))))
        from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word, run_remote_ocr, md_to_pdf
        from llm_langchain import global_var

        # 准备目录路径
        file_dir = os_module.path.dirname(filePath)
        file_base = os_module.path.splitext(os_module.path.basename(filePath))[0]

        # 🔥 优化：优先检查上传时生成的OCR结果（document_ocr目录）
        upload_ocr_dir = os_module.path.join(file_dir, f"{file_base}_ocr")
        upload_md_path = os_module.path.join(upload_ocr_dir, f"{file_base}_ocr.md")
        upload_txt_path = os_module.path.join(upload_ocr_dir, f"{file_base}_raw.txt")
        upload_converted_pdf = os_module.path.join(upload_ocr_dir, f"{file_base}_converted.pdf")
        converted_pdf_path = upload_converted_pdf  # 默认转换后的PDF路径

        # 🔥 检测PDF类型：使用新方法 check_pdf_type_by_word 并配合缓存机制
        # 构建缓存键（从完整路径中提取 username/bookname 结构）
        path_parts = filePath.replace('\\', '/').split('/')
        # 查找 received_dir 后的路径部分作为缓存键
        try:
            received_idx = path_parts.index('received_dir')
            # received_dir/username/bookname/filename.pdf -> username/bookname/filename.pdf
            file_key = '/'.join(path_parts[received_idx+1:]) if received_idx < len(path_parts)-1 else f"unknown/{file_base}.pdf"
        except ValueError:
            # 如果路径中没有 received_dir，使用文件名
            file_key = f"unknown/{file_base}.pdf"

        cached_type = global_var.get_pdf_type(file_key)

        if cached_type is None:
            # 未缓存，使用新方法检测
            print(f"[translate] 对PDF进行精确扫描件检测: {file_key}")
            pdf_type = check_pdf_type_by_word(filePath)
            global_var.set_pdf_type(file_key, pdf_type)
            print(f"[translate] 检测结果: {pdf_type}")
        else:
            # 已缓存，直接使用
            print(f"[translate] 使用缓存的检测结果: {cached_type}")
            pdf_type = cached_type

        is_scanned = (pdf_type == 'scanned')

        if is_scanned:
            print(f"[translate] 检测到原文档是扫描件，进行OCR处理...")

            # 检查是否已有OCR结果
            if (os_module.path.exists(upload_md_path) and
                os_module.path.exists(upload_converted_pdf) and
                os_module.path.exists(upload_txt_path)):
                print(f"[translate] 发现已有OCR结果，直接复用: {upload_ocr_dir}")
                print(f"[translate] 复用转换后的PDF: {upload_converted_pdf}")
                actual_file_to_translate = upload_converted_pdf
                converted_pdf_path = upload_converted_pdf
            elif os_module.path.exists(upload_md_path) and os_module.path.exists(upload_txt_path):
                print(f"[translate] 发现已有OCR文本结果，复用Markdown并转换为PDF...")
                # markdown转PDF
                converted_pdf_path = os_module.path.join(upload_ocr_dir, f"{file_base}_converted.pdf")
                conversion_success = md_to_pdf(upload_md_path, converted_pdf_path)

                if conversion_success and os_module.path.exists(converted_pdf_path):
                    print(f"[translate] 扫描件已转换为可处理的PDF: {converted_pdf_path}")
                    actual_file_to_translate = converted_pdf_path
                else:
                    print(f"[translate] Markdown转PDF失败，使用原始扫描件进行翻译")
            else:
                # 没有现成的OCR结果，需要重新OCR
                print(f"[translate] 未找到已有OCR结果，开始新的OCR处理...")

                # 使用统一的OCR目录（不再区分_ocr和_ocr_for_translation）
                ocr_dir = upload_ocr_dir  # 统一使用 document_ocr 目录

                # 执行OCR
                ocr_success, md_path, txt_path = run_remote_ocr(filePath, ocr_dir)

                if ocr_success and md_path:
                    print("[translate] OCR成功，开始提取并保存图片...")
                    image_dir = os_module.path.join(file_dir, f"{file_base}_image")
                    extract_success, image_count, image_output_dir = extract_and_save_images_from_ocr(
                        filePath, txt_path, image_dir
                    )

                    if extract_success:
                        print(f"[translate] 图片提取成功，共保存 {image_count} 张图片到: {image_output_dir}")
                    else:
                        print("[translate] 图片提取失败")

                    print(f"[translate] OCR处理成功，将markdown转换为PDF...")

                    # markdown转PDF
                    converted_pdf_path = os_module.path.join(ocr_dir, f"{file_base}_converted.pdf")
                    conversion_success = md_to_pdf(md_path, converted_pdf_path)

                    if conversion_success and os_module.path.exists(converted_pdf_path):
                        print(f"[translate] 扫描件已转换为可处理的PDF: {converted_pdf_path}")
                        actual_file_to_translate = converted_pdf_path
                    else:
                        print(f"[translate] Markdown转PDF失败，使用原始扫描件进行翻译")
                else:
                    print(f"[translate] OCR处理失败，使用原始扫描件进行翻译")
        else:
            print(f"[translate] 原文档是数字原生PDF，直接翻译")

    except Exception as e:
        print(f"[translate] 扫描件检测/处理失败: {e}，使用原始文档进行翻译")

    # 🔥 检测PDF文档的语言，自动设置翻译方向
    detected_from_lang = detect_pdf_language(
        converted_pdf_path if converted_pdf_path and os_module.path.exists(converted_pdf_path)
        else filePath
    )
    if detected_from_lang == 'zh':
        # 如果是中文，翻译成英文
        actual_from_lang = 'zh'
        actual_to_lang = 'en'
        print(f"检测到文档为中文，翻译方向：中文 -> 英文")
    else:
        # 如果是英文（或检测失败），翻译成中文
        actual_from_lang = 'en'
        actual_to_lang = 'zh'
        print(f"检测到文档为英文（或默认），翻译方向：英文 -> 中文")

    global file_path, file_name
    file_path = actual_file_to_translate  # 🔥 使用处理后的文件
    file_name = fileName
    print(f"翻译任务开始：{file_path}: {file_name}-------------")
    trans_ret = trans_obj.create_trans_job(actual_from_lang, actual_to_lang, extend, file_name, file_path, output)
    print(trans_ret)
    # 将 JSON 字符串解析为 Python 字典, 提取 requestId 字段并更新，便于之后查询
    data = json.loads(trans_ret)
    request_id = data.get('data', {}).get('requestId')

    # 🔥 创建翻译请求项（此时确认没有正在进行的任务）
    translating_item = {
        "request_id": request_id,
        "isFail": False,
        "original_file_path": filePath,  # 保存原始文件路径
        "target_pdf_path": new_pdf_path,  # 保存目标翻译文件路径
        "converted_pdf_path": converted_pdf_path,  # 保存转换后的PDF路径
        "ocr_attempted": converted_pdf_path is not None,  # 是否已尝试OCR转换
        "retry_count": translation_requests.get(request_key, {}).get('retry_count', 0) + 1  # 重试次数递增
    }
    translation_requests[request_key] = translating_item

    # 启动一个线程来定期查询翻译结果
    threading.Thread(target=check, args=(new_pdf_path, request_key), daemon=True).start()


# 查询翻译结果
def check(new_pdf_path, request_key):
    while True:
        request_id = 0  # 随便初始化一个序号int
        global translation_requests
        if request_key in translation_requests:
            translation_request = translation_requests[request_key]
            request_id = translation_request.get('request_id', 0)
        query_trans_ret = trans_obj.query_trans(request_id)
        print("查询翻译进度：-------------")
        print(query_trans_ret)
        # 将 JSON 字符串解析为 Python 字典，提取 fileSrcUrl 字段，即翻译译文pdf文件下载地址
        data = json.loads(query_trans_ret)
        if data.get('code') != 0:
            print(f"查询翻译进度失败，错误信息：{data.get('msg')}")
        trans_data = data.get('data', {})
        if trans_data and trans_data != {}:
            file_src_url = trans_data.get('fileSrcUrl')
            status = trans_data.get('status')
        else:
            status = 2

        isEnd = False
        if request_key in translation_requests:
            translation_request = translation_requests[request_key]
            if status == 0:
                print("正在翻译中")
                translation_request['isFail'] = False
            elif status == 2:
                print("翻译失败了，可能是没钱了")
                translation_request['isFail'] = True
                isEnd = True  # 退出循环
            else:
                print("翻译完成，准备下载译文pdf")
                # 指定下载路径为传入的new_pdf_path
                try:
                    response = requests.get(file_src_url, stream=True)
                    response.raise_for_status()  # 检查请求是否成功
                    with open(new_pdf_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"译文pdf下载到了 {new_pdf_path}")
                    translation_request['isFail'] = False
                    isEnd = True  # 退出循环
                except requests.RequestException as e:
                    print(f"译文pdf下载失败: {e}")
                    translation_request['isFail'] = True
                    isEnd = True  # 退出循环
                break

        if isEnd == True:
            break
        # 每10秒查询一次
        time.sleep(10)


def check_for_single(request_key):
    isTranslating = False
    if request_key in translation_requests:
        isTranslating = True
    return isTranslating
    # query_trans_ret = trans_obj.query_trans(request_id)
    # print("查询翻译进度：-------------")
    # print(query_trans_ret)
    # # 将 JSON 字符串解析为 Python 字典，提取 fileSrcUrl 字段，即翻译译文pdf文件下载地址
    # data = json.loads(query_trans_ret)
    # status = data.get('data', {}).get('status')
    #
    # if status == 0:
    #     return False
    # elif status == 2:
    #     return True
    # else:
    #     return True