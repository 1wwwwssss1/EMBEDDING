import paramiko
import json
import pandas as pd
import math
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("BAIYUN_HOST")
USER = os.getenv("BAIYUN_USER")
PWD  = os.getenv("BAIYUN_PWD")

CONVERSATIONS_DIR = "/root/BaiYun_Agent/logs/conversations/audit"
CSV_PATH = "/home/user/results.csv"

LOCAL_REPORT = r"D:\yunxiaoxin\BaiYun_Final_Report_Multi.md"

# ========== 部门配置（保持原样） ==========
L1_DEPT_CONFIG = {
    "平台中心":        {"mgr": "杜震宇", "total": 2},
    "产品中心":        {"mgr": "向启胜", "total": 75},
    "营销中心":        {"mgr": "曾桂文", "total": 185},
    "战略业务发展中心": {"mgr": "陈旭东", "total": 123},
    "运作中心":        {"mgr": "林加帆", "total": 100},
    "品牌市场部":      {"mgr": "罗群勇", "total": 11},
    "人力行政部":      {"mgr": "姜宇",   "total": 7},
    "财务部":          {"mgr": "黄定",   "total": 2},
    "海外事业部":      {"mgr": "--",     "total": 46},
}
EXCLUDE_L1 = {"技术支持部"}
L2_HEADCOUNT = {
    "快递产品部": 14, "专线产品部": 19, "海运产品部": 2,
    "陆运产品部": 4,  "空派产品部": 18, "空运产品部": 6, "前线客服部": 11,
    "华中业务战区": 32, "机场管理部": 16, "机场一部": 68,
    "机场二部": 29, "机场三部": 14, "客服操作部": 25,
    "销售一部": 7, "销售二部": 8, "销售三部": 2,
    "广州业务战区": 36, "上海业务战区": 11, "义乌业务战区": 31,
    "坂田业务战区": 27, "创新业务部": 1,"管培生":2,
    "深圳运作部": 69, "广州运作部": 1, "义乌运作部": 4, "单证部": 25, "揽派部": 1,
    "新媒体运营组": 3, "市场策划组": 4, "品牌营销组": 3,
    "成都分公司": 34, "武汉分公司": 1, "汕头分公司": 11,
}
L1_TO_L2 = {
    "产品中心":        ["快递产品部","专线产品部","海运产品部","陆运产品部","空派产品部","空运产品部","前线客服部"],
    "营销中心":        ["华中业务战区","机场管理部","机场一部","机场二部","机场三部","客服操作部"],
    "战略业务发展中心": ["销售一部","销售二部","销售三部","广州业务战区","上海业务战区","义乌业务战区","坂田业务战区","创新业务部"],
    "运作中心":        ["深圳运作部","广州运作部","义乌运作部","单证部","揽派部"],
    "品牌市场部":      ["新媒体运营组","市场策划组","品牌营销组"],
    "人力行政部":      ["管培生"],
    "海外事业部":      ["成都分公司","武汉分公司","汕头分公司"],
}
L1_ORDER = ["平台中心", "产品中心", "营销中心", "战略业务发展中心",
            "运作中心", "品牌市场部", "人力行政部", "财务部", "海外事业部"]

def get_l1_name(dept: str) -> str:
    if not dept:
        return "其他"
    parts = [p.strip() for p in dept.split("/") if p.strip()]
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "其他")

def get_l2_name(dept: str) -> str:
    if not dept:
        return ""
    parts = [p.strip() for p in dept.split("/") if p.strip()]
    return parts[2] if len(parts) >= 3 else ""

def load_user_map_from_csv(ssh):
    sftp = ssh.open_sftp()
    try:
        with sftp.open(CSV_PATH, "r") as f:
            df = pd.read_csv(f)
    except Exception as e:
        print(f"❌ 读取CSV失败: {e}")
        return {}
    user_map = {}
    for _, row in df.iterrows():
        uid = str(row.get("user_id", "")).strip()
        name = str(row.get("name", uid)).strip()
        dept = str(row.get("department") or "默认部门").strip()
        l1 = get_l1_name(dept)
        mgr = L1_DEPT_CONFIG.get(l1, {}).get("mgr", "--")
        user_map[uid] = [name, dept, mgr]
    return user_map

# ========== 修改点 1：重构日志行解析逻辑 ==========
def parse_audit_line_multi(line: str, user_map: dict):
    """
    重构后的全量匹配模式：保持成功转人工判定不变。
    利用 message_id + idx 解决流式重复并防止全量漏算；
    利用 day_full 存储标准年月日修复跨月冲突Bug；
    引入 CSV 权威优先 + 日志信息动态兜底机制。
    """
    try:
        obj = json.loads(line)
    except:
        return []

    datetime_str = obj.get("datetime", "")
    if not datetime_str:
        return []
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except:
        return []
    
    date_part = dt.strftime("%Y-%m-%d")  # 核心：标准完整年月日标尺（防御跨月Bug）
    date_md = dt.strftime("%m-%d")       # 展示用标签
    
    msg_id = obj.get("message_id")
    if not msg_id:
        return [] # 没有核心消息ID的脏数据直接跳过

    uid = str(obj.get("conversation_id") or "")
    log_name = obj.get("user_name")
    log_dept = obj.get("user_department")

    # 【决策树】优先匹配权威 CSV，若无则利用日志现有字段动态兜底新人，防止降级为 unknown
    if uid and uid in user_map:
        name, dept_full, mgr = user_map[uid]
    elif log_name:
        name = str(log_name).strip()
        dept_full = str(log_dept).strip() if log_dept else "默认部门"
        l1 = get_l1_name(dept_full)
        mgr = L1_DEPT_CONFIG.get(l1, {}).get("mgr", "--")
    else:
        name = uid if uid else "unknown"
        dept_full = "默认部门"
        mgr = "--"

    tool_calls = obj.get("tool_calls") or []
    if not tool_calls:
        return []

    rows = []
    # 使用 enumerate 引入位置索引 idx，单轮查多个单号面单时指纹各异，全量精准保留不误杀
    for idx, tc in enumerate(tool_calls):
        tool_name = tc.get("tool_name", "")
        biz = None
        
        if tool_name == "quote_tool":
            biz = "询价"
        elif tool_name == "waybill_tool":
            biz = "面单推送"
        elif tool_name == "tracking_tool":
            biz = "轨迹查询"
        elif tool_name == "handoff_to_human":
            # 1. 优先提取 payload 里面的内容（兼容 4-24 等早期日志）
            payload = tc.get("payload", {})
            
            # 2. 从外层或者 payload 内层获取 ticket_created 状态
            ticket_created_outer = tc.get("ticket_created")
            ticket_created_inner = payload.get("ticket_created")
            
            # 3. 检查是否属于复用历史工单
            is_reused = tc.get("reused") is True or payload.get("reused") is True
            
            # 4. 核心判定逻辑：
            # 只要外层或内层的 ticket_created 为 True
            # 或者明确是复用工单 (is_reused)
            # 或者该工具调用成功 (tc.get("success") is True)，且不是明确失败
            if (ticket_created_outer is True) or (ticket_created_inner is True) or is_reused or (tc.get("success") is True):
                biz = "转人工成功"

        if biz:
            rows.append({
                "day_full": date_part,   # 用作高精过滤
                "date_md": date_md,     # 用作报表渲染
                "uid": uid,
                "name": name,
                "dept": dept_full,
                "mgr": mgr,
                "biz": biz,
                # 终极去重物理指纹：流式整行复写瞬间消除，多单号并发依靠 idx 完美共存
                "fingerprint": f"{msg_id}_{biz}_{idx}"
            })
    return rows

# ========== 修改点 2：重构数据计算与过滤网关 ==========
def generate_multi_report():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(HOST, username=USER, password=PWD, timeout=20)
        user_map = load_user_map_from_csv(ssh)

        start_date = datetime(2026, 4, 24)
        end_date = datetime.now()
        # 修正：今日成功转人工的基准改用标准全日期字符串比对
        today_full_str = end_date.strftime("%Y-%m-%d")

        raw_rows = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            cmd = f"find {CONVERSATIONS_DIR} -name '{date_str}.jsonl' -exec cat {{}} \\; 2>/dev/null"
            _, stdout, _ = ssh.exec_command(cmd)
            for line in stdout:
                rows = parse_audit_line_multi(line, user_map)
                raw_rows.extend(rows)
            current += timedelta(days=1)

        if not raw_rows:
            print("⚠️ 未统计到任何有效行为 (全量模式)")
            return

        # 依赖改良后的精细化指纹去重，杜绝数据虚高
        df = pd.DataFrame(raw_rows).drop_duplicates(subset=['fingerprint'])
        df['l2'] = df['dept'].apply(get_l2_name)
        df['l1'] = df['dept'].apply(get_l1_name)
        df['dept_short'] = df.apply(lambda r: f"{r['l1']}/{r['l2']}" if r['l2'] else r['l1'], axis=1)
        df = df[df['l1'] != '技术支持部']

        # 每日统计数据流组装
        daily_stats = []
        cum_users = set()
        cur = start_date
        while cur <= end_date:
            d_str = cur.strftime("%Y-%m-%d")
            # 修正：切换为完全年月日比对，从根源上斩断跨月Bug
            d_rows = df[df['day_full'] == d_str]
            d_uids = set(d_rows['uid'])
            new_u = d_uids - cum_users
            cum_users.update(d_uids)
            daily_stats.append({
                'date_full_std': d_str,  # 新增用于明细隔离的标准年月日钥匙
                'day': cur.strftime("%d"),
                'date_full': cur.strftime("%m-%d"),
                'dau': len(d_uids),
                'new': len(new_u),
                'cum': len(cum_users)
            })
            cur += timedelta(days=1)

        total_calls = len(df)
        total_trial = df['uid'].nunique()
        avg_dau = math.ceil(sum(s['dau'] for s in daily_stats) / len(daily_stats))
        
        # 修正：今日成功转人工判定卡位精准化
        today_handoff = len(df[(df['day_full'] == today_full_str) & (df['biz'] == '转人工成功')])
        
        active_rates = [(s['dau']/s['cum']) if s['cum']>0 else 0 for s in daily_stats]
        avg_active_rate = f"{round(sum(active_rates)/len(active_rates)*100,1)}%" if active_rates else "0%"

        md = f"# 一、核心数据概览 (全量匹配模式)\n"
        md += f"- 日均使用人数：{avg_dau}\n- 累计试用人数：{total_trial}\n- 功能调用总量：{total_calls}\n"
        md += f"- 日均活跃率：{avg_active_rate}\n- 今日成功转人工次数：{today_handoff}\n\n"
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

        md += "\n## 各部门使用情况明细(调用功能人数/部门人数)\n"
        for l1 in L1_ORDER:
            cfg = L1_DEPT_CONFIG[l1]
            l1_df = df[df['l1']==l1]
            if l1=="海外事业部" and len(l1_df)==0: continue
            mgr_str = cfg['mgr'] if cfg['mgr']!='--' else '—'
            md += f"\n**{l1}：{cfg['total']}人**\n\n"
            if l1 in ("平台中心","财务部","人力行政部"):
                call_users = l1_df['uid'].nunique()
                headcount = cfg['total']
                pct = f"{round(call_users/headcount*100,1)}%" if headcount else "-%"
                md += "| 一级部门 | 负责人 | 二级部门 | 部门人数 | 调用功能人数 | 部门使用人数占比 |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                md += f"| {l1} | {mgr_str} | — | {headcount} | {call_users} | {pct} |\n\n"
            else:
                all_l2 = L1_TO_L2.get(l1,[])
                l2_counts = l1_df.groupby('l2').size()
                l2_with = [l2 for l2 in l2_counts.index if l2!=""]
                l2_without = [l2 for l2 in all_l2 if l2 not in l2_with]
                l2_list = l2_with + l2_without
                md += "| 一级部门 | 负责人 | 二级部门 | 部门人数 | 调用功能人数 | 部门使用人数占比 |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                other_df = l1_df[l1_df['l2']==""]
                l2_total = sum(L2_HEADCOUNT.get(l2,0) for l2 in all_l2)
                other_head = cfg['total'] - l2_total
                if len(other_df)>0:
                    other_names = "、".join(other_df.drop_duplicates('uid')['name'].tolist())
                    o_users = other_df['uid'].nunique()
                    o_pct = f"{round(o_users/other_head*100,1)}%" if other_head else "-%"
                    md += f"| {l1} | {mgr_str} | {mgr_str}（直属，{other_names}） | {other_head} | {o_users} | {o_pct} |\n"
                for l2 in l2_list:
                    l2_df = l1_df[l1_df['l2']==l2]
                    head = L2_HEADCOUNT.get(l2,0)
                    u = l2_df['uid'].nunique()
                    pct = f"{round(u/head*100,1)}%" if head else "-%"
                    md += f"| {l1} | {mgr_str} | {l2} | {head} | {u} | {pct} |\n"
                md += "\n"

        # 修正：每日功能调用统计明细遍历
        md += "\n# 二、功能应用详情\n## 每日功能调用统计\n| 日期 | 询价调用次数 | 面单推送调用次数 | 轨迹查询调用次数 |\n| :--- | :--- | :--- | :--- |\n"
        for s in daily_stats:
            d_std = s['date_full_std']
            d_df = df[df['day_full'] == d_std] # 修正：改用标准年月日过滤
            md += f"| {s['date_full']} | {len(d_df[d_df['biz']=='询价'])} | {len(d_df[d_df['biz']=='面单推送'])} | {len(d_df[d_df['biz']=='轨迹查询'])} |\n"

        for b_name,icon in [("询价","🔍"),("面单推送","📦"),("轨迹查询","📍"),("转人工成功","👤")]:
            s_df = df[df['biz']==b_name]
            u,c = s_df['uid'].nunique(), len(s_df)
            p = round(c/total_calls*100,1) if total_calls else 0
            md += f"\n### {icon} {b_name}功能：累计 {u} 人使用，调用 {c} 次，占比 {p}%\n"
            md += "部门 TOP5\n| 部门 | 负责人 | 人数 | 次数 |\n| :--- | :--- | :--- | :--- |\n"
            dt_s = s_df.groupby(['dept_short','mgr']).agg({'uid':'nunique','biz':'count'}).sort_values('biz',ascending=False).head(5)
            for (d,m),r in dt_s.iterrows():
                md += f"| {d} | {m} | {r['uid']} | {r['biz']} |\n"
            md += f"\n人员 TOP10\n| 姓名 | 负责人 | 次数 |\n| :--- | :--- | :--- |\n"
            ut_s = s_df.groupby(['name','mgr']).size().sort_values(ascending=False).head(10)
            for (n,m),cnt in ut_s.items():
                md += f"| {n} | {m} | {cnt} |\n"

        # 修正：重点功能渗透情况明细遍历
        md += "\n---\n# 三、重点功能渗透情况\n| 日期 | 询价用户数 | 工单(转人工)用户数 |\n| :--- | :--- | :--- |\n"
        for s in daily_stats:
            d_std = s['date_full_std']
            d_df = df[df['day_full'] == d_std] # 修正：改用标准年月日过滤
            md += f"| {s['date_full']} | {d_df[d_df['biz']=='询价']['uid'].nunique()} | {d_df[d_df['biz']=='转人工成功']['uid'].nunique()} |\n"

        os.makedirs(os.path.dirname(LOCAL_REPORT), exist_ok=True)
        with open(LOCAL_REPORT, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ 全量匹配模式报告已生成：{LOCAL_REPORT}")

    finally:
        ssh.close()

if __name__ == "__main__":
    generate_multi_report()