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

text = f"""
在这个游戏中，玩家将扮演一个勇敢的冒险者，探索一个神秘的世界。\
玩家将使用各种工具和技能，如武器、技能、物品等，来探索、战斗和收集物品。\
游戏中有各种各样的敌人和挑战，玩家需要通过策略和技巧来克服它们。\
玩家还可以与其他玩家进行合作或竞争，体验丰富的社交互动。\
游戏的目标是完成各种任务和挑战，提升角色的能力和装备，最终成为这个世界的英雄。\
"""
prompt = f"""
你是一个游戏博主，对于任何游戏都有自己独特的理解。\
请总结这段游戏内容，并给出一个游戏主题。\
请用中文回答。\
游戏内容：
{text}
"""
# 指令内容，使用 ``` 来分隔指令和待总结的内容
response = get_completion(prompt)
print(response)