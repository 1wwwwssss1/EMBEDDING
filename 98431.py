import json
import os

# 🌟 核心配置：锁定最权威的企业微信本地全量缓存与离职黑名单
MASTER_CACHE_PATH = r"D:\yunxiaoxin\wecom_cache\wecom_users_latest.json"
EXCLUDE_TXT_PATH = r"D:\yunxiaoxin\离职人员.txt"

def parse_wecom_layers(dept_names_list):
    """
    针对企业微信真实的 departmentNames 格式进行层级解构：
    真实样例: ["技术支持部/AI项目组/软件开发组"] 或 ["产品中心/前线客服部"]
    """
    if not dept_names_list or not isinstance(dept_names_list, list) or len(dept_names_list) == 0:
        return "其他", ""
    
    # 提取列表里的第一个路径字符串
    dept_path_str = str(dept_names_list[0]).strip()
    if not dept_path_str:
        return "其他", ""
        
    # 按照 '/' 进行切分
    parts = [p.strip() for p in dept_path_str.split("/") if p.strip()]
    
    # 🌟 纯正规律对齐：
    # 第 1 项（parts[0]）是一级部门：如 技术支持部、产品中心、营销中心
    l1 = parts[0] if len(parts) >= 1 else "其他"
    
    # 第 2 项（parts[1]）是二级部门：如 AI项目组、前线客服部
    l2 = parts[1] if len(parts) >= 2 else ""
    
    return l1, l2

def load_excluded_keywords():
    """
    全自动解析本地离职人员.txt，精准抓取离职员工纯姓名，用于日志及花名册洗净
    """
    keywords = []
    if os.path.exists(EXCLUDE_TXT_PATH):
        with open(EXCLUDE_TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "：" in line:
                    name_part = line.split("：")[-1].strip()
                    # 剥离 5.15离职、0531离职 等特殊尾巴，还原纯姓名
                    pure_name = name_part.split("5.")[0].split("05")[0].replace("离职", "").strip()
                    if pure_name and pure_name not in keywords:
                        keywords.append(pure_name)
    # 兜底核心词
    if not keywords:
        keywords = ["赵健", "雷隆瑶", "李媛", "张鑫", "黄俊涛", "叶嘉仪", "蒋欣蓉", "周蜜"]
    return keywords

def main():
    # 1. 动态加载清洗黑名单
    excluded_keywords = load_excluded_keywords()
    print(f"⚙️ 离职黑名单解析成功，共捕获模糊洗净关键词: {len(excluded_keywords)} 个")

    if not os.path.exists(MASTER_CACHE_PATH):
        print(f"❌ 运行失败：未能在本地找到企业微信权威花名册：{MASTER_CACHE_PATH}")
        return

    # 2. 加载本地权威 JSON 全量花名册
    with open(MASTER_CACHE_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"❌ 解析本地 JSON 失败: {e}")
            return

    user_list = data.get("list", [])
    if not user_list:
        print("⚠️ 花名册缓存中没有找到 'list' 用户列表数据。")
        return

    # 3. 初始化在职计数容器
    l1_counts = {}   # 一级部门（中心/大部）
    l2_counts = {}   # 二级部门（业务部/项目组）
    total_in_service = 0

    # 4. 遍历洗净并动态归流
    for user in user_list:
        name = str(user.get("name", "")).strip()
        dept_field = user.get("departmentNames", [])

        # 🛑 拦截网：命中的离职黑名单、名字自带离职后缀、或无效账号，直接剔除
        if any(kw in name for kw in excluded_keywords) or "离职" in name or "not_found" in name or not name:
            continue

        # 解析层级：l1 为 parts[0]，l2 为 parts[1]
        l1, l2 = parse_wecom_layers(dept_field)

        # 过滤掉一些辅助分类或未分类的脏数据
        if l1 in ("其他", "") or not dept_field:
            continue

        total_in_service += 1

        # 累加一级部门（中心）人数
        l1_counts[l1] = l1_counts.get(l1, 0) + 1

        # 累加二级部门人数（三、四、五级更深的小组人头，通通自动合流到对应的二级部门里）
        if l2:
            l2_key = f"{l1}/{l2}"
            l2_counts[l2_key] = l2_counts.get(l2_key, 0) + 1
        else:
            l2_key = f"{l1}/(直属/未划分二级)"
            l2_counts[l2_key] = l2_counts.get(l2_key, 0) + 1

    # ==================== 格式化控制台数据打印 ====================
    print("\n" + "═"*55)
    print(f" 📊 企业微信真实花名册洗净完成！当前正常在职总人数: {total_in_service} 人")
    print("═"*55)

    print("\n🏢 【一级部门（按真实原生 L1 统计）正常在职人数】:")
    print("-" * 52)
    # 按人数由多到少降序排列
    for dept1, count in sorted(l1_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  🔹 {dept1:<18} : {count} 人")

    print("\n📂 【二级部门（业务部/项目组 - 自动吞并更深的小组）人数】:")
    print("-" * 52)
    for dept2, count in sorted(l2_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  🔸 {dept2:<28} : {count} 人")
    print("═"*55 + "\n")

if __name__ == "__main__":
    main()