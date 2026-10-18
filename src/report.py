"""Static private HTML. Every user-controlled value is escaped."""
from datetime import datetime, timedelta, timezone
from html import escape
import json
import base64
import hashlib
import re
from src.commute import FAILURE_LABELS
from src.filter_rules import order_identifier, SUBJECTS
from src.user_settings import feedback_rows, FEEDBACK_FIELDS, GRADE_GROUPS
from pathlib import Path

ZONE = timezone(timedelta(hours=8))
LABELS = {'recommended': '推荐', 'needs_confirmation': '待确认', 'rejected': '不匹配', 'parse_failed': '解析失败'}
DELETE_ICON = re.search(r"const intervalDeleteIcon='([^']+)';", Path(__file__).with_name('settings_workspace.js').read_text(encoding='utf-8')).group(1)

CLOSE_SCRIPT = """(() => {
const key = 'wechat-tutor-filter.closed.v1';
let saved;
try { saved = new Set(JSON.parse(localStorage.getItem(key) || '[]')); } catch { saved = new Set(); }
try { JSON.parse(document.getElementById('saved-closed-keys').textContent).forEach(id => saved.add(id)); } catch {}
const target = document.getElementById('rejected');
let userState = {rejection_feedback: [], preference_overrides: {}, deleted_feedback_rules: [], edited_preference_paths: [], base_revision: ''};
try { userState = {...userState, ...JSON.parse(document.getElementById('user-settings-data').textContent)}; } catch {}
try {
  const draft = JSON.parse(localStorage.getItem('wechat-tutor-filter.feedback.v1') || 'null');
  if (draft && draft.base_revision === userState.base_revision) userState = {...userState, ...draft};
} catch {}
if (typeof window !== 'undefined') window.tutorUserState = userState;
function persistUserState() {
  try { localStorage.setItem('wechat-tutor-filter.feedback.v1', JSON.stringify(userState)); } catch {}
}
function mergeSavedSettings(existing) {
  if (!existing || !Array.isArray(existing.closed_order_keys)) {
    const error = new Error('Invalid existing file'); error.userMessage = '所选文件不是有效的熄单记录，未覆盖。'; throw error;
  }
  const mergedFeedback = new Map();
  for (const item of [...(existing.rejection_feedback || []), ...userState.rejection_feedback]) {
    if (!userState.deleted_feedback_rules.some(deleted => deleted.field === item.field && deleted.value === item.value))
      mergedFeedback.set(JSON.stringify([item.order_key, item.field, item.value]), item);
  }
  const overrides = {...(existing.preference_overrides || {})};
  for (const path of userState.edited_preference_paths) {
    const before = window.tutorPreferenceEditor?.baseline[path];
    if (Object.hasOwn(overrides, path) && JSON.stringify(overrides[path]) !== JSON.stringify(before)
        && JSON.stringify(overrides[path]) !== JSON.stringify(userState.preference_overrides[path])) {
      const error = new Error('Stale preference edit'); error.userMessage = '文件中的偏好已被其他页面修改，未覆盖。请生成最新报告后再编辑。'; throw error;
    }
    overrides[path] = userState.preference_overrides[path];
  }
  return {version: 2, closed_order_keys: [...new Set([...existing.closed_order_keys, ...saved])].sort(),
    rejection_feedback: [...mergedFeedback.values()], preference_overrides: overrides};
}
const localSaveToken = document.querySelector?.('meta[name="tutor-local-token"]')?.content;
let saveInProgress = false;
async function localSettings(method, payload) {
  let response;
  try {
    response = await fetch('/api/settings', {method, headers: {'X-Tutor-Token': localSaveToken, 'Content-Type': 'application/json'},
      ...(payload ? {body: JSON.stringify(payload)} : {})});
  } catch {
    const error = new Error('Service unavailable'); error.userMessage = '本机保存服务未连接，未保存。请让 Agent 重新打开本地报告。'; throw error;
  }
  const data = await response.json();
  if (!response.ok) {
    const error = new Error('Local save rejected');
    error.userMessage = response.status === 409 ? '设置文件已变化或内容无效，未覆盖。请重新加载最新设置后再保存。' : '本机保存失败，未写入设置，请检查服务与设置内容。';
    throw error;
  }
  return data;
}
let saveDirectory;
const directoryDb = typeof indexedDB === 'undefined' ? Promise.resolve(null) : new Promise(resolve => {
  const request = indexedDB.open('wechat-tutor-filter-settings', 1);
  request.onupgradeneeded = () => request.result.createObjectStore('settings');
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => resolve(null);
});
directoryDb.then(db => {
  if (!db) return;
  const request = db.transaction('settings').objectStore('settings').get('save-directory');
  request.onsuccess = () => { saveDirectory = request.result; };
});
async function selectDirectory() {
  document.getElementById('close-feedback').textContent = '请选择 当前项目，之后会记住该目录。';
  const handle = await window.showDirectoryPicker({id: 'tutor-project-directory', mode: 'readwrite'});
  saveDirectory = handle;
  const db = await directoryDb;
  if (db) await new Promise((resolve, reject) => {
    const transaction = db.transaction('settings', 'readwrite');
    transaction.objectStore('settings').put(handle, 'save-directory');
    transaction.oncomplete = resolve;
    transaction.onerror = reject;
  });
  return handle;
}
function counts() {
  document.querySelectorAll('section').forEach(section => {
    const count = section.querySelectorAll('article').length;
    section.querySelector('h2 span').textContent = count;
    const empty = section.querySelector('.empty');
    if (empty) empty.hidden = count > 0;
  });
}
function move(card) {
  target.appendChild(card);
  card.querySelector('.close-order')?.remove();
  card.querySelector('.shortlist-order')?.remove();
  card.querySelector('.check-grid')?.remove();
  card.querySelector('.dismiss-order')?.remove();
  const reason = [...userState.rejection_feedback].reverse().find(item => item.order_key === card.dataset.orderKey);
  card.querySelector('.reason').textContent = reason ? reason.reason + '；保存后按同字段内容排除后续订单' : '单已被抢走';
  if (card.querySelectorAll) card.querySelectorAll('.feedback-reject').forEach(button => {button.disabled = true;});
}
document.querySelectorAll('article[data-order-key]').forEach(card => {
  if (saved.has(card.dataset.orderKey)) move(card);
});
counts();
document.addEventListener('click', async event => {
  if (event.target.closest('#save-closed')) {
    const feedback = document.getElementById('close-feedback');
    if (saveInProgress) return;
    saveInProgress = true;
    try {
      if (window.tutorPreferenceEditor) userState.preference_overrides = window.tutorPreferenceEditor.collect();
      persistUserState();
      let content = JSON.stringify({version: 2, closed_order_keys: [...saved].sort(), rejection_feedback: userState.rejection_feedback, preference_overrides: userState.preference_overrides}, null, 2);
      if (localSaveToken || window.showSaveFilePicker) {
        if (localSaveToken) {
          const existing = await localSettings('GET');
          const result = await localSettings('POST', {revision: existing.revision, settings: mergeSavedSettings(existing.settings)});
          content = JSON.stringify(result.settings);
        } else {
        if (!saveDirectory && window.showDirectoryPicker) await selectDirectory();
        const options = {id: 'tutor-closed-save', suggestedName: 'manual_closed_orders.json', types: [{description: '熄单记录', accept: {'application/json': ['.json']}}]};
        if (saveDirectory) options.startIn = saveDirectory;
        const handle = await window.showSaveFilePicker(options);
        const file = await handle.getFile();
        if (file.size) {
          let existing;
          try { existing = JSON.parse(await file.text()); }
          catch { const error = new Error('Bad JSON'); error.userMessage = '所选文件内容无效，未覆盖。'; throw error; }
          content = JSON.stringify(mergeSavedSettings(existing), null, 2);
        }
        const writable = await handle.createWritable();
        await writable.write(content);
        await writable.close();
        }
        const written = JSON.parse(content);
        userState.rejection_feedback = written.rejection_feedback;
        userState.preference_overrides = written.preference_overrides;
        userState.deleted_feedback_rules = [];
        userState.edited_preference_paths = [];
        written.closed_order_keys.forEach(id => saved.add(id));
        window.tutorPreferenceEditor?.updateBaseline(written.preference_overrides);
        userState.saved_preference_baseline = {...window.tutorPreferenceEditor?.baseline};
        persistUserState();
        document.dispatchEvent(new CustomEvent('tutor-settings-saved'));
        feedback.textContent = localSaveToken ? '已保存到当前项目，下次筛选生效。' : '已保存熄单、反馈理由和偏好。文件需位于项目根目录，下次筛选生效。';
      } else {
        const url = URL.createObjectURL(new Blob([content], {type: 'application/json'}));
        const link = document.createElement('a');
        link.href = url;
        link.download = 'manual_closed_orders.json';
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        feedback.textContent = '已导出：请将文件保存到 当前项目 根目录，下次筛选永久生效。';
      }
    } catch (error) { feedback.textContent = error.name === 'AbortError' ? '已取消保存，浏览器标记仍保留。' : (error.userMessage || '保存失败，请重试。'); }
    finally { saveInProgress = false; }
    return;
  }
  const feedbackButton = event.target.closest('.feedback-reject');
  const button = feedbackButton || event.target.closest('.close-order');
  if (!button) return;
  const card = button.closest('article');
  if (feedbackButton) {
    const item = {order_key: card.dataset.orderKey, field: button.dataset.feedbackField,
      value: button.dataset.feedbackValue, reason: button.dataset.feedbackReason, created_at: new Date().toISOString()};
    if (!userState.rejection_feedback.some(row => row.order_key === item.order_key && row.field === item.field && row.value === item.value)) userState.rejection_feedback.push(item);
    persistUserState();
  }
  saved.add(card.dataset.orderKey);
  try { localStorage.setItem(key, JSON.stringify([...saved])); }
  catch { document.getElementById('close-feedback').textContent = '已移入不匹配；浏览器无法保存标记，刷新后可能恢复。'; }
  document.querySelectorAll('article[data-order-key]').forEach(candidate => {
    if(candidate.dataset.orderKey!==card.dataset.orderKey)return;
    if(candidate.id?.startsWith('shortlist-'))candidate.remove();else move(candidate);
  });
  counts();
  if (typeof CustomEvent === 'function') document.dispatchEvent(new CustomEvent('tutor-order-closed', {detail: card.dataset.orderKey}));
});
})();"""

CLOSE_SCRIPT += """
/* Shortlist */
(() => {
const storageKey = 'wechat-tutor-filter.shortlist.v1';
let chosen;
try { chosen = new Set(JSON.parse(localStorage.getItem(storageKey) || '[]')); } catch { chosen = new Set(); }
const section = document.getElementById('shortlist');
const container = section.querySelector('.shortlist-cards');
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify([...chosen])); }
  catch { document.getElementById('close-feedback').textContent = '待选项已更新，但浏览器无法保存，刷新后可能恢复。'; }
}
function render() {
  container.replaceChildren();
  const added = new Set();
  document.querySelectorAll('#recommended article, #needs_confirmation article').forEach(card => {
    const id = card.dataset.orderKey;
    const selected = chosen.has(id);
    card.classList.toggle('shortlisted', selected);
    const button = card.querySelector('.shortlist-order');
    if (button) { button.setAttribute('aria-pressed', String(selected)); button.title = selected ? '移出待选项' : '加入待选项'; }
    if (!selected || added.has(id)) return;
    added.add(id);
    const copy = card.cloneNode(true);
    copy.id = 'shortlist-' + card.id;
    copy.querySelector('.close-order')?.remove();
    copy.querySelector('.shortlist-order')?.remove();
    copy.querySelectorAll('.feedback-reject:not(.dismiss-order)').forEach(button => button.remove());
    copy.querySelector('.feedback-help')?.remove();
    const remove = document.createElement('button');
    remove.className = 'unshortlist-order';
    remove.type = 'button';
    remove.textContent = '移出待选';
    copy.appendChild(remove);
    container.appendChild(copy);
  });
  section.querySelector('h2 span').textContent = added.size;
  section.querySelector('.empty').hidden = added.size > 0;
  document.getElementById('jump-shortlist').textContent = '🛒 ' + added.size;
}
document.addEventListener('click', event => {
  if (event.target.closest('#jump-shortlist')) {
    location.hash = 'shortlist';
    section.scrollIntoView({block: 'start'});
    section.querySelector('h2').focus();
    return;
  }
  const button = event.target.closest('.shortlist-order, .unshortlist-order');
  if (button) {
    const id = button.closest('article').dataset.orderKey;
    if (chosen.has(id)) chosen.delete(id); else chosen.add(id);
    persist(); render();
  }
});
document.addEventListener('tutor-order-closed', event => { chosen.delete(event.detail); persist(); render(); });
render();
})();"""

CLOSE_SCRIPT += '\n/* Preference editor */\n' + Path(__file__).with_name('preference_editor.js').read_text(encoding='utf-8')
CLOSE_SCRIPT += '\n/* Settings workspace */\n' + Path(__file__).with_name('settings_workspace.js').read_text(encoding='utf-8')
CLOSE_SCRIPT += '\n/* Workspace */\n' + Path(__file__).with_name('report_workspace.js').read_text(encoding='utf-8')


def date_text(timestamp):
    return datetime.fromtimestamp(timestamp, ZONE).strftime('%Y-%m-%d %H:%M:%S')


def confirmation_heading(order):
    reasons, fields = order['reasons'], order['fields']
    uncertain = lambda words: any(any(word in reason for word in words) for reason in reasons)
    route = fields.get('commute', {})
    checks = [('科目', bool(fields.get('subjects')) and not uncertain(['科目', '全科', '年级', '英文授课'])),
              ('时间', (fields.get('time_status') == 'ok' or bool(fields.get('schedule'))) and not uncertain(['上课时间'])),
              ('报价', fields.get('hourly_cny') is not None and not uncertain(['报价', '价格'])),
              ('教师要求', not uncertain(['教师要求', '英文授课', '不可解析'])),
              ('通勤', route.get('status') == 'ok' and not uncertain(['通勤', '公共交通']))]
    return '<div class="check-grid" aria-label="筛选状态">' + ''.join(
        f'<span class="check-item">{label}<span class="check-result {"" if passed else "pending"}" role="img" aria-label="{"通过" if passed else "待确认"}">{"已通过" if passed else "待确认"}</span></span>'
        for label, passed in checks) + '</div>'


def candidate_priority(order, address_keywords=()):
    return (max(source['timestamp'] for source in order['sources']),
            confirmation_heading(order).count('aria-label="通过"'),
            any(keyword in order['fields'].get('address', '') for keyword in address_keywords))


def render_raw(order):
    annotations = {index: (field, value) for index, field, value in feedback_rows(order['raw'])}
    if not annotations or order['status'] == 'closed':
        return escape(order['raw'], quote=True)
    lines = []
    for index, line in enumerate(order['raw'].splitlines()):
        button = ''
        if index in annotations:
            field, value = annotations[index]
            if len(value) <= 2000:
                reason = FEEDBACK_FIELDS[field][0]
                button = f'<button type="button" class="feedback-reject" data-feedback-field="{field}" data-feedback-value="{escape(value, quote=True)}" data-feedback-reason="{reason}">{reason}</button>'
        lines.append(f'<span class="raw-line"><span>{escape(line, quote=True)}</span>{button}</span>')
    return '\n'.join(lines)


def render_key_information(order, grade_label, price):
    """Summaries use extracted fields; feedback always keeps the exact source value."""
    fields = order['fields']
    annotations = feedback_rows(order['raw']) if order['status'] != 'closed' else []
    rows = [('学生年级', grade_label, None), ('科目', ' / '.join(fields.get('subjects') or []) or '未识别', 'subject'),
            ('上课时间', fields.get('schedule') or '未指定', 'frequency'), ('报价', price, 'pay'),
            ('教师要求', fields.get('teacher_requirements') or '未识别，需查看原文', 'teacher'),
            ('授课地址', fields.get('address') or '未识别', 'address')]
    rendered = []
    for label, value, field in rows:
        buttons = []
        for _, source_field, source_value in annotations:
            if source_field == field and len(source_value) <= 2000:
                reason = FEEDBACK_FIELDS[field][0]
                buttons.append(f'<button type="button" class="feedback-reject" data-feedback-field="{field}" data-feedback-value="{escape(source_value, quote=True)}" data-feedback-reason="{reason}">{reason}</button>')
        rendered.append(f'<div class="key-row"><span class="key-label">{label}</span><span class="key-value">{escape(str(value), quote=True)}</span><span class="key-feedback">{"".join(buttons)}</span></div>')
    return '<details class="key-information" open><summary>关键信息</summary>' + ''.join(rendered) + '</details>'


def render_report(orders, metadata):
    cutoff = metadata['generated_at'] - 7 * 86400
    orders = [{**order, 'sources': [s for s in order['sources'] if s['timestamp'] >= cutoff]}
              for order in orders if any(s['timestamp'] >= cutoff for s in order['sources'])]
    e = lambda value: escape(str(value), quote=True)
    sections = []
    changed_note = '<p class="note">规则或偏好已变更，保留候选已重新筛选。</p>' if metadata.get('configuration_changed') else ''
    if metadata.get('map_check_enabled') is False:
        changed_note += '<p class="note">本轮仅重新提取和代码筛选，未调用地图；通勤尚需核实。</p>'
    for status, label in LABELS.items():
        matches = [order for order in orders if order['status'] == status or status == 'rejected' and order['status'] == 'closed']
        cards = []
        sort_key = (lambda o: candidate_priority(o, metadata.get('preferred_address_keywords', []))) if status in ('recommended', 'needs_confirmation') else lambda o: (max(s['timestamp'] for s in o['sources']),)
        for order in sorted(matches, key=sort_key, reverse=True):
            sources = '<br>'.join(e(s['group_name']) + ' · ' + e(date_text(s['timestamp'])) for s in order['sources'])
            fields = json.dumps(order['fields'], ensure_ascii=False, indent=2)
            reasons = '；'.join(order['reasons'])
            if order['status'] == 'closed':
                reasons = reasons.removeprefix('熄单：')
                if not reasons or '被别人接走' in reasons or '手动标记已被接走' in reasons:
                    reasons = '单已被抢走'
            commute = order['fields'].get('commute', {})
            commute_note = ''
            if commute.get('online'):
                commute_note = '<p>线上授课 · 无需通勤 · 0分钟 · 未调用地图</p>'
            elif commute.get('status') == 'ok':
                context_label = '按明确上课时段查询' if commute.get('verified_schedule') else '参考时段估算'
                if commute.get('destination_is_reference'):
                    context_label += '；参考目的地：' + str(commute.get('located_name', '地标')) + '，住宅位置未精确定位'
                commute_note = f'<p>公共交通预计 {e(commute["minutes"])} 分钟 · 换乘 {e(commute.get("transfers", "未知"))} 次 · 步行 {e(commute.get("walking_meters", "未知"))} 米<br>{e(context_label)} · 查询出发时刻：{e(commute.get("query_departure", "未知"))}</p>'
            elif commute:
                commute_note = f'<p class="note">{e(FAILURE_LABELS.get(commute.get("reason"), "地图查询未成功，通勤待确认"))}</p>'
            heading = confirmation_heading(order)
            if status == 'recommended':
                heading = '<div class="check-grid" aria-label="筛选状态">' + ''.join(
                    f'<span class="check-item">{label}<span class="check-result" role="img" aria-label="通过">已通过</span></span>'
                    for label in ('科目', '时间', '报价', '教师要求', '通勤')) + '</div>'
            elif status in ('rejected', 'parse_failed', 'closed'):
                # These categories must not imply five successful checks.
                heading = ''
            identifier = order_identifier(order['raw'])
            order_key = identifier if identifier else order.get('fingerprint') or hashlib.sha256(order['raw'].encode()).hexdigest()
            close_button = '<button class="close-order" type="button" title="标记为已被抢" aria-label="标记此订单为已被抢">已被抢</button>' if order['status'] != 'closed' else ''
            if status in ('recommended', 'needs_confirmation'):
                close_button = '<button class="shortlist-order" type="button" title="加入待选项" aria-label="加入或移出待选项" aria-pressed="false">加入待选</button>' + close_button
            summary_fields = order['fields']
            grade = summary_fields.get('grade')
            grade_label = '小学' if grade == 'primary' else (f'小学{"一二三四五六"[grade - 1]}年级' if isinstance(grade, int) and 1 <= grade <= 6 else f'初中{"一二三"[grade - 7]}年级' if isinstance(grade, int) and 7 <= grade <= 9 else f'高中{"一二三"[grade - 10]}年级' if isinstance(grade, int) and 10 <= grade <= 12 else {-3:'幼儿园小班',-2:'幼儿园中班',-1:'幼儿园大班',0:'学前班',13:'大学',14:'成人','preschool':'幼教（班级待确认）'}.get(grade,'年级待确认'))
            if grade in ('junior','senior'):
                grade_label = ('初中' if grade == 'junior' else '高中') + '（具体年级未指定）'
            if summary_fields.get('grade_candidates'):
                grade_label = '小学' + ' / '.join('一二三四五六'[value-1] for value in summary_fields['grade_candidates']) + '年级（需确认）'
            title = grade_label + ' · ' + (' / '.join(summary_fields.get('subjects') or []) or '科目待确认')
            hourly = summary_fields.get('hourly_cny')
            price = '–'.join(dict.fromkeys(str(value) for value in hourly)) if isinstance(hourly, list) else str(hourly) if hourly is not None else ''
            price = price + '元/小时' if price else '报价待确认'
            timestamp = max(source['timestamp'] for source in order['sources'])
            priority = candidate_priority(order, metadata.get('preferred_address_keywords', []))
            card_id = 'order-' + hashlib.sha256((status + str(order_key)).encode()).hexdigest()[:16]
            dismiss = f'<button class="feedback-reject dismiss-order" type="button" title="移入不匹配" aria-label="删除此订单并移入不匹配" data-feedback-field="order" data-feedback-value="{e(order_key)}" data-feedback-reason="手动排除">{DELETE_ICON}</button>' if order['status'] != 'closed' else ''
            order_heading = f'<div class="order-heading"><h3>{e(title)}</h3>{dismiss}</div>'
            cards.append(f'<article id="{card_id}" data-order-key="{e(order_key)}" data-title="{e(title)}" data-address="{e(summary_fields.get("address", "地址待确认"))}" data-price="{e(price)}" data-schedule="{e(summary_fields.get("schedule", ""))}" data-time-label="{e(date_text(timestamp)[5:16])}" data-timestamp="{e(timestamp)}" data-passed="{priority[1]}" data-preferred="{int(priority[2])}">{order_heading}<p class="order-id">订单 {e(identifier or str(order_key)[:12])} · {sources}</p>{heading}<p class="reason">{e(reasons) or "已识别条件符合；接单前确认订单仍有效"}</p>{render_key_information(order, grade_label, price)}<div class="commute-note">{commute_note}</div><details class="raw-details"><summary>原文核对</summary><pre>{e(order["raw"])}</pre></details><details class="fields-details"><summary>提取字段</summary><pre>{e(fields)}</pre></details><div class="order-actions">{close_button}<span class="note">待选仅保存在此浏览器</span></div></article>')
        sections.append(f'<section class="order-section" id="{status}"><h2 tabindex="-1">{label} <span>{len(matches)}</span></h2>{"".join(cards)}<p class="empty" {"hidden" if matches else ""}>暂无记录</p></section>')
    sections.insert(2, '<section class="order-section" id="shortlist"><h2 tabindex="-1">待选项 <span>0</span></h2><div class="shortlist-cards"></div><p class="empty">暂无待选项，打开推荐或待确认订单后点击“加入待选”。</p></section>')
    revision = hashlib.sha256(json.dumps([metadata.get('ui_preferences', {}), metadata.get('rejection_feedback', []), metadata.get('closed_order_keys', [])], sort_keys=True).encode()).hexdigest()
    settings_data = e(json.dumps({'rejection_feedback': metadata.get('rejection_feedback', []), 'preference_overrides': metadata.get('preference_overrides', {}), 'base_revision': revision}, ensure_ascii=False))
    preference_data = e(json.dumps(metadata.get('ui_preferences', {}), ensure_ascii=False))
    sections.append('<section id="preferences"><h2>用户设置 <span hidden>0</span></h2><p>编辑后点击右上角“保存更改”，保存到项目根目录，下次筛选生效。此处不编辑群白名单、地图Key或定时任务。</p><button id="back-report" type="button">返回报告</button><form id="preference-form"><div id="preference-fields"></div></form><h3>已学习的排除规则</h3><p>按同字段内容匹配；地址按清洗后的地点匹配。删除规则不会解除原订单的熄单。</p><div id="learned-rules"></div></section>')
    context = metadata.get('preference_context', {})
    if context:
        fixed_context = '<div class="preference-context">' + ''.join(f'<p>{e(label)}：{e(value)}</p>' for label, value in context.items() if label not in ('出发地点','城市与交通','其他规则')) + '<p>此处展示运行信息。修改设置不会自动调整运行计划、消息来源或地图额度。</p></div>'
        sections[-1] = sections[-1].replace('<form id="preference-form">', fixed_context + '<form id="preference-form">')
    browser_script = CLOSE_SCRIPT.replace('\r\n', '\n').replace('\r', '\n')
    script_hash = base64.b64encode(hashlib.sha256(browser_script.encode()).digest()).decode()
    settings_schema = e(json.dumps({'grade_groups': GRADE_GROUPS, 'subject_choices': [*SUBJECTS,'识字','拼音','启蒙']}, ensure_ascii=False))
    css = Path(__file__).with_name('report_workspace.css').read_text(encoding='utf-8')
    navigation = {'recommended': '推荐', 'needs_confirmation': '待确认', 'shortlist': '待选项',
                  'rejected': '不匹配', 'parse_failed': '解析失败'}
    nav = ''.join(f'<a class="nav-link" data-category="{key}" href="#{key}"><span>{label}</span><span class="nav-count">{sum(order["status"] == key or key == "rejected" and order["status"] == "closed" for order in orders)}</span></a>' for key, label in navigation.items())
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>家教筛客 · 本地报告</title><style>{css}</style></head><body>
<div class="app"><aside class="sidebar"><div class="brand"><span>家教筛客</span><button id="theme-toggle" type="button" aria-label="切换到亮色主题"></button></div><nav class="category-nav" aria-label="订单分类">{nav}</nav><div class="sidebar-bottom"><a class="nav-link preferences-link" data-category="preferences" href="#preferences">用户设置</a><p class="local-label">本地报告 · 数据保存在本机</p></div></aside>
<div class="main-shell"><header class="topbar"><div><div class="heading-line"><h1 id="view-title">待确认</h1><span class="caption" id="view-caption">先核对，再待选</span></div><p class="generated">{e(date_text(metadata['generated_at']))} · <span id="message-window-label">近7天</span> · 本轮读取 {metadata['messages_read']} 条 · 新增 {metadata['new_orders']} 单</p></div><div class="save-tools"><button id="save-closed" type="button" aria-label="保存熄单、反馈与偏好（永久生效）">保存更改</button><span id="save-state" role="status">本地报告</span></div></header>
<div class="workspace"><aside class="master" aria-label="订单列表"><div class="list-toolbar search-toolbar"><label for="search-orders">关键词</label><input id="search-orders" type="search" placeholder="查找当前分类订单" autocomplete="off"></div><div class="list-toolbar"><label for="sort-orders">排序</label><select id="sort-orders"><option value="time">时间倒序</option><option value="checks">通过项数量</option><option value="address">地址优先关键词</option></select></div><div id="order-list"></div><p id="list-empty" class="empty" hidden>当前分类暂无订单</p><p class="list-footer">选择订单查看原文与筛选依据</p></aside>
<main id="detail-pane" aria-label="订单详情">{''.join(sections)}<p class="detail-empty" id="detail-empty" hidden>当前分类暂无订单，可以切换其他分类。</p><details class="report-info"><summary>报告说明与保存帮助</summary>{changed_note}<p>仅展示本次运行时刻往前7天内发布的订单。地图估算不保证实际到达时间，订单是否仍可接需本人确认。图片及复杂文本可能需要返回微信核对。正文保存在本机，仅地点和出发时段用于高德查询。</p><p>熄单、反馈理由和偏好统一保存为项目根目录的 manual_closed_orders.json，下次筛选生效。首次保存选择项目目录，之后浏览器会记住；不支持文件选择时下载后手动放入根目录。待选项仅保存于当前浏览器。</p></details></main></div></div></div>
<button id="jump-shortlist" type="button" hidden aria-label="跳转到待选项">待选 0</button><pre id="settings-schema" hidden>{settings_schema}</pre><pre id="user-settings-data" hidden>{settings_data}</pre><pre id="preference-data" hidden>{preference_data}</pre><pre id="saved-closed-keys" hidden>{e(json.dumps(metadata.get("closed_order_keys", [])))}</pre><div id="feedback-toast" hidden><svg class="toast-icon" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false"><path d="M512 85.333333c235.648 0 426.666667 191.018667 426.666667 426.666667s-191.018667 426.666667-426.666667 426.666667S85.333333 747.648 85.333333 512 276.352 85.333333 512 85.333333z m0 170.666667a42.666667 42.666667 0 0 0-42.666667 42.666667v341.333333a42.666667 42.666667 0 0 0 85.333334 0V298.666667a42.666667 42.666667 0 0 0-42.666667-42.666667z m0 554.666667a42.666667 42.666667 0 1 0 0-85.333334 42.666667 42.666667 0 0 0 0 85.333334z" fill="#FAAD14"></path></svg><p id="close-feedback" role="status"></p></div><script type="text/javascript">{CLOSE_SCRIPT}</script></body></html>'''
