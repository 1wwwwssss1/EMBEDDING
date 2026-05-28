import paramiko
import re
import json
import pandas as pd
import math
import os
from datetime import datetime, timedelta

HOST = ""
USER = "user"
PWD  = ""

LOG_DIR = "/root/BaiYun_Agent/logs"
CONVERSATIONS_DIR = "/root/BaiYun_Agent/logs/conversations/audit"
CSV_PATH = "/home/user/results.csv"

LOCAL_REPORT = r"D:\yunxiaoxin\BaiYun_Final_Report.md"

#===== 一级部门配置：负责人、总人数 =====
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

#技术支持部整体排除
EXCLUDE_L1 = {"技术支持部"}

#===== 二级部门人数 =====
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

#===== 一级部门 → 二级部门列表 =====
L1_TO_L2 = {
    "产品中心":        ["快递产品部","专线产品部","海运产品部","陆运产品部","空派产品部","空运产品部","前线客服部"],
    "营销中心":        ["华中业务战区","机场管理部","机场一部","机场二部","机场三部","客服操作部"],
    "战略业务发展中心": ["销售一部","销售二部","销售三部","广州业务战区","上海业务战区","义乌业务战区","坂田业务战区","创新业务部"],
    "运作中心":        ["深圳运作部","广州运作部","义乌运作部","单证部","揽派部"],
    "品牌市场部":      ["新媒体运营组","市场策划组","品牌营销组"],
    "人力行政部":      ["管培生"],
    "海外事业部":      ["成都分公司","武汉分公司","汕头分公司"],
}

#===== 一级部门排列顺序 =====
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


def parse_jsonl_conversations(ssh, user_full_map, start_date, conversations_end):
    """
    读取 conversations/audit 中日期在 [start_date, conversations_end] 范围内的记录。
    conversations_end = agent.log最早日期 - 1天，随时间自动扩展，不重叠。
    用 conversation_id（企微user_id）匹配CSV，查不到用 user_name+user_department 兜底。
    一条命令批量 cat 所有文件，避免逐文件 SSH 开销。
    """
    cmd = f"find {CONVERSATIONS_DIR} -name '*.jsonl' | xargs cat 2>/dev/null"
    _, stdout, _ = ssh.exec_command(cmd)

    rows = []

    for raw_line in stdout:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        # ---- 时间戳 ----
        ts_str = str(obj.get("datetime") or obj.get("timestamp") or "")
        ts_m = re.search(r'(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})', ts_str)
        if not ts_m:
            continue
        date_str = ts_m.group(1)
        time_str = ts_m.group(2)
        log_dt = datetime.strptime(date_str, "%Y-%m-%d")

        # ✅ 只处理 [start_date, conversations_end] 范围，不与 agent.log 重叠
        if not (start_date <= log_dt <= conversations_end):
            continue

        full_ts = f"{date_str} {time_str}"
        day_str = date_str[8:10]

        # ---- 用户信息：conversation_id 就是企微 user_id ----
        uid = str(obj.get("conversation_id") or "").strip()
        user_name = str(obj.get("user_name") or "").strip()
        user_dept = str(obj.get("user_department") or "").strip()

        if not uid and not user_name:
            continue

        uid_key = uid if uid else user_name

        if uid and uid in user_full_map:
            u_info = user_full_map[uid]
        elif user_name:
            dept = user_dept if user_dept else "默认部门"
            l1 = get_l1_name(dept)
            mgr = L1_DEPT_CONFIG.get(l1, {}).get("mgr", "--")
            u_info = [user_name, dept, mgr]
        else:
            u_info = [uid_key, "默认部门", "--"]

        # ---- 业务识别 ----
        tool_calls = obj.get("tool_calls") or []
        tool_names = [
            (tc.get("tool_name") or tc.get("name") or "")
            if isinstance(tc, dict) else ""
            for tc in tool_calls
        ]
        intent_val = str(obj.get("intent") or "")

        biz = None
        if any("quote" in n for n in tool_names):
            biz = "询价"
        elif any("track" in n for n in tool_names):
            biz = "轨迹查询"
        elif any("waybill" in n for n in tool_names):
            biz = "面单推送"
        elif "转人工" in intent_val:
            biz = "转人工"

        if biz:
            rows.append({
                "day": day_str,
                "day_full": date_str,
                "uid": uid_key,
                "name": u_info[0],
                "dept": u_info[1],
                "mgr": u_info[2],
                "biz": biz,
                "fingerprint": f"{full_ts}_{uid_key}_{biz}",
            })

    print(f"   conversations 归档解析到 {len(rows)} 条记录（{start_date.date()} 至 {conversations_end.date()}）")
    return rows

def generate_strict_report():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(HOST, username=USER, password=PWD, timeout=20)
        user_full_map = load_user_map_from_csv(ssh)

        # ✅ 时间范围：4月24日 到 今天
        start_date = datetime(2026, 4, 24)
        end_date = datetime.now()
        today_str = end_date.strftime("%d")

        # 获取日志文件
        _, stdout, _ = ssh.exec_command(f"ls -1tr {LOG_DIR}/agent.log*")
        files = [f for f in stdout.read().decode().splitlines() if not f.endswith('.gz')]

        # ✅ 解析 agent.log 最早覆盖日期，conversations 只读这个日期之前的数据，避免重叠
        agentlog_earliest = end_date
        for f in files:
            m = re.search(r'agent\.log\.(\d{4}-\d{2}-\d{2})', f)
            if m:
                d = datetime.strptime(m.group(1), "%Y-%m-%d")
                if d < agentlog_earliest:
                    agentlog_earliest = d
        conversations_end = agentlog_earliest - timedelta(days=1)
        print(f"📅 agent.log 最早日期: {agentlog_earliest.date()}，conversations 读取截止: {conversations_end.date()}")

        raw_rows = []
        pending_handoff = {}

        for f_path in files:
            _, f_out, _ = ssh.exec_command(f"cat {f_path}")
            current_uid = None

            for line in f_out:
                ts_m = re.search(r'(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})', line)
                if not ts_m:
                    continue

                date_str = ts_m.group(1)
                full_ts = f"{date_str} {ts_m.group(2)}"

                log_dt = datetime.strptime(date_str, "%Y-%m-%d")

                if not (start_date <= log_dt <= end_date):
                    continue

                day_str = date_str[8:10]

                uid_m = re.search(r'Resolved qywx user id:\s*(\d+)', line)
                if uid_m:
                    current_uid = uid_m.group(1)

                if not current_uid:
                    continue

                u_info = user_full_map.get(current_uid, [current_uid, "默认部门", "--"])
                biz = None

                if "agent.tools.quote_tool" in line and "request(async)" in line:
                    biz = '询价'
                elif 'quote_tool' in line and "tool_calls=[" in line:
                    biz = '询价'
                elif "api.track.service" in line and "地理编码线程已启动" in line:
                    biz = '轨迹查询'
                elif 'track' in line and "tool_calls=[" in line:
                    biz = '轨迹查询'
                elif 'waybill' in line and "tool_calls=[" in line:
                    biz = '面单推送'
                elif "intents=[" in line and "'转人工'" in line:
                    if log_dt < datetime(2026, 4, 26):
                        biz = '转人工'
                    else:
                        pending_handoff[current_uid] = True
                        continue

                if log_dt >= datetime(2026, 4, 26) and pending_handoff.get(current_uid):
                    if ("tracking_tool" in line or "api.track.service" in line):
                        biz = '转人工'
                        pending_handoff[current_uid] = False

                if biz:
                    raw_rows.append({
                        'day': day_str,
                        'day_full': date_str,
                        'uid': current_uid,
                        'name': u_info[0],
                        'dept': u_info[1],
                        'mgr': u_info[2],
                        'biz': biz,
                        'fingerprint': f"{full_ts}_{current_uid}_{biz}"
                    })

        # ✅ 补充：从 conversations/audit/*.jsonl 中读取归档数据
        print("📂 正在读取 conversations 归档日志...")
        archive_rows = parse_jsonl_conversations(ssh, user_full_map, start_date, conversations_end)
        print(f"   归档日志共解析到 {len(archive_rows)} 条记录")
        raw_rows.extend(archive_rows)

        if not raw_rows:
            print("⚠️ 未统计到任何有效行为，请检查日志格式。")
            return

        df = pd.DataFrame(raw_rows).drop_duplicates(subset=['fingerprint'])

        df['l2'] = df['dept'].apply(get_l2_name)
        df['l1'] = df['dept'].apply(get_l1_name)

        def make_dept_short(row):
            if row['l2']:
                return f"{row['l1']}/{row['l2']}"
            return row['l1']
        df['dept_short'] = df.apply(make_dept_short, axis=1)

        df = df[df['l1'] != '技术支持部']

        # ✅ 动态日期列表
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
        today_handoff_count = len(df[(df['day'] == today_str) & (df['biz'] == '转人工')])

        active_rates = [
            (s['dau'] / s['cum']) if s['cum'] > 0 else 0
            for s in daily_stats
        ]
        avg_active_rate = f"{round(sum(active_rates) / len(active_rates) * 100, 1)}%" if active_rates else "0%"

        # ===== 报告 =====
        md = f"# 一、核心数据概览\n"
        md += f"- 日均使用人数：{avg_dau}\n"
        md += f"- 累计试用人数：{total_trial}\n"
        md += f"- 功能调用总量：{total_calls}\n"
        md += f"- 日均活跃率：{avg_active_rate}\n"
        md += f"- 今日成功转人工次数：{today_handoff_count}\n\n"

        md += "| 日期 | 日活跃用户 | 当日新增 | 累计人数 |\n| :--- | :--- | :--- | :--- |\n"
        for s in daily_stats:
            md += f"| {s['date_full']} | {s['dau']} | {s['new']} | {s['cum']} |\n"

        md += "\n部门调用 TOP 5\n| 排名 | 部门 | 部门负责人 | 次数 |\n| :--- | :--- | :--- | :--- |\n"
        dept_top = df.groupby(['dept_short', 'mgr']).size().reset_index(name='c').sort_values('c', ascending=False).head(5)
        for i, r in enumerate(dept_top.itertuples(), 1):
            md += f"| {i} | {r.dept_short} | {r.mgr} | {r.c} |\n"

        md += "\n人均 TOP 15\n| 排名 | 姓名 | 部门 | 部门负责人 | 调用次数 |\n| :--- | :--- | :--- | :--- | :--- |\n"
        user_top = df.groupby(['name', 'dept_short', 'mgr']).size().reset_index(name='c').sort_values('c', ascending=False).head(15)
        for i, r in enumerate(user_top.itertuples(), 1):
            md += f"| {i} | {r.name} | {r.dept_short} | {r.mgr} | {r.c} |\n"

        md += "\n## 各部门使用情况明细(调用功能人数/部门人数)\n"

        for l1 in L1_ORDER:
            cfg = L1_DEPT_CONFIG[l1]
            l1_df = df[df['l1'] == l1]

            if l1 == "海外事业部" and len(l1_df) == 0:
                continue

            mgr_str = cfg['mgr'] if cfg['mgr'] != '--' else '—'
            md += f"\n**{l1}：{cfg['total']}人**\n\n"

            if l1 in ("平台中心", "财务部", "人力行政部"):
                call_users = l1_df['uid'].nunique()
                headcount = cfg['total']
                user_pct = f"{round(call_users/headcount*100, 1)}%" if headcount > 0 else "-%"
                md += f"| 一级部门 | 负责人 | 二级部门 | 部门人数 | 调用功能人数 | 部门使用人数占比 |\n"
                md += f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                md += f"| {l1} | {mgr_str} | — | {headcount} | {call_users} | {user_pct} |\n\n"
            else:
                all_l2 = L1_TO_L2.get(l1, [])
                l2_counts = l1_df.groupby('l2').size().sort_values(ascending=False)
                l2_with_data = [l2 for l2 in l2_counts.index if l2 != ""]
                l2_no_data = [l2 for l2 in all_l2 if l2 not in l2_with_data]
                l2_list = l2_with_data + l2_no_data

                md += f"| 一级部门 | 负责人 | 二级部门 | 部门人数 | 调用功能人数 | 部门使用人数占比 |\n"
                md += f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"

                other_df = l1_df[l1_df['l2'] == ""]
                l2_total_headcount = sum(L2_HEADCOUNT.get(l2, 0) for l2 in all_l2)
                other_headcount = cfg['total'] - l2_total_headcount
                if len(other_df) > 0:
                    other_names = "、".join(other_df.drop_duplicates('uid')['name'].tolist())
                    o_users = other_df['uid'].nunique()
                    o_user_pct = f"{round(o_users/other_headcount*100, 1)}%" if other_headcount > 0 else "-%"
                    md += f"| {l1} | {mgr_str} | {mgr_str}（直属，{other_names}） | {other_headcount} | {o_users} | {o_user_pct} |\n"

                for l2 in l2_list:
                    l2_df = l1_df[l1_df['l2'] == l2]
                    headcount = L2_HEADCOUNT.get(l2, 0)
                    call_users = l2_df['uid'].nunique()
                    user_pct = f"{round(call_users/headcount*100, 1)}%" if headcount > 0 else "-%"
                    md += f"| {l1} | {mgr_str} | {l2} | {headcount} | {call_users} | {user_pct} |\n"

                md += "\n"

        md += "\n# 二、功能应用详情\n"
        md += "\n## 每日功能调用统计\n"
        md += "| 日期 | 询价调用次数 | 面单推送调用次数 | 轨迹查询调用次数 |\n"
        md += "| :--- | :--- | :--- | :--- |\n"

        for s in daily_stats:
            d = s['day']
            d_df = df[df['day'] == d]
            quote_count = len(d_df[d_df['biz'] == '询价'])
            waybill_count = len(d_df[d_df['biz'] == '面单推送'])
            track_count = len(d_df[d_df['biz'] == '轨迹查询'])
            md += f"| {s['date_full']} | {quote_count} | {waybill_count} | {track_count} |\n"

        for b_name, icon in [("询价", "🔍"), ("面单推送", "📦"), ("轨迹查询", "📍"), ("转人工", "👤")]:
            s_df = df[df['biz'] == b_name]
            u, c = s_df['uid'].nunique(), len(s_df)
            p = round(c/total_calls*100, 1) if total_calls > 0 else 0

            md += f"\n### {icon} {b_name}功能：累计 {u} 人使用，调用 {c} 次，占比 {p}%\n"
            md += f"部门 TOP5\n| 部门 | 负责人 | 人数 | 次数 |\n| :--- | :--- | :--- | :--- |\n"
            dt_s = s_df.groupby(['dept_short', 'mgr']).agg({'uid':'nunique', 'biz':'count'}).sort_values('biz', ascending=False).head(5)
            for (d, m), r in dt_s.iterrows():
                md += f"| {d} | {m} | {r['uid']} | {r['biz']} |\n"

            md += f"\n人员 TOP10\n| 姓名 | 负责人 | 次数 |\n| :--- | :--- | :--- |\n"
            ut_s = s_df.groupby(['name', 'mgr']).size().sort_values(ascending=False).head(10)
            for (n, m), count in ut_s.items():
                md += f"| {n} | {m} | {count} |\n"

        md += "\n---\n# 三、重点功能渗透情况\n| 日期 | 询价用户数 | 工单(转人工)用户数 |\n| :--- | :--- | :--- |\n"
        for s in daily_stats:
            d = s['day']
            d_df = df[df['day'] == d]
            md += f"| {s['date_full']} | {d_df[d_df['biz']=='询价']['uid'].nunique()} | {d_df[d_df['biz']=='转人工']['uid'].nunique()} |\n"

        os.makedirs(os.path.dirname(LOCAL_REPORT), exist_ok=True)
        with open(LOCAL_REPORT, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"✅ 报告已生成：{LOCAL_REPORT}")

    finally:
        ssh.close()

if __name__ == "__main__":
    generate_strict_report()