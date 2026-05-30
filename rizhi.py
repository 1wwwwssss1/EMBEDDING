import paramiko
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("BAIYUN_HOST")
USER = os.getenv("BAIYUN_USER")
PWD  = os.getenv("BAIYUN_PWD")

CONVERSATIONS_DIR = "/root/BaiYun_Agent/logs/conversations/audit"
OUTPUT_FILE = "audit_log_output.csv"


def parse_line(line: str):
    try:
        obj = json.loads(line)
    except:
        return []

    datetime_str = obj.get("datetime", "")
    conv_id = str(obj.get("conversation_id", "")).strip()

    if not datetime_str or not conv_id:
        return []

    tool_calls = obj.get("tool_calls") or []
    intent = obj.get("intent", "")

    rows = []

    if tool_calls:
        # 只保留每个 tool_call 的 tool_name 字段
        simplified = [{"tool_name": tc.get("tool_name", "")} for tc in tool_calls if tc.get("tool_name")]
        if simplified:
            rows.append(
                f'"datetime": "{datetime_str}","conversation_id": "{conv_id}","tool_calls": {json.dumps(simplified, ensure_ascii=False)}'
            )
    elif intent == "闲聊":
        rows.append(
            f'"datetime": "{datetime_str}","conversation_id": "{conv_id}","intent": "闲聊"'
        )

    return rows


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(HOST, username=USER, password=PWD, timeout=20)
        print("✅ SSH 连接成功，开始拉取日志...")

        start_date = datetime(2026, 4, 24)
        end_date = datetime.now()

        all_rows = []
        current = start_date

        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            cmd = f"find {CONVERSATIONS_DIR} -name '{date_str}.jsonl' -exec grep -H '' {{}} \\; 2>/dev/null"
            _, stdout, _ = ssh.exec_command(cmd)

            for line_with_path in stdout:
                if ":" not in line_with_path:
                    continue
                _, line_content = line_with_path.split(":", 1)
                rows = parse_line(line_content)
                all_rows.extend(rows)

            print(f"  📅 {date_str} 处理完成，当前累计 {len(all_rows)} 条")
            current += timedelta(days=1)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for row in all_rows:
                f.write(row + "\n")

        print(f"\n🎉 完成！共写入 {len(all_rows)} 条记录 -> {OUTPUT_FILE}")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()