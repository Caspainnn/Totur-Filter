"""Count field labels from allowlisted messages without exporting message values."""
from collections import Counter
import json
import os
from pathlib import Path
import re
import time

from src.wechat_source import read_messages


def main():
    allowlist = json.loads(Path('config/chat_allowlist.json').read_text(encoding='utf-8'))
    now = int(time.time())
    messages = read_messages(allowlist, now - 86400, now,
                             Path(os.environ['LOCALAPPDATA']) / 'WeChatTutorFilter' / 'temporary')
    labels = Counter()
    sampled = [message for message in messages if message['type'] == 1]
    for message in sampled:
        text = message['content']
        found = set(re.findall(r'【([\u4e00-\u9fff]{2,12})】', text))
        found.update(re.findall(r'(?m)^[^\u4e00-\u9fffA-Za-z0-9\n]*([\u4e00-\u9fff]{2,12})\s*[:：]', text))
        labels.update(found)
    print(json.dumps({'messages_sampled': len(sampled), 'window_hours': 24,
                      'label_message_counts': dict(labels.most_common())}, ensure_ascii=True))
    return 0 if len(sampled) >= 50 else 1


if __name__ == '__main__':
    raise SystemExit(main())
