import nkcn_public_config as _public_config
# -*- coding:utf-8 -*-
#
#   author: iflytek
#
#  本demo测试时运行的环境为：Windows + Python3.7
#  本demo测试成功运行时所安装的第三方库及其版本如下：
#   cffi==1.12.3
#   gevent==1.4.0
#   greenlet==0.4.15
#   pycparser==2.19
#   six==1.12.0
#   websocket==0.2.1
#   websocket-client==0.56.0
#   合成小语种需要传输小语种文本、使用小语种发音人vcn、tte=unicode以及修改文本编码方式
#  错误码链接：https://www.xfyun.cn/document/error-code （code返回错误码时必看）
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
import websocket
import datetime
import hashlib
import base64
import hmac
import json
from urllib.parse import urlencode
import time
import ssl
import subprocess
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
import _thread as thread
import os

import wave

import pyaudio

STATUS_FIRST_FRAME = 0  # 第一帧的标识
STATUS_CONTINUE_FRAME = 1  # 中间帧标识
STATUS_LAST_FRAME = 2  # 最后一帧的标识


class Ws_Param(object):
    # 初始化
    def __init__(self, APPID, APIKey, APISecret, Text):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.Text = Text

        # 公共参数(common)
        self.CommonArgs = {"app_id": self.APPID}
        # 业务参数(business)，更多个性化参数可在官网查看
        self.BusinessArgs = {"aue": "raw", "auf": "audio/L16;rate=16000", "vcn": "xiaoyan", "tte": "utf8"}
        self.Data = {"status": 2, "text": str(base64.b64encode(self.Text.encode('utf-8')), "UTF8")}
        # 使用小语种须使用以下方式，此处的unicode指的是 utf16小端的编码方式，即"UTF-16LE"”
        # self.Data = {"status": 2, "text": str(base64.b64encode(self.Text.encode('utf-16')), "UTF8")}

    def set_data_text(self, text):
        self.Text = text
        self.Data = {"status": 2, "text": str(base64.b64encode(self.Text.encode('utf-8')), "UTF8")}

    # 生成url
    def create_url(self):
        url = 'wss://tts-api.xfyun.cn/v2/tts'
        # 生成RFC1123格式的时间戳
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        # 拼接字符串
        signature_origin = "host: " + "ws-api.xfyun.cn" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/tts " + "HTTP/1.1"
        # 进行hmac-sha256进行加密
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
            self.APIKey, "hmac-sha256", "host date request-line", signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        # 将请求的鉴权参数组合为字典
        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        # 拼接鉴权参数，生成url
        url = url + '?' + urlencode(v)
        # print("date: ",date)
        # print("v: ",v)
        # 此处打印出建立连接时候的url,参考本demo的时候可取消上方打印的注释，比对相同参数时生成的url与自己代码生成的url是否一致
        # print('websocket url :', url)
        return url


wsParam = Ws_Param(APPID=_public_config.secret('XFYUN_APP_ID'), APISecret=_public_config.secret('XFYUN_API_SECRET'),
                   APIKey=_public_config.secret('XFYUN_API_KEY'),
                   Text='请介绍你自己')

audio_base64_list = []

def on_message(ws, message):
    try:
        message = json.loads(message)
        code = message["code"]
        sid = message["sid"]
        audio = message["data"]["audio"]
        audio_base64_list.append(audio)
        audio = base64.b64decode(audio)
        status = message["data"]["status"]
        if status == 2:
            print("ws is closed")
            ws.close()
        if code != 0:
            errMsg = message["message"]
            print("sid:%s call error:%s code is:%s" % (sid, errMsg, code))
        else:

            with open('./demo.pcm', 'ab') as f:
                f.write(audio)

    except Exception as e:
        print("receive msg,but parse exception:", e)


# 收到websocket错误的处理
def on_error(ws, error):
    print("### error:", error)


# 收到websocket关闭的处理
def on_close(ws, _, __):
    print("### closed ###")


# 收到websocket连接建立的处理
def on_open(ws):
    def run(*args):
        d = {"common": wsParam.CommonArgs,
             "business": wsParam.BusinessArgs,
             "data": wsParam.Data,
             }
        d = json.dumps(d)
        print("------>开始发送文本数据")
        ws.send(d)
        if os.path.exists('demo.pcm'):
            os.remove('demo.pcm')

    thread.start_new_thread(run, ())


def pcm2wav(pcm_file, wav_file, channels=1, bits=16, sample_rate=16000):
    # 打开 PCM 文件
    pcmf = open(pcm_file, 'rb')
    pcmdata = pcmf.read()
    pcmf.close()

    # 打开将要写入的 WAVE 文件
    wavfile = wave.open(wav_file, 'wb')
    # 设置声道数
    wavfile.setnchannels(channels)
    # 设置采样位宽
    wavfile.setsampwidth(bits // 8)
    # 设置采样率
    wavfile.setframerate(sample_rate)
    # 写入 data 部分
    wavfile.writeframes(pcmdata)
    wavfile.close()


def sound_out(output_wav):
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    wf = wave.open(output_wav, 'rb')
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    output=True,
                    frames_per_buffer=CHUNK, )

    data = wf.readframes(CHUNK)

    while len(data) > 0:
        stream.write(data)
        data = wf.readframes(CHUNK)

    stream.stop_stream()
    stream.close()

    p.terminate()


def generate_wav_response(message, file_path='demo.wav'):
    wsParam.set_data_text(message)

    websocket.enableTrace(False)
    wsUrl = wsParam.create_url()
    ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.on_open = on_open
    print('开始合成了', datetime.now(), message)
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
    print('应该是结束合成了', datetime.now())
    output_pcm = 'demo.pcm'
    output_wav = file_path
    print('开始转换了', datetime.now())
    pcm2wav(output_pcm, output_wav)
    print('应该是结束转换了', datetime.now())
    return

def generate_base64_array(message):
    global audio_base64_list
    audio_base64_list = []

    wsParam = Ws_Param(APPID=_public_config.secret('XFYUN_APP_ID'), APISecret=_public_config.secret('XFYUN_API_SECRET'),
                       APIKey=_public_config.secret('XFYUN_API_KEY'),
                       Text="大语言模型，指使用大量文本数据训练的深度学习模型，可以生成自然语言文本或理解语言文本的含义")
    websocket.enableTrace(False)
    wsUrl = wsParam.create_url()
    ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.on_open = on_open
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    return audio_base64_list

def convert_pcm_to_webm(pcm_file_path, webm_file_path):
    current_working_directory = os.getcwd()
    print(current_working_directory)

    pcm_file_abs_path = os.path.abspath(pcm_file_path)
    webm_file_abs_path = os.path.abspath(webm_file_path)
    print(pcm_file_abs_path)
    print(webm_file_abs_path)
    try:
        # 构建ffmpeg命令
        command = [
            'ffmpeg',
            '-i', pcm_file_abs_path,  # 输入文件
            '-c:a', 'libopus',  # 使用libopus编码器
            '-b:a', '128k',  # 音频比特率，可以根据需要调整
            '-v', 'error',  # 只输出错误信息
            webm_file_abs_path  # 输出文件
        ]

        # 执行ffmpeg命令
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 检查命令是否执行成功
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr.decode()}")
            return False
        else:
            print("Conversion successful.")
            return True
    except Exception as e:
        print(f"An error occurred during conversion: {e}")
        return False


if __name__ == "__main__":
    # 测试时候在此处正确填写相关信息即可运行
    wsParam = Ws_Param(APPID=_public_config.secret('XFYUN_APP_ID'), APISecret=_public_config.secret('XFYUN_API_SECRET'),
                       APIKey=_public_config.secret('XFYUN_API_KEY'),
                       Text="大语言模型，指使用大量文本数据训练的深度学习模型，可以生成自然语言文本或理解语言文本的含义")
    websocket.enableTrace(False)
    wsUrl = wsParam.create_url()
    ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.on_open = on_open
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    output_pcm = 'demo.pcm'
    output_wav = 'demo.wav'
    pcm2wav(output_pcm, output_wav)
    sound_out(output_wav)