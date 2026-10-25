#coding=utf-8

"""
requires Python 3.6 or later
pip install requests
"""
import nkcn_public_config as _public_config
import base64
import json
import uuid
import requests

# 填写平台申请的appid, access_token以及cluster
appid = _public_config.secret("VOLCANO_TTS_APP_ID")
access_token= _public_config.secret('VOLCANO_TTS_ACCESS_TOKEN')
cluster = "volcano_tts"

voice_type = "BV700_V2_streaming"
host = "openspeech.bytedance.com"
api_url = f"https://{host}/api/v1/tts"

header = {"Authorization": f"Bearer;{access_token}"}

speakMessage = "你好宝贝，我是AI人工智障"

def generate(message, file_path, role, emotion):
    global speakMessage, voice_type
    speakMessage = message
    voice_type = role
    request_json = {
        "app": {
            "appid": appid,
            "token": "access_token",
            "cluster": cluster
        },
        "user": {
            "uid": "388808087185088"
        },
        "audio": {
            "voice_type": voice_type,
            "encoding": "mp3",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": speakMessage,
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson"
        }
    }
    # 非通用情感需要指明
    if emotion != "no":
        request_json["audio"]["emotion"] = emotion
    try:
        resp = requests.post(api_url, json.dumps(request_json), headers=header)
        # print(f"resp body: \n{resp.json()}")
        print("speak_generate: 请求ok")
        if "data" in resp.json():
            data = resp.json()["data"]
            file_to_save = open(file_path, "wb")
            file_to_save.write(base64.b64decode(data))
            print("speak_generate: 写入ok")
        else:
            print("语音合成请求回来的resp异常，没有data字段？？")
    except Exception as e:
        e.with_traceback()
        print("语音合成请求回来的resp异常")
    return
