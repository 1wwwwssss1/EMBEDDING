import os
from openai import OpenAI
#def get_completion(prompt, model="qwen-plus"):
#    api_key = os.environ.get("OPENAI_API_KEY")
#    if not api_key:
#        raise ValueError("未找到 OPENAI_API_KEY environment variable ")
#    client = OpenAI(
#        api_key=api_key,
#        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
#    )
#    try:
#        completion = client.chat.completions.create(
#            model=model,
#            messages=[{"role": "user", "content": prompt}],
#        )
#       return completion.choices[0].message.content
#    except Exception as e:
#        return f"调用 API 失败:{str(e)} "

def get_completion_from_messages(messages, model="qwen-plus",temperature=0):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
          raise ValueError("未找到 OPENAI_API_KEY environment variable ")
    client = OpenAI(
         api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"调用 API 失败:{str(e)} "
