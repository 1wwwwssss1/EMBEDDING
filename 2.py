import paramiko
import json
import pandas as pd
import math
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量（获取服务器连接凭证）
load_dotenv()

HOST = os.getenv("BAIYUN_HOST")
USER = os.getenv("BAIYUN_USER")
PWD  = os.getenv("BAIYUN_PWD")

# 服务器日志审计根目录
CONVERSATIONS_DIR = "/root/BaiYun_Agent/logs/conversations/audit"

# 本地报告输出路径与企业微信最新花名册路径
LOCAL_REPORT = r"D:\yunxiaoxin\BaiYun_Final_Report_Multi.md"
WECOM_CACHE_PATH = r"D:\yunxiaoxin\wecom_cache\wecom_users_latest.json"

# ========== 一级部门负责人硬编码映射 ==========
L1_MGR_MAP = {
    "平台中心": "杜震宇",
    "产品中心": "向启胜",
    "营销中心": "曾桂文",
    "战略业务发展中心": "陈旭东",
    "运作中心": "林加帆",
    "品牌市场部": "罗群勇",
    "品牌 market 部": "罗群勇",
    "人力行政部": "姜宇",
    "财务部": "黄定",
    "海外事业部": "无"
}

# ========== 部门统计大盘全局容器 ==========
DYNAMIC_L1_TOTAL = {}     
DYNAMIC_L2_TOTAL = {}     
DYNAMIC_L1_TO_L2 = {}     
DYNAMIC_L1_ORDER = []     

def get_l1_name(dept: str) -> str:
    if not dept: return "其他"
    parts = [p.strip() for p in dept.replace("[","").replace("]","").replace('"','').split("/") if p.strip()]
    if not parts: return "其他"
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "other")

# ==============================================================================
# 🧠 升级版花名册加载：将所有人录入身份库（包括离职人员），但对在职/离职进行分流打标
# ==============================================================================
def load_wecom_user_registry():
    global DYNAMIC_L1_TOTAL, DYNAMIC_L2_TOTAL, DYNAMIC_L1_TO_L2, DYNAMIC_L1_ORDER
    user_registry = {}  # 存放 账号/手机号 -> [姓名, 完整部门路径, 是否离职] 的映射
    
    if not os.path.exists(WECOM_CACHE_PATH):
        print(f"⚠️ 警告：未找到企微本地缓存 {WECOM_CACHE_PATH}")
        return user_registry
        
    l1_counter = {}
    l2_counter = {}
    l1_to_l2_rel = {}
    observed_l1_order = []

    with open(WECOM_CACHE_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            user_list = data.get("list", [])
            for u in user_list:
                name = u.get("name", "").strip()
                uid = str(u.get("wecomUserId", "")).strip()  # 员工的唯一账号/手机号
                
                if not uid: continue
                
                # 🌟 关键诊断：判断此人是否属于离职人员
                is_resigned = "离职" in name
                
                dept_paths = u.get("departmentNames", [])
                primary_path = dept_paths[0] if dept_paths else "默认部门"
                
                # 无论是否离职，全部放入大身份库中登记，打上离职标签 (True/False)
                user_registry[uid] = [name, primary_path, is_resigned]

                # 🛑 阻断：只有【在职】人员，才有资格参与分母大盘的统计！
                if is_resigned: 
                    continue
                    
                if not dept_paths: 
                    continue
                    
                # 基础花名册层面过滤技术支持部参与大盘分母编制
                parts = [p.strip() for p in primary_path.split("/") if p.strip()]
                if not parts: 
                    continue
                
                l1 = parts[0]
                l2 = parts[1] if len(parts) >= 2 else ""

                if "技术支持部" in l1: 
                    continue

                if l1 not in l1_counter:
                    l1_counter[l1] = 0
                    observed_l1_order.append(l1)
                    l1_to_l2_rel[l1] = set()
                l1_counter[l1] += 1

                if l2:
                    l2_counter[l2] = l2_counter.get(l2, 0) + 1
                    l1_to_l2_rel[l1].add(l2)

            DYNAMIC_L1_TOTAL = l1_counter
            DYNAMIC_L2_TOTAL = l2_counter
            DYNAMIC_L1_TO_L2 = {k: sorted(list(v)) for k, v in l1_to_l2_rel.items()}
            DYNAMIC_L1_ORDER = observed_l1_order
            print(f"✅ 成功加载企微全局身份库。在职大盘总分母数已对齐。")
            
        except Exception as e:
            print(f"❌ 解析企微缓存失败: {e}")
            
    return user_registry

# ==============================================================================
# 🪵 解析审计日志行（精准打击、拦截离职人员产生的历史日志分子）
# ==============================================================================
def parse_audit_line_multi(line: str, user_registry: dict, folder_user_id: str):
    try:
        obj = json.loads(line)
    except:
        return []

    datetime_str = obj.get("datetime", "")
    if not datetime_str: return []
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except:
        return []
    
    date_part = dt.strftime("%Y-%m-%d")
    date_md = dt.strftime("%m-%d")
    msg_id = obj.get("message_id")
    if not msg_id: return []

    conv_id = str(obj.get("conversation_id") or "").strip()

    # --- 🌟 核心修改点：强制身份对齐 ---
    # 1. 尝试匹配文件夹名(手机号)
    # 2. 如果匹配不到，尝试匹配会话ID(缩写或手机号)
    # 3. 彻底过滤掉匹配不到任何人的“随机哈希乱码”
# 修改后的逻辑：只认 conv_id 是否在花名册的名单里
    # 如果 conv_id 对应不上花名册里的任何一个人，直接扔掉这行日志，不进行任何后续处理
    if conv_id not in user_registry:
        return []

    target_uid = conv_id
    
    # 强制检查离职状态
    if user_registry[target_uid][2]:
        return []
        
    # 强制检查部门（只有在花名册里登记的部门才被认可）
    name, dept_full, _ = user_registry[target_uid]
    # 这里不需要再去看日志里的部门了，直接用花名册里的



    tool_calls = obj.get("tool_calls") or []
    rows = []
    
    for idx, tc in enumerate(tool_calls):
        tool_name = tc.get("tool_name", "")
        biz = None
        if tool_name == "quote_tool": biz = "询价"
        elif tool_name == "waybill_tool": biz = "面单推送"
        elif tool_name == "tracking_tool": biz = "轨迹查询"
        elif tool_name == "handoff_to_human":
            payload = tc.get("payload", {})
            if (tc.get("ticket_created") is True) or (payload.get("ticket_created") is True) or (tc.get("reused") is True) or (tc.get("success") is True):
                biz = "转人工成功"
        else:
            biz = tool_name
        
        if biz:
            rows.append({
                "day_full": date_part,
                "date_md": date_md,
                "uid": target_uid,      # 【标准化UID】解决统计重复
                "raw_conv": conv_id,    # 【保留原始ID】用于溯源
                "name": name,
                "dept": dept_full,
                "biz": biz,
                "fingerprint": f"{msg_id}_{biz}_{idx}"
            })
    
    # 提取闲聊行为
    intent = obj.get("intent", "")
    if intent == "闲聊" and not tool_calls:
        rows.append({
            "day_full": date_part,
            "date_md": date_md,
            "uid": target_uid,
            "raw_conv": conv_id,
            "name": name,
            "dept": dept_full,
            "biz": "闲聊",
            "fingerprint": f"{msg_id}_chat"
        })
    
    return rows

# ==============================================================================
# 📊 报表生成主引擎
# ==============================================================================
def generate_multi_report():
    # 1. 初始化身份注册大本营
    user_registry = load_wecom_user_registry()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(HOST, username=USER, password=PWD, timeout=20)

        start_date = datetime(2026, 4, 24)
        end_date = datetime.now()
        today_full_str = end_date.strftime("%Y-%m-%d")

        raw_rows = []
        current = start_date
        
        print("📂 正在连接白云服务器并行拉取日志，并基于手机号文件夹实现全量身份对账...")
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            
            # 使用 Linux find 命令，在拉取每一行日志内容时同时带上其文件绝对路径
            cmd = f"find {CONVERSATIONS_DIR} -name '{date_str}.jsonl' -exec grep -H '' {{}} \\; 2>/dev/null"
            _, stdout, _ = ssh.exec_command(cmd)
            
            for line_with_path in stdout:
                if ":" not in line_with_path: continue
                file_path, line_content = line_with_path.split(":", 1)
                
                # 完美切割路径，提取出当前行日志所属的手机号/账号文件夹名称
                path_parts = file_path.split("/")
                folder_user_id = path_parts[-2] if len(path_parts) >= 2 else ""
                
                rows = parse_audit_line_multi(line_content, user_registry, folder_user_id)
                raw_rows.extend(rows)
                
            current += timedelta(days=1)

        if not raw_rows:
            print("⚠️ 未统计到任何非离职人员的有效行为日志。")
            return

        df = pd.DataFrame(raw_rows).drop_duplicates(subset=['fingerprint'])

        # ==========================================
        # 🌟 强力清洗阻断技术支持部
        # ==========================================
        df = df[~df['dept'].str.contains('技术支持部', na=False)]

        def parse_clean_l1(d):
            parts = [p.strip() for p in d.split("/") if p.strip()]
            if not parts: return "其他"
            return parts[1] if parts[0] == "百运网" and len(parts) >= 2 else parts[0]

        def parse_clean_l2(d):
            parts = [p.strip() for p in d.split("/") if p.strip()]
            if not parts: return ""
            if parts[0] == "百运网":
                return parts[2] if len(parts) >= 3 else ""
            return parts[1] if len(parts) >= 2 else ""

        df['l1'] = df['dept'].apply(parse_clean_l1)
        df['l2'] = df['dept'].apply(parse_clean_l2)
        df['dept_short'] = df.apply(lambda r: f"{r['l1']}/{r['l2']}" if r['l2'] else r['l1'], axis=1)
        df['mgr'] = df['l1'].apply(lambda l: L1_MGR_MAP.get(l, "无"))

        core_biz_list = ["询价", "面单推送", "轨迹查询", "转人工成功"]
        df_core = df[df['biz'].isin(core_biz_list)]

        # 趋势基础统计
        daily_stats = []
        cum_users = set()
        cur = start_date
        while cur <= end_date:
            d_str = cur.strftime("%Y-%m-%d")
            d_rows = df[df['day_full'] == d_str]
            d_uids = set(d_rows['uid'])
            new_u = d_uids - cum_users
            cum_users.update(d_uids)
            daily_stats.append({
                'date_full_std': d_str,
                'day': cur.strftime("%d"),
                'date_full': cur.strftime("%m-%d"),
                'dau': len(d_uids),
                'new': len(new_u),
                'cum': len(cum_users)
            })
            cur += timedelta(days=1)

        total_calls = len(df_core)
        total_trial = df['uid'].nunique()
        avg_dau = math.ceil(sum(s['dau'] for s in daily_stats) / len(daily_stats))
        #today_handoff = len(df_core[(df_core['day_full'] == today_full_str) & (df_core['biz'] == '转人工成功')])
        active_rates = [(s['dau']/s['cum']) if s['cum']>0 else 0 for s in daily_stats]
        avg_active_rate = f"{round(sum(active_rates)/len(active_rates)*100,1)}%" if active_rates else "0%"

        # ==================== 渲染输出 Markdown 报告 ====================
        md = f"# 一、核心数据概览\n"
        md += f"- 日均使用人数：{avg_dau}\n- 累计试用人数：{total_trial}\n- 功能调用总量：{total_calls}\n"
        md += f"- 日均活跃率：{avg_active_rate}\n"#- 今日成功转人工次数：{today_handoff}\n\n"
        md += "| 日期 | 日活跃用户 | 当日新增 | 累计人数 |\n| :--- | :--- | :--- | :--- |\n"
        for s in daily_stats:
            md += f"| {s['date_full']} | {s['dau']} | {s['new']} | {s['cum']} |\n"

        md += "\n## 部门调用 TOP 5\n| 排名 | 部门 | 部门负责人 | 次数 |\n| :--- | :--- | :--- | :--- |\n"
        dept_top = df.groupby(['dept_short','mgr']).size().reset_index(name='c').sort_values('c',ascending=False).head(5)
        for i,r in enumerate(dept_top.itertuples(),1):
            md += f"| {i} | {r.dept_short} | {r.mgr} | {r.c} |\n"

        md += "\n## 人均调用 TOP 15\n| 排名 | 姓名 | 部门 | 部门负责人 | 调用次数 |\n| :--- | :--- | :--- | :--- | :--- |\n"
        user_top = df.groupby(['name','dept_short','mgr']).size().reset_index(name='c').sort_values('c',ascending=False).head(15)
        for i,r in enumerate(user_top.itertuples(),1):
            md += f"| {i} | {r.name} | {r.dept_short} | {r.mgr} | {r.c} |\n"

        md += "\n## 各部门使用情况明细\n"
        for l1 in DYNAMIC_L1_ORDER:
            l1_total_headcount = DYNAMIC_L1_TOTAL.get(l1, 0)
            l1_df = df[df['l1'] == l1]
            
            if l1_total_headcount == 0 and len(l1_df) == 0: continue
                
            mgr_str = L1_MGR_MAP.get(l1, "无")
            md += f"\n**{l1}：{l1_total_headcount}人**\n\n"
            all_l2 = DYNAMIC_L1_TO_L2.get(l1, [])
            
            if not all_l2:
                call_users = l1_df['uid'].nunique()
                pct = f"{round(call_users/l1_total_headcount*100,1)}%" if l1_total_headcount else "-%"
                md += "| 一级部门 | 负责人 | 二级部门 | 部门人数 | 调用功能人数 | 部门使用人数占比 |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                md += f"| {l1} | {mgr_str} | 无 | {l1_total_headcount} | {call_users} | {pct} |\n\n"
            else:
                l2_counts = l1_df.groupby('l2').size()
                l2_with = [l2 for l2 in l2_counts.index if l2 != ""]
                l2_without = [l2 for l2 in all_l2 if l2 not in l2_with]
                l2_list = l2_with + l2_without
                
                md += "| 一级部门 | 负责人 | 二级部门 | 部门人数 | 调用功能人数 | 部门使用人数占比 |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                
                other_df = l1_df[l1_df['l2'] == ""]
                l2_total_headcount_sum = sum(DYNAMIC_L2_TOTAL.get(l2, 0) for l2 in all_l2)
                other_head = l1_total_headcount - l2_total_headcount_sum
                
                if other_head > 0 or len(other_df) > 0:
                    o_users = other_df['uid'].nunique()
                    o_pct = f"{round(o_users/other_head*100,1)}%" if other_head > 0 else "-%"
                    md += f"| {l1} | {mgr_str} | 无 | {max(other_head, 0)} | {o_users} | {o_pct} |\n"
                
                for l2 in l2_list:
                    l2_df = l1_df[l1_df['l2'] == l2]
                    head = DYNAMIC_L2_TOTAL.get(l2, 0)
                    u = l2_df['uid'].nunique()
                    pct = f"{round(u/head*100,1)}%" if head else "-%"
                    l2_display = l2 if l2 else "无"
                    md += f"| {l1} | {mgr_str} | {l2_display} | {head} | {u} | {pct} |\n"
                md += "\n"

        # 功能应用详情
        md += "\n# 二、功能应用详情\n## 每日功能调用统计\n| 日期 | 询价调用次数 |面单推送调用次数 | 轨迹查询调用次数 | 转人工次数 |\n| :--- | :--- | :--- | :--- | :--- |\n"
        for s in daily_stats:
            d_std = s['date_full_std']
            d_df_core = df_core[df_core['day_full'] == d_std]
            md += f"| {s['date_full']} | {len(d_df_core[d_df_core['biz']=='询价'])} | {len(d_df_core[d_df_core['biz']=='面单推送'])} | {len(d_df_core[d_df_core['biz']=='轨迹查询'])} | {len(d_df_core[d_df_core['biz']=='转人工成功'])} |\n"

        for b_name,icon in [("询价","🔍"),("面单推送","📦"),("轨迹查询","📍"),("转人工成功","👤")]:
            s_df = df_core[df_core['biz']==b_name]
            u,c = s_df['uid'].nunique(), len(s_df)
            p = round(c/total_calls*100,1) if total_calls else 0
            md += f"\n### {icon} {b_name}功能：累计 {u} 人使用，调用 {c} 次，占比 {p}%\n"
            md += "部门 TOP5\n| 部门 | 负责人 | 人数 | 次数 |\n| :--- | :--- | :--- | :--- |\n"
            dt_s = s_df.groupby(['dept_short','mgr']).agg({'uid':'nunique','biz':'count'}).sort_values('biz',ascending=False).head(5)
            for (d,m),r in dt_s.iterrows():
                md += f"| {d} | {m} | {r['uid']} | {r['biz']} |\n"
            md += f"\n人员 TOP5\n| 姓名 | 负责人 | 次数 |\n| :--- | :--- | :--- |\n"
            ut_s = s_df.groupby(['name','mgr']).size().sort_values(ascending=False).head(5)
            for (n,m),cnt in ut_s.items():
                md += f"| {n} | {m} | {cnt} |\n"

        md += "\n## 三、重点功能渗透情况\n| 日期 | 询价用户数 | 工单(转人工)用户数 |\n| :--- | :--- | :--- |\n"
        for s in daily_stats:
            d_std = s['date_full_std']
            d_df_core = df_core[df_core['day_full'] == d_std]
            md += f"| {s['date_full']} | {d_df_core[d_df_core['biz']=='询价']['uid'].nunique()} | {d_df_core[d_df_core['biz']=='转人工成功']['uid'].nunique()} |\n"

        # 写入本地大报告
        os.makedirs(os.path.dirname(LOCAL_REPORT), exist_ok=True)
        with open(LOCAL_REPORT, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"🎉 完美闭环！全量在职数据对齐完毕。最终运营报告已生成至：{LOCAL_REPORT}")

    finally:
        ssh.close()

if __name__ == "__main__":
    generate_multi_report()