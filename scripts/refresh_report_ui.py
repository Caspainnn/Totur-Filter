"""Rerender the already exported snapshot; never read WeChat or request maps."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.report import render_report
from src.run_filter import load_preferences
from src.user_settings import preference_snapshot
from src.filter_rules import classify_order, normalize_order, address_text, schedule_text, parse_grade


def refresh():
    metadata = json.loads((ROOT / 'scheduled-once-result.json').read_text(encoding='utf-8-sig'))
    if metadata.get('status') != 'OK':
        raise RuntimeError('The last exported run was not successful; report left unchanged.')
    private_root = Path(os.environ['LOCALAPPDATA']) / 'WeChatTutorFilter' / 'accounts'
    # Match the exported generation, rather than silently substituting a newer run.
    snapshots = list(private_root.glob(f'*/run-{int(metadata["generated_at"])}-*/orders.json'))
    if len(snapshots) != 1:
        raise RuntimeError('Cannot uniquely locate the exported snapshot; report left unchanged.')
    orders = json.loads(snapshots[0].read_text(encoding='utf-8'))
    counts = {status: sum(order['status'] == status or status == 'rejected' and 'closed' not in metadata['counts'] and order['status'] == 'closed' for order in orders) for status in metadata['counts']}
    if counts != metadata['counts']:
        raise RuntimeError('Snapshot does not match exported counts; report left unchanged.')
    destination = ROOT / 'tutor-report.html'
    # Refresh editable values without claiming old order evaluations were rerun.
    preferences = load_preferences()
    repaired = 0
    for index, order in enumerate(orders):
        if not re.search(r'【(?:上课区域|上课时段|预算范围|年级科目)】', order['raw']):
            continue
        normalized = normalize_order(order['raw'])
        fields = order.get('fields', {})
        if fields.get('address') == address_text(normalized) and fields.get('schedule') == schedule_text(normalized) and fields.get('grade') == parse_grade(normalized)[0]:
            continue
        corrected = classify_order(order, preferences)
        # A route to an incorrectly extracted address cannot verify the corrected order.
        if (fields.get('address') == corrected['fields'].get('address')
                and fields.get('schedule') == corrected['fields'].get('schedule') and fields.get('commute')):
            corrected['fields']['commute'] = fields['commute']
        orders[index] = corrected
        repaired += 1
    if repaired:
        metadata['counts'] = {status: sum(o['status'] == status or status == 'rejected' and o['status'] == 'closed' for o in orders) for status in metadata['counts'] if status != 'closed'}
    metadata['ui_preferences'] = preference_snapshot(preferences)
    metadata['preference_overrides'] = preferences.get('user_preference_overrides', {})
    metadata['rejection_feedback'] = preferences.get('rejection_feedback', [])
    metadata['closed_order_keys'] = sorted(set(preferences.get('closed_order_keys', []) + preferences.get('closed_order_ids', [])))
    markup = render_report(orders, metadata)
    temporary = destination.with_suffix('.html.tmp')
    temporary.write_text(markup, encoding='utf-8', newline='\n')
    temporary.replace(destination)
    print(f'Rerendered {len(orders)} existing orders; repaired {repaired} legacy field extractions; original generation time retained. No WeChat or map calls.')


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    refresh()
