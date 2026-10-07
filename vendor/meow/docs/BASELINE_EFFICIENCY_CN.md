# 两套请求效率候选：详细参数与验证结果

更新入口修正：本地在线目录使用 `4.5.3-predictive.3`，替代排序低于旧版本的 `4.5.3-efficiency.rc1`。仅版本标签与内容摘要改变，以下题目、配额、评分、校准和验证数据完全不变；旧文件保留。现有4.5.3程序点击“检查更新”即可发现两份基准，无须重装。网站仍使用同参数的efficiency.rc1。

2026-09-09。以下是已检查候选中的成本/表现折中，不声称全局最优或真实准确率保证。用户已授权发布本次基准更新；没有新增付费采样。

评分仍为v3；总体/逐题60%资格；强指向线≤98%；无温度字段；完整非空答案只做strip/casefold。早段误指路径≤3%，80%后≤1%，满额正确强指向≥99%且误指≤1%，整路径额外≤3%。

错误率是每来源/场景10,000条经验池模拟；不是新真实请求或独立盲测。0次错误不代表真实风险为零。历史数据被反复用于研发，完整新采样验证尚未完成；本次由用户授权按现有模拟证据发布。

## GPT

- 文件：`meow-gpt-other-cap98-efficient--4.5.3-efficiency.rc1.meow.json`
- 内容SHA256：`67a410ab169b2f997ec208cd1f01d03aa6870d647c0337c187f63fb11e4954d7`

### 请求数与题目配额

| 题目ID | 低档 | 中档 | 高档 |
|---|---:|---:|---:|
| gpt__ZH006 | 6 | 8 | 16 |
| gpt__ZH027 | 6 | 8 | 16 |
| gpt__ZH071 | 5 | 8 | 16 |
| gpt__b80_letter_count | 5 | 8 | 16 |
| gpt__rand_bird | 5 | 8 | 16 |
| gpt__rand_country | 5 | 8 | 16 |
| 总请求数 | 32 | 48 | 96 |

0表示该档不使用这道题。预算式默认重试额度为总请求数的50%向上取整，额外发送不改变每题有效样本配额。

### 强指向线

| 候选 | 低档 | 中档 | 高档 |
|---|---:|---:|---:|
| gpt-6-astra | 57.5761% | 57.9629% | 56.4354% |
| gpt-5.6-sol | 56.8617% | 55.4321% | 56.0006% |
| gpt-5.6-terra | 58.3117% | 60.7256% | 59.1461% |
| gpt-5.6-luna | 63.4232% | 63.6566% | 61.0959% |
| other | 64.1750% | 66.9262% | 67.2574% |

仅唯一最高匹配且严格超过对应线、样本资格满足时，才强指向。线不是身份概率。

### 模拟表现

| 档位 | 内部最差满额正确强指向 | 内部平均证据不足 | 内部最大满额误指 | 已拟合外部最低正确other | 早段最大误指 | 80%后最大误指 | 满额最大误指（含来源剔除） |
|---|---:|---:|---:|---:|---:|---:|---:|
| 低 | 99.8500% | 0.0425% | 0.0000% | 99.9700% | 2.3600% | 0.0000% | 0.0000% |
| 中 | 99.8900% | 0.0275% | 0.0000% | 99.9400% | 0.0000% | 0.0000% | 0.0000% |
| 高 | 100.0000% | 0.0000% | 0.0000% | 100.0000% | 0.0000% | 0.0000% | 0.0000% |

### 题目与请求参数原文

#### gpt__ZH006

```json
{
  "system": ".",
  "prompt": "随便说出一个国家，只回答国名。",
  "history": [],
  "effort": "low",
  "profile": "standard",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### gpt__ZH027

```json
{
  "system": ".",
  "prompt": "随便说出一个拟声词，只回答拟声词。",
  "history": [],
  "effort": "low",
  "profile": "standard",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### gpt__ZH071

```json
{
  "system": ".",
  "prompt": "从17到83中随便选一个整数，只回答数字。",
  "history": [],
  "effort": "low",
  "profile": "standard",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### gpt__b80_letter_count

```json
{
  "system": ".",
  "prompt": "Count the letter r in strawberry. Reply only with the integer.",
  "history": [],
  "effort": "low",
  "profile": "standard",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### gpt__rand_bird

```json
{
  "system": ".",
  "prompt": "Name a random bird. Reply with ONLY the bird name, one word.",
  "history": [],
  "effort": "low",
  "profile": "standard",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### gpt__rand_country

```json
{
  "system": ".",
  "prompt": "Name a random country. Reply with ONLY the country name.",
  "history": [],
  "effort": "low",
  "profile": "standard",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

## CLAUDE

- 文件：`meow-claude-other-cap98-efficient--4.5.3-efficiency.rc1.meow.json`
- 内容SHA256：`d03ce3752d3304aeaf0258cc1b5f302b90a49cb66a23096f32ae0ba3124fe18a`

### 请求数与题目配额

| 题目ID | 低档 | 中档 | 高档 |
|---|---:|---:|---:|
| claude__CL011 | 0 | 12 | 20 |
| claude__CL026 | 12 | 12 | 20 |
| claude__CL033 | 12 | 12 | 20 |
| claude__CL045 | 12 | 12 | 20 |
| claude__CL085 | 0 | 12 | 20 |
| claude__CL087 | 12 | 12 | 20 |
| 总请求数 | 48 | 72 | 120 |

0表示该档不使用这道题。预算式默认重试额度为总请求数的50%向上取整，额外发送不改变每题有效样本配额。

### 强指向线

| 候选 | 低档 | 中档 | 高档 |
|---|---:|---:|---:|
| claude-fable-5.1 | 54.5097% | 52.9401% | 52.8803% |
| claude-opus-5 | 52.5381% | 56.2421% | 55.2050% |
| claude-sonnet-5 | 52.7263% | 52.8870% | 52.5560% |
| claude-haiku-4.5 | 54.2108% | 54.7454% | 54.4024% |
| other | 51.3553% | 53.3864% | 54.5522% |

仅唯一最高匹配且严格超过对应线、样本资格满足时，才强指向。线不是身份概率。

### 模拟表现

| 档位 | 内部最差满额正确强指向 | 内部平均证据不足 | 内部最大满额误指 | 已拟合外部最低正确other | 早段最大误指 | 80%后最大误指 | 满额最大误指（含来源剔除） |
|---|---:|---:|---:|---:|---:|---:|---:|
| 低 | 99.6500% | 0.1025% | 0.0000% | 99.8200% | 0.3600% | 0.0900% | 0.0000% |
| 中 | 99.9700% | 0.0075% | 0.0000% | 99.7000% | 0.0600% | 0.0000% | 0.0000% |
| 高 | 99.9900% | 0.0025% | 0.0000% | 99.9400% | 0.0000% | 0.0000% | 0.0000% |

### 题目与请求参数原文

#### claude__CL011

```json
{
  "system": ".",
  "prompt": "不要思考，直接回答。从mepo、takri、sulon、vash中选一个词，只回答所选词。",
  "history": [],
  "effort": "low",
  "profile": "claude-code",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### claude__CL026

```json
{
  "system": ".",
  "prompt": "不要思考，直接回答。从19到71中选一个整数，只回答数字。",
  "history": [],
  "effort": "low",
  "profile": "claude-code",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### claude__CL033

```json
{
  "system": ".",
  "prompt": "不要思考，直接回答。随便选一个大写英文字母，只回答该字母。",
  "history": [],
  "effort": "low",
  "profile": "claude-code",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### claude__CL045

```json
{
  "system": ".",
  "prompt": "不要思考，直接回答。随便选一个整点，只回答0到23中的数字。",
  "history": [],
  "effort": "low",
  "profile": "claude-code",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### claude__CL085

```json
{
  "system": ".",
  "prompt": "不要思考，直接回答。从山地、平原、高原、盆地中选一种地形，只回答名称。",
  "history": [],
  "effort": "low",
  "profile": "claude-code",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

#### claude__CL087

```json
{
  "system": ".",
  "prompt": "不要思考，直接回答。从十个天干中随便选一个，只回答一个字。",
  "history": [],
  "effort": "low",
  "profile": "claude-code",
  "parameters": {
    "max_output_tokens": 128
  }
}
```

## 选择与限制

GPT：32/48/96；相比正式36/72/108减少约11.1%/33.3%/11.1%。新增两题未强制采用；该六题组合没有新的整套真实验证。追加3种种子低档早段最大误指2.46%、后段约0.022%，不是新样本。

Claude：固定比较6个已有开发候选；先满足分段门槛，再优先低请求数，同预算选择内部拒判较少者。以下保留失败方案，不以导出成功冒充所有方案通过。

| Claude方案 | 请求数 | 新分段门槛 | 内部最差正确 | 外部最差正确 | 整路径最大误指 |
|---|---:|---|---:|---:|---:|
| six-low48 | 48 | 失败 | 95.9300% | 99.2000% | 0.1000% |
| four-low48 | 48 | 通过 | 99.6500% | 99.8200% | 0.3600% |
| seven-low60 | 60 | 失败 | 99.8000% | 93.8600% | 0.3017% |
| six-medium72 | 72 | 通过 | 99.9700% | 99.7000% | 0.0600% |
| optimized-medium72 | 72 | 失败 | 99.9500% | 90.8300% | 0.5580% |
| six-high120 | 120 | 通过 | 99.9900% | 99.9400% | 0.0000% |

外部来源有限，稀疏Qwen仅作为额外检查而未拟合。少数外部格的经验样本很少，增加模拟次数不会增加真实信息。强指向线和错误率不可脱离题目、配额、拟合数据单独使用。

没有改变线上、GitHub或用户预览；此次交付为本地可导入候选，不是正式发布。
