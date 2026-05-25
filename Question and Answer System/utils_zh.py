import json

def get_products_and_category():
    """
    获取商品及其分类
    """
    return {
        "科技产品": {
            "手机与配件": [
                "SmartX ProPhone - 6.5英寸显示屏，128GB存储空间，1200万像素双摄像头，支持5G，售价899元",
                "MobiTech Ultra - 6.1英寸显示屏，256GB存储空间，4800万像素三摄，防水设计，售价799元",
                "无线充电板 - 15W快速充电，兼容所有支持无线充电的手机，售价29元",
                "手机保护壳 - 防摔设计，多种颜色可选，售价19元"
            ],
            "电脑与平板": [
                "TechPro笔记本 - 15.6英寸全高清屏，Intel i7处理器，16GB内存，1TB固态硬盘，售价1499元",
                "TabMaster平板 - 10.9英寸显示屏，256GB存储空间，支持手写笔，售价599元",
                "无线鼠标 - 静音设计，长续航，兼容Windows和Mac，售价25元",
                "机械键盘 - 青轴手感，RGB背光，全键无冲，售价49元"
            ],
            "电视与影音": [
                "4K智能电视 - 55英寸，HDR，语音控制，内置流媒体应用，售价699元",
                "超高清电视 - 65英寸，120Hz刷新率，游戏模式，售价999元",
                "家庭影院音响 - 5.1声道，杜比音效，无线低音炮，售价399元",
                "蓝牙音箱 - 便携防水，360度环绕音效，20小时续航，售价89元"
            ],
            "相机与摄像": [
                "FotoSnap相机 - 2400万像素，4K视频录制，WiFi连接，售价599元",
                "ActionCam运动相机 - 防水防震，4K/60fps，防抖技术，售价299元",
                "相机三脚架 - 可折叠，铝合金材质，适用于所有相机型号，售价39元",
                "镜头清洁套装 - 专业清洁，不伤镜头，包含清洁液、布、刷，售价15元"
            ]
        }
    }

def find_category_and_product_only(user_input, products_and_category):
    """
    从用户输入中识别商品和分类
    """
    products = []
    user_input_lower = user_input.lower()
    
    categories = products_and_category["科技产品"]
    for category_name, items in categories.items():
        for item in items:
            item_name = item.split(" - ")[0].lower()
            if item_name in user_input_lower:
                products.append(item)
    
    if not products:
        return "[]"
    
    return json.dumps(products, ensure_ascii=False)

def read_string_to_list(input_string):
    """
    将字符串转换为列表
    """
    if input_string is None:
        return []
    
    try:
        return json.loads(input_string)
    except json.JSONDecodeError:
        return []

def generate_output_string(input_list):
    """
    生成输出字符串
    """
    if not input_list:
        return "未找到相关产品信息"
    
    output = ""
    for i, product in enumerate(input_list, 1):
        output += f"{i}. {product}\n"
    
    return output