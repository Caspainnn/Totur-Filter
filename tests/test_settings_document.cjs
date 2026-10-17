const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('src/settings_workspace.js','utf8');
const importer=source.slice(source.indexOf('function importValues('),source.indexOf('let importWarnings=[];'));
const parser=source.slice(source.indexOf('function parseLegacy('),source.indexOf("fileInput.addEventListener('change'"));
const initial={'pay.minimum_hourly_cny':100,'pay.range_crossing_minimum':'accept_if_maximum_meets_minimum',
  'pending_female_keyword_rejection':false,'availability.daily_start':{'1':'17:00','2':'18:00'},
  'subjects.by_stage':{primary:{mode:'legacy',accepted:['数学']},junior:{mode:'any',accepted:[]}},
  'grades.accepted':['初中一年级']};
const specs=[['pay.minimum_hourly_cny','最低时薪（元/小时）','number'],
  ['pay.range_crossing_minimum','报价区间规则','select'],
  ['pending_female_keyword_rejection','额外女字筛选','boolean'],
  ['availability.daily_start','逐日可上课时间','daily'],
  ['subjects.by_stage','分学段科目','policy'],['grades.accepted','可接学生年级','multi']];
let current=structuredClone(initial),baseline=structuredClone(initial);
const controls=new Map(specs.map(([path,label,kind])=>[path,{label,kind,control:{options:
  kind==='select'?[{value:'accept_if_maximum_meets_minimum'},{value:'needs_confirmation'}]:[{value:'初中一年级'},{value:'初中二年级'}]}}]));
const context={Map,Set,JSON,Object,Number,Array,Error,
  editor:{controls,baseline,collect:()=>structuredClone(current),updateBaseline(values){Object.assign(current,structuredClone(values));Object.assign(baseline,structuredClone(values));}},
  daily:structuredClone(initial['availability.daily_start']),schema:{grade_groups:{初中:['初中一年级','初中二年级']}},
  stages:[['primary','小学'],['junior','初中']],weekdays:['周一','周二','周三','周四','周五','周六','周日'],
  changes:{replaceChildren(){},appendChild(){}},dialog:{showModal(){}},status:{},node:()=>({})};
vm.createContext(context);
vm.runInContext('let incoming={};let importWarnings=[];'+importer+parser+';globalThis.api={importValues,parseLegacy,incoming:()=>incoming};',context);
context.api.importValues({'availability.daily_start':{'1':'20:00'}});
assert.equal(context.api.incoming()['availability.daily_start']['2'],'18:00','Partial daily import must retain other days');
assert.deepEqual(current,initial,'Preview must restore current draft');
assert.deepEqual(baseline,initial,'Preview must restore conflict baseline');
assert.throws(()=>context.api.importValues({'pending_female_keyword_rejection':'false'}));
assert.throws(()=>context.api.importValues({'pay.range_crossing_minimum':'invalid'}));
assert.throws(()=>context.api.importValues({'grades.accepted':['未知年级']}));
const parsed=context.api.parseLegacy('| 项目 | 填写内容 |\n| 最低时薪（元/小时） | 150 |\n| 初中可接科目 | 不限科目 |\n| 周一可上课时间 | 18:30之后 |');
assert.equal(parsed['pay.minimum_hourly_cny'],150);
assert.equal(parsed['subjects.by_stage'].junior.mode,'any');
assert.equal(parsed['availability.daily_start']['1'],'18:30');
context.intervals={'1':[['09:00','12:00']],'2':[['18:00','22:00']]};
current['availability.daily_intervals']=structuredClone(context.intervals);
controls.set('availability.daily_intervals',{label:'逐日区间',kind:'intervals',control:{}});
const intervalDoc=context.api.parseLegacy('| 周一可上课时间 | 09:00–12:00、18:00–22:00 |');
assert.equal(intervalDoc['availability.daily_intervals']['1'].length,2);
context.api.importValues(intervalDoc);
assert.equal(context.api.incoming()['availability.daily_intervals']['2'][0][0],'18:00');
assert.deepEqual(current['availability.daily_intervals'],context.intervals,'Interval preview must restore draft');
context.api.importValues({'availability.daily_start':{'1':'20:00'}});
assert.equal(context.api.incoming()['availability.daily_intervals']['2'][0][0],'18:00','Legacy-day import must preserve another day’s intervals');
assert.equal(context.api.incoming()['availability.daily_intervals']['1'][0][0],'20:00');
console.log('Document import: type/enum checks, partial-day merge, preview rollback, human Markdown parser passed');
if (process.argv[2]) {
  const editorSource=fs.readFileSync('src/preference_editor.js','utf8');
  const specsCode=editorSource.slice(editorSource.indexOf('const specs = ['),editorSource.indexOf('const controls = new Map();'));
  const allSpecs=vm.runInNewContext(specsCode+';specs;');
  const fullControls=new Map(allSpecs.map(([path,label,kind,options])=>[path,{label,kind,control:{options:(options||[]).map(item=>({value:Array.isArray(item)?item[0]:item}))}}]));
  context.editor.controls=fullControls;
  const actual=context.api.parseLegacy(fs.readFileSync(process.argv[2],'utf8'));
  assert.equal(actual['pay.minimum_hourly_cny'],140);
  assert.equal(actual['availability.daily_start']['1'],'20:30');
  assert.equal(actual['availability.daily_start']['2'],'19:30');
  assert.equal(actual['tutor_profile.academic_stage'],'master_1');
  assert.equal(actual['commute.city'],'示例城市');
  assert.ok(Array.isArray(actual['grades.accepted']));
  assert.equal(typeof actual['pending_female_keyword_rejection'],'boolean');
  context.api.importValues(actual);
  console.log('Actual browser-exported Markdown parsed with correct typed values and passes import preview');
}
