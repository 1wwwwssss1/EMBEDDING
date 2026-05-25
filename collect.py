import os
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
import panel as pn
load_dotenv(find_dotenv())
import json
from tool import get_completion_from_messages

context = [{'role':'system', 'content':"""
你是订餐机器人，为披萨餐厅自动收集订单信息。
你要首先问候顾客。然后等待用户回复收集订单信息。收集完信息需确认顾客是否还需要添加其他内容。
最后需要询问是否自取或外送，如果是外送，你要询问地址。
最后告诉顾客订单总金额，并送上祝福。

请确保明确所有选项、附加项和尺寸，以便从菜单中识别出该项唯一的内容。
你的回应应该以简短、非常随意和友好的风格呈现。

菜单包括：

菜品：
意式辣香肠披萨（大、中、小） 12.95、10.00、7.00
芝士披萨（大、中、小） 10.95、9.25、6.50
茄子披萨（大、中、小） 11.95、9.75、6.75
薯条（大、小） 4.50、3.50
希腊沙拉 7.25

配料：
奶酪 2.00
蘑菇 1.50
香肠 3.00
加拿大熏肉 3.50
AI酱 1.50
辣椒 1.00

饮料：
可乐（大、中、小） 3.00、2.00、1.00
雪碧（大、中、小） 3.00、2.00、1.00
瓶装水 5.00
"""} ]

panels = []
def collect_messages(_):
    prompt = inp.value_input
    inp.value = ''
    context.append({"role": "user", "content": f"{prompt}"})
    response = get_completion_from_messages(context)
    context.append({"role": "assistant", "content": f"{response}"})
    panels.append(
        pn.Row("user", pn.pane.Markdown(prompt, width=600)))
    panels.append(
        pn.Row("assistant", pn.pane.Markdown(response, width=600),styles={'background-color': '#F6F6F6'}))
    
    if any(x in prompt for x in ["就这些","完成","下单"]):
        json_result = generate_order_json()
        panels.append(pn.Row("订单JSON", pn.pane.Markdown(f"'''json\n{json_result}\n'''",width=600))
        )
    return pn.Column(*panels)

def generate_order_json():
    """根据当前的context历史消息，生成订单的JSON摘要"""
    messages = context.copy()
    messages.append({"role": "system", "content": 
                     '''创建上一个食品订单的 json 摘要。\
逐项列出每件商品的价格，字段应该是 1) 披萨，包括大小 2) 配料列表 3) 饮料列表，包括大小 4) 配菜列表包括大小 5) 总价
你应该给我返回一个可解析的Json对象，包括上述字段'''},
    )

pn.extension()

inp = pn.widgets.TextInput(value='Hi', placeholder='Enter text here…')
button_conversation = pn.widgets.Button(name="Chat!")

interactive_conversation = pn.bind(collect_messages, button_conversation)

def show_json_output(_):
    json_result = generate_order_json()
    return pn.pane.JSON(json.loads(json_result) if isinstance(json_result, str) else json_result,name = "Order Summary")
interactive_json = pn.bind(show_json_output, button_conversation)
dashboard = pn.Column(
    inp,
    pn.Row(button_conversation),
    pn.panel(interactive_conversation, loading_indicator=True, height=300),
    pn.panel(interactive_json,height=200)
)
if __name__ == "__main__":
    dashboard.show()