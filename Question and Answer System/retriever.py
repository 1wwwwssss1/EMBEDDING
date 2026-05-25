import os
import openai 
import utils_zh
import panel as pn
from tool import get_completion_from_messages
from dotenv import load_dotenv, find_dotenv
# 获取环境变量 OPENAI_API_KEY
load_dotenv(find_dotenv())
openai.api_key = os.environ['OPENAI_API_KEY']

def moderation_check(text):
    """
    使用大模型进行内容安全检查（替代 OpenAI Moderation API）
    """
    prompt = f"""
判断以下内容是否包含违规信息（暴力/色情/政治敏感/辱骂等）：

内容：{text}

只回答：
安全 或 不安全
"""

    res = get_completion_from_messages([
        {"role": "system", "content": "你是内容安全审核助手"},
        {"role": "user", "content": prompt}
    ])

    return "不安全" in res

def process_user_message_ch(user_input, all_messages, debug=True):
        """
    对用户信息进行预处理
    
    参数:
    user_input : 用户输入
    all_messages : 历史信息
    debug : 是否开启 DEBUG 模式,默认开启
    """
        #分隔符
        delimiter = "```"

        if moderation_check(user_input):
            if debug: print("第一步：输入不合规（LLM审核）")
            return "抱歉，您的请求不合规，请重新输入。", all_messages

        if debug: print("第一步：通过安全检查")

        #第二步：抽取出商品和对应的目录
        category_and_product_response = utils_zh.find_category_and_product_only(user_input, utils_zh.get_products_and_category())
        #print(category_and_product_response)
        try:
            category_and_product_list = utils_zh.read_string_to_list(category_and_product_response)
        except:
            category_and_product_list = []

        if debug: print("第二步：抽取出商品列表")

        #第三步：查找商品对应信息
        product_information = utils_zh.generate_output_string(category_and_product_list)
        if debug: print("第三步：查找抽取出的商品信息")

        #第四步：根据信息生成回答
        system_message = f"""
            您是一家大型电子商店的客户服务助理。\
            请以友好和乐于助人的语气回答问题，并提供简洁明了的答案。\
            请确保向用户提出相关的后续问题。
        """
        #插入message
        messages = [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': f"{delimiter}{user_input}{delimiter}"},
            {'role': 'assistant', 'content': f"相关商品信息:\n{product_information}"}
        ]
        #获取模型回复
        #通过附加all_messages实现多轮对话
        final_response = get_completion_from_messages(all_messages + messages)
        if debug: print("第四步：生成用户回答")
        #将该轮信息加入到历史信息中
        all_messages = all_messages + [
            {'role': 'user', 'content': user_input},
            {'role': 'assistant', 'content': final_response}
        ]


        #第五步：基于模型检查是否合规
        if moderation_check(final_response):
            if debug: print("第五步：输出不合规")
            return "抱歉，我们不能提供信息。", all_messages

        if debug: print("第五步：输出通过检查")

        #第六步：模型检查是否很好地回答了用户问题
        user_message = f"""
        用户信息: {delimiter}{user_input}{delimiter}
        代理回复: {delimiter}{final_response}{delimiter}

        回复是否足够回答问题
        如果足够，回答 Y
        如果不足够，回答 N
        仅回答上述字母即可
        """
        #要求模型评估回答
        evaluation_messages = [
            {'role': 'system', 'content': '你是一个评估助手。只返回Y或N。'},
            {'role': 'user', 'content': user_message}
        ]

        evaluation_response = get_completion_from_messages(evaluation_messages)
        #print(evaluation_response)
        if debug: print("第六步：模型评估该回答")
        #第七步：如果评估为Y，输出回答；如果评估为N，反馈将由人工修正答案
        is_good = evaluation_response.strip().upper().startswith("Y")

        if is_good:
            if debug: print("第七步：模型赞同该回答")
            return final_response, all_messages
        else:
            if debug: print("第七步：模型不赞成该回答")
            neg_str = "很抱歉，我无法提供您所需信息。我将为您转接到一位人工客服代表以获取进一步帮助。"
            return neg_str, all_messages
        
#user_input = "请告诉我关于 SmartX ProPhone 和 相机三脚架 的信息。另外，请告诉我关于你们的tvs的情况。"
#respoense,_ = process_user_message_ch(user_input, [])
#print(respoense)
output = pn.Column()
def collect_messages_ch(event=None, debug=True):
     global context
     '''
    用于收集用户的输入并生成助手的回答

    参数：
    debug: 用于觉得是否开启调试模式
    '''
     user_input = inp.value
     if debug:print(f'User Input = {user_input}')
     if user_input == "":
         return
     inp.value = ''
     #调用process_user_message_ch函数
     #response, context = process_user_message_ch(user_input, context, utils.get_products_and_category(),debug = True)
     response, context = process_user_message_ch(user_input, context, debug = False)
     #print(response)
     
     panels.append(
                pn.Row("user: ", pn.pane.Markdown(user_input, width=600))
    )
     panels.append(
               pn.Row("assistant: ", pn.pane.Markdown(response, width=600,styles={'background-color': '#F6F6F6'})))
     output.objects = panels

pn.extension()

panels = []
context = [{"role": "system", "content": "You are a Service assistant."}]
inp = pn.widgets.TextAreaInput(placeholder='Enter text here...')
button_conversation = pn.widgets.Button(name="Svervice Assistant")

output.objects = panels
button_conversation.on_click(collect_messages_ch)
dashboard = pn.Column(
    inp,
    button_conversation,
    pn.Column(*panels)
)

dashboard = pn.Column(
    inp,
    button_conversation,
    output
)
if __name__ == "__main__":
     pn.serve(dashboard)


