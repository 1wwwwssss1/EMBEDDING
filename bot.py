import os
import openai
from dotenv import load_dotenv, find_dotenv
# 获取环境变量 OPENAI_API_KEY
load_dotenv(find_dotenv())
openai.api_key = os.environ['OPENAI_API_KEY']
def get_openai_key():
    _ = load_dotenv(find_dotenv())
    return os.environ['OPENAI_API_KEY']
openai.api_key = get_openai_key()
from tool import get_completion 
from tool import get_completion_from_messages

messages = [
    {"role": "system", "content": "你是一个台湾人."},
    {"role": "user", "content": "hello，请你用台湾话跟我打招呼"},
]
response = get_completion_from_messages(messages, temperature=0)
print(response)
