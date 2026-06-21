# PersonaIter 人设迭代器

追踪 Bot 人设一致性，识别一天对话中的人设偏移节点，生成优化建议文件。  
**不追着用户喜好改人设，而是看人设有没有按剧本演。**

三种触发方式：
- 🧑 手动命令 → `/persona_suggest`
- 🤖 Planner 工具 → `persona_analyze`
- ⏰ 定时静默 → `scheduled_time`

只管建议，不动配置。

插件仍在测试中,可能出现用不了或者其他意外情况,发现情况可以提交issue或者找作者

## 安装

复制 `persona-iter` 目录到 MaiBot 的 `plugins/` 下：

```
plugins/
└── persona-iter/
    ├── _manifest.json
    ├── config.toml
    ├── plugin.py
    ├── README.md
    └── suggestions/
```

重载插件或重启 MaiBot。

## 配置

编辑 `plugins/persona-iter/config.toml`：

```toml
[plugin]
enabled = true

# 优化指令：告诉 LLM 从什么方向去分析人设
# 比如 "语气再活泼一点" "减少颜文字" "多加入一些专业感"
# 留空则使用默认的分析框架
optimize_prompt = ""

# 定时执行时间（24h 格式 HH:MM）。留空禁用定时
scheduled_time = ""

# 分析的默认时间范围（小时）
default_hours = 24
# 每个聊天流最多拉取的消息数
max_messages_per_stream = 100
# 最多分析的聊天流数（0 = 不限制）
max_streams = 0
# LLM 模型名，留空使用默认模型
model = ""
# 建议文件的输出目录（相对插件目录）
storage_dir = "suggestions"
```

### 配置项说明

| 字段 | 说明 |
|------|------|
| `optimize_prompt` | 用户自定义优化方向。若有填写，会追加到默认提示词之后且优先级更高 |
| `scheduled_time` | 定时执行时间，到点自动分析并写文件，不发送任何消息 |
| `default_hours` | 不指定 hours 参数时的默认分析范围 |

## 使用

### 方式一：手动命令

| 命令 | 说明 |
|------|------|
| `/persona_suggest` | 手动触发分析（默认 24h） |
| `/persona_suggest --hours 48` | 指定时间范围 |
| `/psuggest` | 别名 |
| `/人设建议` | 中文别名 |

### 方式二：Planner 工具

插件注册了 `persona_analyze` Tool，MaiBot 的 LLM Planner 可以直接调用：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `hours` | integer | 否 | 分析时间范围，默认使用配置值 |
| `force` | boolean | 否 | 设为 `true` 可强制重新分析 |

Planner 调用后返回 `{"success": true, "message": "done", ...}`。

### 方式三：定时执行

配置 `scheduled_time = "03:00"` 后，每天凌晨 3 点自动执行静默分析，不发送任何消息，文件静默写入 `suggestions/` 目录。

### 分析输出结构

生成的建议文件包含以下内容：

| 章节 | 说明 |
|------|------|
| **人设演变追踪** | 按时间分阶段，追踪情感/语气/态度的变化轨迹 |
| **关键偏差节点** | 具体到哪段对话、什么表现、可能原因 |
| **优化方向** | 强化人设定力、补充场景覆盖、明确化描述 |
| **建议的人设调整** | 可直接使用的调整片段 |

### 执行流程

```
你: /persona_suggest
Bot: 分析完成！建议文件: plugins/persona-iter/suggestions/persona-suggest-2026-06-20.md
     数据: 分析 47 条消息，3 个聊天流
     已参考优化指令进行分析
     请阅读建议文件后手动修改 bot_config，插件不会自动应用。

你: (打开建议文件审阅)
你: (手动复制建议的人设调整到 bot_config)
```

## 史诗级免责声明

### 一、插件内容过大

本插件使用 LLM 分析聊天记录，Token 消耗量取决于你的聊天活跃度。活跃群聊的日分析可能吃掉数十万 Token，请自行评估模型预算。

### 二、建议质量为 LLM 输出

- 建议质量取决于 LLM 的分析能力和 optimize_prompt 的质量
- 拉取聊天记录依赖 `get_by_time_in_chat` 的实际行为，不同 SDK 版本可能有差异
- 部分聊天流可能因权限或平台限制无法读取

### 三、人设是你的

本插件按现状提供，不提供任何明示或暗示的担保。作者不对因使用本插件造成的人设崩塌、用户流失、AI 觉醒、猫娘化、赛博精神病等任何后果负责。**人设是你自己的，别让 AI 替你做决定。**

## 许可证

AGPL v3.0 or later
