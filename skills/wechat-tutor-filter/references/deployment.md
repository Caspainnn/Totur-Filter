# Agent 部署指南

所有命令在完整项目根目录执行。此文档供 Agent 操作，README 保留用户最小路径。

## 1. 环境

确认 Windows、已登录的桌面微信及同一 Windows 用户。已有实测微信版本为 4.1.15.53；其他版本只能说明待验证。不要升级、降级微信或修改系统安全策略来绕过问题。

确认 64 位 Python 3.11。已有环境可复用；没有时引导用户安装 Python，不静默安装全局软件。使用已有 Python 创建隔离环境：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import struct, cryptography, zstandard; assert struct.calcsize('P') == 8; print('Dependencies OK')"
```

`py` 不可用时用实际 Python 完整路径代替。无须激活虚拟环境。第三方读取模块已在 `vendor/`，保留来源、许可证及校验值，不另外下载未知工具。

## 2. 私人配置

引导用户填写 Skill 的 `assets/用户偏好模板.md`，保存为项目根目录 `用户偏好.md`。只有文件缺失时才从对应 `config/*.example.json` 创建实际 JSON，不覆盖已有设置。使用 UTF-8 无 BOM 写入（Python `encoding='utf-8'`），JSON 不支持注释。

示例文件是空白结构，不是可直接运行的个人默认值。逐项填写并检查：

| 文件 / 字段 | 配置方式 |
| --- | --- |
| `chat_allowlist.json` / `allowed_group_names` | 非空、唯一、完整群名列表；保持精确匹配为 true，其余私聊、上传、密钥持久化和原文日志开关为 false |
| `tutor_profile.json` | `gender` 为 male/female，未知条件不要伪造；`academic_stage` 按代码支持的阶段，例如 undergraduate_3/master_1；学校全称、简称按本人提供 |
| `university_tiers` | 211/985为确认的布尔值，未知 null；不能把优势学科平台当985资格 |
| `teaching_experience_levels` | 已确认的 preschool/primary/junior/senior/adult 列表，不含推断经历 |
| `grades.accepted` | 用户选择的年级，合法名称见 `src/user_settings.py` 的 `GRADE_GROUPS` |
| `subjects.by_stage` | 每学段 `mode` 为 any/custom/legacy；custom 填非空 `accepted` 列表。只为用户接受的学段设置策略，不保留示例中的空 custom 策略 |
| `pay.minimum_hourly_cny` | 正数；区间跨阈值策略由用户选择，不自行取最高价 |
| `availability.daily_intervals` | 1–7 对应周一至周日，每天填多个 `[HH:MM, HH:MM]`；结束可为24:00，区间递增不重叠，空列表表示不可上课；跨午夜分到两天 |
| `availability.unspecified_class_time` | 用户选择 accept_as_negotiable 或 needs_confirmation |
| `commute.city` / `origin` | 用户自己的城市和明确起点，不能空着使用隐含的北京沙河坐标 |
| `commute.maximum_one_way_minutes` | 正数；仅公共交通估算，不承诺实际抵达时间 |
| `automatic_query_enabled` | 本人 Key 已配置且用户选择核实通勤时启用，否则显著说明未核实 |
| 黑名单、优先地点、熄单 | 新用户从空列表开始，只依据其明确输入追加 |

填写完检查所有必填值非空，验证群名和配置结构；不要直接运行空白模板。可将可编辑字段映射为点路径后用 `validate_overrides` 校验。普通运行前调用 `load_preferences()` 确认配置能读取，但这不代表来源、学校、地址或 Key 已验证。

已有 `manual_closed_orders.json` 时仅合并用户更新的项；未知键或非法格式应解释并修复，不删除全部文件来绕过。简历与个人文档不提交 Git。

## 3. 用户自己的高德 Key

引导用户在高德开放平台申请自己的 Web 服务 Key，确认地理编码、POI 检索和公交路线接口权限及额度。收费条件以其账户控制台为准，项目不提供共享 Key。

让用户在自己的 Windows 交互终端运行：

```powershell
& .\scripts\set_amap_key.ps1
```

脚本通过隐藏输入和 Windows 当前用户 DPAPI 保存；绝不要求用户把 Key 发到对话或写入文件。旧 Key 已存在时先确认属于用户；更换本人 Key 可用 `-Replace`。不要读取、复制、上传作者的 `%LOCALAPPDATA%\WeChatTutorFilter\amap-key.dpapi`。

不打印 Key 的本机格式检查：

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import os; from src.commute import load_private_key; load_private_key(Path(os.environ['LOCALAPPDATA']) / 'WeChatTutorFilter'); print('Local key is readable')"
```

此检查只能证明本机能解密和格式正确，不证明服务已授权或剩余额度充足。首次真实地图查询由用户授权的正式筛选完成。没有 Key 时可按用户选择用 `-NoMap` 输出降级报告，不回退任何他人账户。

## 4. 首次运行与验收

确认用户知悉微信账号风险及授权的群范围，然后：

```powershell
& .\scripts\run_once_scheduled.ps1
```

默认查找 `.venv\Scripts\python.exe`，也可 `-PythonPath '实际路径'`。脚本自动定位项目，不需要用户编辑路径。用户选择不查地图时加 `-NoMap`。

退出码0且 `scheduled-once-result.json` 为本次 `OK`，才提供其中的报告；检查是否带 `map_unavailable` 或 `map_skipped`。确认起点、范围和规则确为用户配置。零推荐不等于失败；失败不展示旧报告冒充成功。报告保存到根目录，内部状态与Key保存在当前Windows用户的应用数据目录。

筛选成功后，用相同 Python 启动或复用本机报告服务：

```powershell
.\.venv\Scripts\python.exe -m src.report_server
```

命令返回 `status: OK` 和 `http://127.0.0.1:端口/` 地址。Agent 使用浏览器工具打开这个地址，不要继续让用户双击 HTML。服务隐藏运行，只提供报告和固定的设置保存接口，不提供其他文件或命令执行。`report-server.json` 是本机运行状态，不提交 Git。服务器端口自动分配，重复启动会复用同一项目的现存服务；电脑重启后重新运行命令。

用户点击“保存更改”即可直接保存到项目目录，不弹目录或文件窗口。建议确认保存成功提示；再运行筛选时读取该设置。服务未连接或配置发生冲突时不覆盖文件，提示用户重开报告或取得最新设置。关闭服务可由 Agent 核对运行状态中的 PID 确为本项目进程后停止；不要终止其他 Python 进程。用户未要求定时任务前不创建计划。

## 离线验证

Python测试只用 `tests/fixtures/` 和模拟接口，不需要真实配置、微信或地图 Key：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Node 仅为开发测试所需。先在独立测试目录或新克隆中使用虚构数据生成报告，不能覆盖用户真实报告：

```powershell
.\.venv\Scripts\python.exe -m tests.ui_fixture
Copy-Item .\ui-preview.html .\tutor-report.html
Get-ChildItem .\tests\test_*.cjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { throw 'UI test failed' } }
```

这些命令不读取微信或调用地图。实际浏览器布局、系统保存窗口与真实微信兼容性需要另外验收，不能由单元测试代替。

## 故障定位

- 缺配置 / 依赖：先补本机环境，不读取私聊或扩大白名单排障。
- `GROUP_NOT_UNIQUE`：群名不匹配或有同名群，要求用户核实准确名称。
- `DATABASE_KEYS_UNAVAILABLE`：核查微信登录、版本与进程访问权限，不要求发送数据库密钥。
- `ACCOUNT_SELECTION_REQUIRED`：多个本地账号尚无法唯一确定，停止让用户明确，不任意选账号。
- `RUN_ALREADY_ACTIVE`：等待已有运行结束，不启动第二份。
- 地图暂缓：区分其他条件未知、窗口之外、额度、地点歧义及服务失败，不反复重试绕过额度。
- 修改无效：检查是否使用本机网页、保存是否成功及是否有反馈覆盖，重新运行筛选。报告服务只保存设置，不能启动采集。
- `DEPENDENCY_CHECKSUM_MISMATCH`：核对vendor文件与来源，不取消校验。
