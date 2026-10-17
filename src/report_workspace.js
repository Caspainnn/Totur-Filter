/* Focused workspace: the original articles remain the source of truth. */
(() => {
const list = document.getElementById('order-list');
if (!list) return;
const categories = ['recommended', 'needs_confirmation', 'shortlist', 'rejected', 'parse_failed'];
const sections = categories.map(id => document.getElementById(id));
const sort = document.getElementById('sort-orders');
const themeButton = document.getElementById('theme-toggle');
const themeIcons={
  sun:'M554.666667 839.111111v113.777778h-71.111111v-113.777778h71.111111z m220.885333-120.945778l80.455111 80.455111-50.275555 50.275556-80.455112-80.455111 50.275556-50.275556z m-512.881778 0l50.275556 50.275556-80.455111 80.455111-50.275556-50.275556 80.455111-80.455111zM512 256c141.383111 0 256 114.616889 256 256s-114.616889 256-256 256-256-114.616889-256-256 114.616889-256 256-256z m0 71.111111c-102.115556 0-184.888889 82.773333-184.888889 184.888889s82.773333 184.888889 184.888889 184.888889 184.888889-82.773333 184.888889-184.888889-82.773333-184.888889-184.888889-184.888889z m448 149.333333v71.111112h-113.777778v-71.111112h113.777778z m-768 0v71.111112h-113.777778v-71.111112h113.777778z m40.490667-301.340444l80.455111 80.455111-50.275556 50.275556-80.455111-80.455111 50.275556-50.275556z m573.240889 0l50.275555 50.275556-80.455111 80.455111-50.275556-50.275556 80.455112-80.455111zM554.666667 71.111111v113.777778h-71.111111V71.111111h71.111111z',
  moon:'M425.799111 141.269333A383.075556 383.075556 0 0 0 398.222222 284.444444c0 212.081778 171.918222 384 384 384 34.744889 0 68.408889-4.608 100.423111-13.269333C825.898667 796.330667 687.687111 896 526.222222 896c-212.081778 0-384-171.918222-384-384 0-177.336889 120.206222-326.584889 283.576889-370.730667z m-98.460444 129.080889l-3.000889 2.517334A312.945778 312.945778 0 0 0 213.333333 512c0 172.8 140.088889 312.888889 312.888889 312.888889 82.033778 0 158.122667-31.857778 214.812445-85.333333l1.777777-1.706667-5.290666-0.455111C509.610667 715.178667 330.951111 524.828444 327.168 291.968L327.111111 284.444444c0-3.100444 0.028444-6.186667 0.099556-9.272888l0.128-4.821334zM590.222222 199.111111l22.983111 46.577778 51.413334 7.466667-37.205334 36.266666 8.789334 51.2-45.980445-24.177778-45.980444 24.177778 8.789333-51.2-37.205333-36.266666 51.413333-7.466667L590.222222 199.111111z'
};
function setTheme(theme){
  document.documentElement.dataset.theme=theme;
  if(themeButton){
    const label=theme==='light'?'切换到暗色主题':'切换到亮色主题';
    themeButton.innerHTML='<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false"><path d="'+themeIcons[theme==='light'?'moon':'sun']+'" fill="currentColor"></path></svg>';
    themeButton.setAttribute('aria-label',label);themeButton.setAttribute('title',label);
  }
}
let savedTheme='dark';try{savedTheme=localStorage.getItem('wechat-tutor-filter.theme')==='light'?'light':'dark';}catch{}
setTheme(savedTheme);
themeButton?.addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='light'?'dark':'light';setTheme(theme);try{localStorage.setItem('wechat-tutor-filter.theme',theme);}catch{}});
const search = document.getElementById('search-orders');
let category = 'needs_confirmation', selected = null;
const lastSelected = new Map();
const visibleOrderKeys = new Map();
function nextOrderKey(previous, current, available) {
  const index=previous.indexOf(current), allowed=new Set(available);
  if(index<0)return available[0];
  return previous.slice(index+1).find(key=>allowed.has(key)) ||
    previous.slice(0,index).reverse().find(key=>allowed.has(key)) || available[0];
}
function text(tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}
function withinMessageWindow(timestamp,days,now=Date.now()/1000){return Number(timestamp)>=now-days*86400;}
function render() {
  const cutoff=Date.now()/1000-7*86400;
  sections.forEach(section=>section.querySelectorAll('article').forEach(card=>{if(Number(card.dataset.timestamp)<cutoff)card.remove();}));
  const requestedDays=Number(window.tutorPreferenceEditor?.controls.get('message_window_days')?.control.value || 7);
  const days=[1,3,5,7].includes(requestedDays)?requestedDays:7;
  const inWindow=card=>withinMessageWindow(card.dataset.timestamp,days);
  const windowLabel=document.getElementById('message-window-label');if(windowLabel)windowLabel.textContent='近'+days+'天';
  const preferenceView = location.hash === '#preferences';
  const requested = location.hash === '#closed' ? 'rejected' : location.hash.slice(1);
  if (categories.includes(requested)) category = requested;
  document.body.classList.toggle('preferences-view', preferenceView);
  const active = document.getElementById(category);
  sections.forEach(section => {
    section.hidden = preferenceView || section !== active;
    document.querySelector(`[data-category="${section.id}"] .nav-count`).textContent = [...section.querySelectorAll('article')].filter(inWindow).length;
  });
  document.querySelectorAll('[data-category]').forEach(link => {
    const current = link.dataset.category === (preferenceView ? 'preferences' : category);
    if (current) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  document.getElementById('view-title').textContent = preferenceView ? '用户设置' : active.querySelector('h2').firstChild.textContent.trim();
  document.getElementById('view-caption').textContent = preferenceView ? '统一维护个人信息与筛选偏好' : category === 'needs_confirmation' ? '先核对，再待选' : category === 'shortlist' ? '集中比较你的候选' : '浏览订单，查看详情';
  const keyword = (search?.value || '').trim().toLocaleLowerCase();
  const cards = [...active.querySelectorAll('article')].filter(inWindow).filter(card => !keyword ||
    [card.dataset.title, card.dataset.address, card.dataset.price, card.dataset.schedule,
      card.querySelector('.raw-details')?.textContent || card.textContent].join(' ').toLocaleLowerCase().includes(keyword));
  cards.sort((a, b) => {
    const priority = sort.value === 'checks' ? 'passed' : sort.value === 'address' ? 'preferred' : 'timestamp';
    return Number(b.dataset[priority]) - Number(a.dataset[priority]) || Number(b.dataset.timestamp) - Number(a.dataset.timestamp) || Number(b.dataset.passed) - Number(a.dataset.passed) || Number(b.dataset.preferred) - Number(a.dataset.preferred);
  });
  const keys=cards.map(card=>card.dataset.orderKey), oldKey=lastSelected.get(category);
  const selection=keys.includes(oldKey)?oldKey:nextOrderKey(visibleOrderKeys.get(category)||[],oldKey,keys);
  selected = cards.find(card => card.dataset.orderKey === selection) || null;
  visibleOrderKeys.set(category,keys);
  if (selected) lastSelected.set(category, selected.dataset.orderKey);
  sections.forEach(section => section.querySelectorAll('article').forEach(card => card.classList.toggle('active-order', !preferenceView && card === selected)));
  list.replaceChildren();
  for (const card of cards) {
    const row = document.createElement('button');
    row.type = 'button'; row.className = 'order-row';
    row.setAttribute('aria-pressed', String(card === selected));
    row.setAttribute('aria-controls', card.id);
    row.appendChild(text('span', card.dataset.title, 'row-title'));
    if (card.classList.contains('shortlisted')) row.appendChild(text('span', '已待选', 'row-badge'));
    row.appendChild(text('span', [card.dataset.address, card.dataset.price].filter(Boolean).join(' · '), 'row-meta'));
    row.appendChild(text('span', card.dataset.schedule || '上课时间未明确', 'row-schedule'));
    row.appendChild(text('span', card.dataset.timeLabel, 'row-time'));
    row.addEventListener('click', () => {
      lastSelected.set(category, card.dataset.orderKey); render();
      // Rebuilding the list must not drop keyboard focus.
      [...list.children].find(button => button.getAttribute('aria-controls') === card.id)?.focus();
      document.getElementById('detail-pane').scrollTop = 0;
    });
    list.appendChild(row);
  }
  document.getElementById('list-empty').hidden = cards.length > 0;
  document.getElementById('list-empty').textContent = keyword ? '没有找到匹配的订单，请换个关键词' : '当前分类暂无订单';
  document.getElementById('detail-empty').hidden = preferenceView || cards.length > 0;
  document.querySelectorAll('.shortlist-order').forEach(button => {
    button.textContent = button.getAttribute('aria-pressed') === 'true' ? '已加入待选' : '加入待选';
  });
}
function dirty() {
  document.getElementById('save-state').textContent = '有更改待保存';
  document.getElementById('save-state').classList.add('dirty');
}
document.addEventListener('click', event => {
  const navigation = event.target.closest('a[data-category]');
  if (navigation) {
    event.preventDefault();
    history.pushState(null, '', navigation.getAttribute('href'));
    window.dispatchEvent(new Event('hashchange'));
    document.getElementById('detail-pane').scrollTop = 0;
    return;
  }
  const shortlistAction=event.target.closest('.shortlist-order, .unshortlist-order');
  if (shortlistAction) {
    if(shortlistAction.classList.contains('shortlist-order') && shortlistAction.getAttribute('aria-pressed')==='true'){
      const current=shortlistAction.closest('article').dataset.orderKey, keys=visibleOrderKeys.get(category)||[];
      lastSelected.set(category,nextOrderKey(keys,current,keys.filter(key=>key!==current)) || current);
    }
    render();document.getElementById('detail-pane').scrollTop=0;
  }
  if (event.target.closest('.close-order, .feedback-reject, .learned-rule button')) dirty();
});
document.getElementById('preference-form').addEventListener('input', dirty);
document.addEventListener('tutor-settings-draft-changed', () => {dirty();render();});
document.addEventListener('tutor-message-window-changed',render);
document.addEventListener('tutor-order-closed', () => {dirty(); render();document.getElementById('detail-pane').scrollTop=0;});
document.addEventListener('tutor-settings-saved', () => {
  document.getElementById('save-state').textContent = '已保存到文件';
  document.getElementById('save-state').classList.remove('dirty');
  render();
});
window.addEventListener('hashchange', render);
sort.addEventListener('change', render);
search?.addEventListener('input', render);
const feedback = document.getElementById('close-feedback');
const toast = document.getElementById('feedback-toast');
if (toast) {
  let noticeTimer;
  new MutationObserver(()=>{
    const message=feedback.textContent;toast.hidden=!message;clearTimeout(noticeTimer);
    if(message)noticeTimer=setTimeout(()=>{if(feedback.textContent===message){feedback.textContent='';toast.hidden=true;}},3000);
  }).observe(feedback,{childList:true,characterData:true,subtree:true});
}
// Restored drafts are still browser-local until explicitly saved to a file.
try {
  const state = window.tutorUserState;
  const savedKeys = new Set(JSON.parse(document.getElementById('saved-closed-keys').textContent));
  const browserKeys = JSON.parse(localStorage.getItem('wechat-tutor-filter.closed.v1') || '[]');
  if (state.edited_preference_paths.length || state.deleted_feedback_rules.length || browserKeys.some(key => !savedKeys.has(key)) ||
      JSON.stringify(state.rejection_feedback) !== JSON.stringify(JSON.parse(document.getElementById('user-settings-data').textContent).rejection_feedback)) dirty();
} catch {}
render();
setInterval(render,60000);
})();
