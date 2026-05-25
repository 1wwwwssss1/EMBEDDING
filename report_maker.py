import paramiko
import re
import pandas as pd
import math
import os
from datetime import datetime, timedelta

HOST = "8.135.23.169"
USER = "user"
PWD  = "baiyun56.com"

LOG_DIR = "/root/BaiYun_Agent/logs"
CSV_PATH = "/home/user/results.csv"

LOCAL_REPORT = r"D:\yunxiaoxin\BaiYun_Final_Report.md"

DEPT_MANAGER_MAP = {
    "产品中心/空派产品部": "向启胜",
    "营销中心/客服操作部": "曾桂文",
    "营销中心/机场一部": "曾桂文",
    "营销中心/机场二部": "曾桂文",
    "营销中心/机场三部": "曾桂文",
    "产品中心/前线客服部": "向启胜",
    "技术支持部/AI项目组": "唐健新",
    "品牌市场部/品牌营销组": "罗群勇",
    "战略业务发展中心/销售一部": "陈旭东",
    "战略业务发展中心/义乌业务战区/辅助部": "陈旭东",
}

def normalize_dept(dept: str) -> str:
    if not dept:
        return "默认部门"
    parts = [p.strip() for p in dept.split("/") if p.strip()]
    for i, p in enumerate(parts):
        if "部" in p:
            if i > 0:
                return parts[i-1] + "/" + p
            else:
                return p
    return dept

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

        dept_for_mgr = normalize_dept(dept)
        mgr = DEPT_MANAGER_MAP.get(dept_for_mgr, "--")
        user_map[uid] = [name, dept, mgr]

    return user_map

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

        raw_rows = []
        pending_handoff = {}

        for f_path in files:
            _, f_out, _ = ssh.exec_command(f"cat {f_path}")
            current_uid = None

            for line in f_out:
                # ✅ 解析完整日期
                ts_m = re.search(r'(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})', line)
                if not ts_m:
                    continue

                date_str = ts_m.group(1)
                full_ts = f"{date_str} {ts_m.group(2)}"

                log_dt = datetime.strptime(date_str, "%Y-%m-%d")

                # ✅ 过滤 4.24 之后
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

                # 询价
                if "agent.tools.quote_tool" in line and "request(async)" in line:
                    biz = '询价'
                elif 'quote_tool' in line and "tool_calls=[" in line:
                    biz = '询价'

                # 轨迹查询
                elif "api.track.service" in line and "地理编码线程已启动" in line:
                    biz = '轨迹查询'
                elif 'track' in line and "tool_calls=[" in line:
                    biz = '轨迹查询'

                # 面单推送
                elif 'waybill' in line and "tool_calls=[" in line:
                    biz = '面单推送'

                # 转人工
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
                        'day_full': date_str,   # ✅ 新增（不影响原逻辑）
                        'uid': current_uid,
                        'name': u_info[0],
                        'dept': u_info[1],
                        'mgr': u_info[2],
                        'biz': biz,
                        'fingerprint': f"{full_ts}_{current_uid}_{biz}"
                    })

        if not raw_rows:
            print("⚠️ 未统计到任何有效行为，请检查日志格式。")
            return

        df = pd.DataFrame(raw_rows).drop_duplicates(subset=['fingerprint'])

        # 剔除AI项目组
        EXCLUDE_DEPTS = [
            "百运网/技术支持部/AI项目组",
            "百运网/技术支持部/AI产品与项目组",
            "百运网/技术支持部/AI算法组",
            "百运网/技术支持部/软件开发组",
            "百运网/技术支持部/数据质量与测试组",
            "百运网/技术支持部/数据科学组",
            "百运网/技术支持部/其他",
        ]

        df = df[~df['dept'].isin(EXCLUDE_DEPTS)]

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

        # ===== 报告（完全没改格式）=====
        md = f"# 一、核心数据概览\n"
        md += f"- 日均使用人数：{avg_dau}\n"
        md += f"- 累计试用人数：{total_trial}\n"
        md += f"- 功能调用总量：{total_calls}\n"
        md += f"- 日均活跃率：{avg_active_rate}\n"
        md += f"- 今日成功转人工次数：{today_handoff_count}\n\n"

        md += "| 日期 | 日活跃用户 | 当日新增 | 累计去重人数 |\n| :--- | :--- | :--- | :--- |\n"
        for s in daily_stats:
            md += f"| {s['date_full']} | {s['dau']} | {s['new']} | {s['cum']} |\n"

        md += "\n**部门调用 TOP 5**\n| 排名 | 部门 | 部门负责人 | 次数 | 占比 |\n| :--- | :--- | :--- | :--- | :--- |\n"
        dept_top = df.groupby(['dept', 'mgr']).size().reset_index(name='c').sort_values('c', ascending=False).head(5)
        for i, r in enumerate(dept_top.itertuples(), 1):
            md += f"| {i} | {r.dept} | {r.mgr} | {r.c} | {round(r.c/total_calls*100, 1)}% |\n"

        md += "\n**人均 TOP 15**\n| 排名 | 姓名 | 部门 | 部门负责人 | 调用次数 |\n| :--- | :--- | :--- | :--- | :--- |\n"
        user_top = df.groupby(['name', 'dept', 'mgr']).size().reset_index(name='c').sort_values('c', ascending=False).head(15)
        for i, r in enumerate(user_top.itertuples(), 1):
            md += f"| {i} | {r.name} | {r.dept} | {r.mgr} | {r.c} |\n"

        md += "\n## 二、功能应用详情\n"
        for b_name, icon in [("询价", "🔍"), ("面单推送", "📦"), ("轨迹查询", "📍"), ("转人工", "👤")]:
            s_df = df[df['biz'] == b_name]
            u, c = s_df['uid'].nunique(), len(s_df)
            p = round(c/total_calls*100, 1) if total_calls > 0 else 0

            md += f"\n### {icon} {b_name}功能：累计 {u} 人使用，调用 {c} 次，占比 {p}%\n"
            md += f"**部门 TOP5**\n| 部门 | 负责人 | 人数 | 次数 |\n| :--- | :--- | :--- | :--- |\n"
            dt_s = s_df.groupby(['dept', 'mgr']).agg({'uid':'nunique', 'biz':'count'}).sort_values('biz', ascending=False).head(5)
            for (d, m), r in dt_s.iterrows():
                md += f"| {d} | {m} | {r['uid']} | {r['biz']} |\n"

            md += f"\n**人员 TOP10**\n| 姓名 | 负责人 | 次数 |\n| :--- | :--- | :--- |\n"
            ut_s = s_df.groupby(['name', 'mgr']).size().sort_values(ascending=False).head(10)
            for (n, m), count in ut_s.items():
                md += f"| {n} | {m} | {count} |\n"

        md += "\n---\n## 三、重点功能渗透情况\n| 日期 | 询价用户数 | 工单(转人工)用户数 |\n| :--- | :--- | :--- |\n"
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