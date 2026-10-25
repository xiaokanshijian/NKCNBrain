import nkcn_public_config as _public_config
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

@app.route('/invoke_rate', methods=['POST'])
def invoke_rate():
    # 获取POST请求中的JSON数据
    data = request.json
    username = data.get('username')
    text = data.get('text')

    text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\r\n', '\\r\\n')

    # 构造要发送的数据
    formData = {
        'username': username,
        'message': text
    }

    # 发送POST请求到192.0.2.1的8000端口
    try:
        response = requests.post(_public_config.endpoint('NKCN_SERVICE_8000_API_INVOKE_RATE_URL', 'http://localhost:8000/api/invoke_rate/'), data=formData)
        response.raise_for_status()  # 如果请求返回了一个错误状态码，这会抛出一个异常
        print("成功！")
        print(jsonify(response.text))
        # 返回响应内容
        return jsonify(response.text)
    except requests.RequestException as e:
        # 处理请求异常
        print("出错")
        print(str(e))
        return jsonify({'error': str(e)}), 400


@app.route('/invoke_rate_stream', methods=['POST'])
def invoke_rate_stream():
    # 获取POST请求中的JSON数据
    data = request.json
    username = data.get('username')
    text = data.get('text')  # GCS输入
    text_for_d = data.get('text_for_d', text)  # D输入（新增，默认与GCS相同）
    add_mode = data.get('add_mode', '')  # 获取评估模式参数
    include_d_part = data.get('include_d_part', True)  # 获取D部分参数，默认为True
    gcs_content_mode = data.get('gcs_content_mode', 'simple_reason')  # GCS内容模式
    d_content_mode = data.get('d_content_mode', 'inspire_framework')  # D内容模式
    
    # 处理换行符
    text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\r\n', '\\r\\n')
    text_for_d = text_for_d.replace('\n', '\\n').replace('\r', '\\r').replace('\r\n', '\\r\\n')
    
    # 构造要发送的数据
    formData = {
        'username': username,
        'message': text,  # GCS输入
        'message_for_d': text_for_d,  # D输入（新增）
        'add_mode': add_mode,  # 传递评估模式参数
        'include_d_part': str(include_d_part).lower(),  # 传递D部分参数
        'gcs_content_mode': gcs_content_mode,  # 传递GCS内容模式
        'd_content_mode': d_content_mode  # 传递D内容模式
    }
    
    def generate():
        try:
            # 使用stream=True参数来获取流式响应
            response = requests.post(
                _public_config.endpoint('NKCN_SERVICE_8000_API_INVOKE_RATE_STREAM_URL', 'http://localhost:8000/api/invoke_rate_stream/'), 
                data=formData,
                stream=True
            )
            
            # 直接传递流式响应
            for chunk in response.iter_lines():
                if chunk:
                    yield chunk.decode('utf-8') + '\n'
            
        except requests.RequestException as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    # 返回一个流式响应
    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream"
    )


@app.route('/model_switch', methods=['POST'])
def model_switch():
    # 获取POST请求中的JSON数据
    data = request.json
    username = data.get('username')
    model_id = data.get('model_id')

    # 构造要发送的数据
    formData = {
        'username': username,
        'model_id': model_id
    }

    # 发送POST请求到192.0.2.1的8000端口
    try:
        response = requests.post(_public_config.endpoint('NKCN_SERVICE_8000_API_MODEL_SWITCH_URL', 'http://localhost:8000/api/model_switch/'), data=formData)
        response.raise_for_status()
        print("成功！")
        print(jsonify(response.text))
        # 返回响应内容
        return jsonify(response.text)
    except requests.exceptions.RequestException as e:
        print("出错")
        print(str(e))
        return jsonify({'error': str(e)}), 400


@app.route('/assess_document_confidence', methods=['POST'])
def assess_document_confidence():
    """文档置信度评估API"""
    # 获取POST请求中的JSON数据
    data = request.json
    user_name = data.get('user_name')
    document_content = data.get('document_content')
    
    print(f"[中转服务器] 收到文档置信度评估请求，user_name: {user_name}, content长度: {len(document_content) if document_content else 0}")

    # 构造要发送的数据（使用表单数据格式，与其他API保持一致）
    formData = {
        'user_name': user_name,
        'document_content': document_content
    }

    # 发送POST请求到192.0.2.1的8000端口（使用data参数发送表单数据）
    try:
        print(f"[中转服务器] 转发到8卡服务器: http://127.0.0.1:8000/api/assess_document_confidence/")
        response = requests.post(_public_config.endpoint('NKCN_SERVICE_8000_API_ASSESS_DOCUMENT_CONFIDENCE_URL', 'http://localhost:8000/api/assess_document_confidence/'), data=formData, timeout=30)
        response.raise_for_status()
        print(f"[中转服务器] 8卡服务器响应状态: {response.status_code}")
        print(f"[中转服务器] 8卡服务器响应内容: {response.text[:200]}")
        print("文档置信度评估成功！")
        
        # 返回8卡服务器的响应（与其他API保持一致）
        return jsonify(response.text)
    except requests.exceptions.RequestException as e:
        print(f"[中转服务器] 文档置信度评估出错: {str(e)}")
        return jsonify({'error': str(e)}), 400


@app.route('/get_depth_suggestion', methods=['POST'])
def get_depth_suggestion():
    """深度建议生成接口"""
    try:
        # 获取POST请求中的JSON数据
        data = request.json
        input_text = data.get('input_text', '')
        user_name = data.get('user_name', 'default_user')
        task_type = data.get('task_type', 'qa')  # 新增参数
        
        if not input_text:
            return jsonify({'error': '输入文本不能为空'}), 400
        
        # 构造要发送的数据
        formData = {
            'input_text': input_text,
            'user_name': user_name,
            'task_type': task_type  # 传递task_type参数
        }
        
        # 发送POST请求到8卡服务器
        response = requests.post(_public_config.endpoint('NKCN_SERVICE_8000_API_GET_DEPTH_SUGGESTION_URL', 'http://localhost:8000/api/get_depth_suggestion/'), data=formData)
        response.raise_for_status()
        
        # 解析响应
        result = response.json()
        
        return jsonify(result)
        
    except requests.RequestException as e:
        print(f"[中转服务器] 深度建议请求失败: {str(e)}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f"[中转服务器] 深度建议处理异常: {str(e)}")
        return jsonify({'error': str(e)}), 500
    

@app.route('/upload_file', methods=['POST'])
def upload_file():
    """
    文件上传中转接口
    功能：接收外部文件流，直接转发给内网Django服务器
    """
    try:
        # 1. 校验文件是否存在
        if 'file' not in request.files:
            return jsonify({'error': '未找到上传的文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '文件名为空'}), 400

        # 2. 获取附加数据（如用户名、任务ID等）
        username = request.form.get('username', 'unknown')
        
        print(f"[中转服务器] 收到文件: {file.filename} (用户: {username})，准备转发...")

        # 3. 构造转发请求
        # 关键点：使用 files 参数传递文件对象
        # 格式: '字段名': (文件名, 文件流, MIME类型)
        files_to_send = {
            'file': (file.filename, file.stream, file.content_type)
        }
        
        data_to_send = {
            'username': username
        }

        # 4. 转发给内网 Django 服务器
        # 假设 Django 的接收路由是 /api/receive_file/
        target_url = _public_config.endpoint('NKCN_SERVICE_8000_API_RECEIVE_FILE_URL', 'http://localhost:8000/api/receive_file/')
        
        response = requests.post(
            target_url, 
            files=files_to_send, 
            data=data_to_send,
            timeout=300  # 文件上传可能较慢，设置较长的超时时间
        )
        
        # 检查响应状态
        response.raise_for_status()
        
        print("[中转服务器] 文件转发成功")
        # 返回 Django 的响应结果
        return jsonify(response.json())

    except requests.RequestException as e:
        print(f"[中转服务器] 转发异常: {str(e)}")
        return jsonify({'error': f'转发失败: {str(e)}'}), 500
    except Exception as e:
        print(f"[中转服务器] 处理异常: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/ocr_forward', methods=['POST'])
def ocr_forward():
    """OCR 专用透传接口"""
    try:
        # 1. 检查文件
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        
        #根据调用方 IP 决定 ocr model:127.0.0.1 传 0CR2，其他传 OCRclient ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if isinstance(client_ip, str)and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        ocr_model ='OCR2' if client_ip =='127.0.0.1' else 'OCR'
        
        # 2. 准备转发
        files = {
            'file': (file.filename, file.stream, file.content_type)
        }
        data = {'ocr_model': ocr_model}
        
        print(f"[中转] 收到OCR请求: {file.filename}，正在转发到算力服务器...")

        # 3. 发送给内网算力服务器
        # 注意：timeout 设置为 600秒 (10分钟)，因为 OCR 很慢
        response = requests.post(
            _public_config.endpoint('NKCN_SERVICE_8000_API_PROCESS_OCR_DOCUMENT_URL', 'http://localhost:8000/api/process_ocr_document/'), 
            files=files,
            data=data,
            timeout=600 
        )
        
        # 4. 检查并返回结果
        response.raise_for_status()
        print("[中转] OCR处理完成，正在返回结果")
        
        # 直接返回算力服务器的 JSON 数据
        return jsonify(response.json())

    except requests.exceptions.ReadTimeout:
        print("[中转] OCR请求超时")
        return jsonify({'error': 'OCR processing timed out'}), 504
    except Exception as e:
        print(f"[中转] 异常: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
