# customer-portrait — 客户画像生成引擎

> 一个面向「接待/拜访前调研」的自动客户画像生成引擎。输入客户单位与主宾信息，通过三阶段 LLM Agent 循环 + 多维互联网搜索，自动产出可执行的多维客户画像。

适用于 B2B 销售、商务/展厅接待、政府接待、采访准备等"需要在见面前快速摸清对方"的场景。

---

## ✨ 特性

- **三阶段 Agent 循环架构**：调研规划 → 多维并行搜索 → 画像合成
- **维度台账机制**：单位背景 / 行业地位 / 主宾背景 / 来访动机，逐维度验收闭环
- **新颖性检测**：连续多轮无新信息自动收口，避免无限搜索
- **可插拔 LLM**：任意 OpenAI 兼容接口（DashScope / OpenAI / DeepSeek 等）改一行配置即可切换
- **可扩展搜索**：`SearchAdapter` 抽象基类 + 工厂注册，内置 Bochaai / Ansipai，新增引擎只需继承
- **多种接入方式**：CLI、Python 库调用、FastAPI 服务（REST + SSE 流式）、WebUI
- **Prompt 外置热改**：三个阶段对应 `prompts/*.txt`，无需改代码

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/LeckyHuang/customer-portrait-skill.git
cd customer-portrait-skill
pip install -r requirements.txt
```

### 2. 配置

从模板复制并填入 LLM 与搜索 API 密钥：

```bash
cp config.yaml.example config.yaml
cp .env.example .env   # 或直接在 config.yaml 中填写
```

`config.yaml` 关键字段：

```yaml
llm:
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1   # 或任意 OpenAI 兼容接口
  api_key: ${LLM_API_KEY}        # 走 .env / 环境变量
  model: qwen3.6-plus

search:
  providers:
    bochaai:
      api_key: ${BOCHAAI_API_KEY}
```

> ⚠️ **`config.yaml` 已在 `.gitignore` 中，不会被提交。请勿手动 `git add config.yaml`，以免泄漏密钥。**

### 3. 运行

**CLI 直传参数：**

```bash
python main.py --config config.yaml \
  --org "XX集团有限公司" \
  --industry "新能源汽车" \
  --guest "张伟" \
  --needs "考察智能制造产线和数字化转型方案" \
  --pretty
```

**JSON 文件输入：**

```bash
python main.py --config config.yaml --input customer.json --output portrait.json --pretty
```

`customer.json`：

```json
{
  "org_name": "XX集团有限公司",
  "industry": "新能源汽车",
  "guest_name": "张伟",
  "visit_needs": "考察智能制造产线和数字化转型方案"
}
```

**FastAPI 服务（供中控/外部系统集成）：**

```bash
python server.py    # 默认提供 REST + SSE 流式接口与 WebUI
```

**作为库调用：**

```python
from src.config import load_config
from src.schemas import CustomerInput
from src.llm import create_llm
from src.search import create_search
from src.engine import PortraitEngine

config = load_config("config.yaml")
engine = PortraitEngine(config, create_llm(config["llm"]), create_search(config["search"]))

customer = CustomerInput(
    org_name="XX集团有限公司",
    industry="新能源汽车",
    guest_name="张伟",
    visit_needs="考察智能制造产线和数字化转型方案",
)
result = engine.run(customer)
print(result.portrait)
```

## 🧠 工作原理（三阶段 Loop）

| 阶段 | Prompt 文件 | 作用 |
|------|------------|------|
| 1. 调研规划 | `prompts/keyword_extraction.txt` | LLM 分析调研方向，按维度生成初始搜索词 |
| 2. 多维研究循环 | `prompts/portrait.txt` | LLM 自主搜索并维护四维采集台账，逐维度验收；含新颖性检测 |
| 3. 画像合成 | `prompts/portrait_synthesis.txt` | 独立 LLM 调用，基于全部搜索结果生成最终画像 |

循环终止条件：所有维度完成 **或** 达到 `engine.max_queries_total` 搜索上限。

## 📤 输出结构

```jsonc
{
  "portrait": {
    "org_profile":        "...",   // 单位规模、业务、近期动态
    "industry_position":  "...",   // 行业地位、竞争格局
    "guest_profile":      "...",   // 主宾身份、决策权限、公开立场
    "visit_motivation":   "...",   // 明面需求 + 潜在动机 + 决策阶段
    "reception_focus":    "...",   // 话题切入点、展示重点、互动建议
    "risk_alerts":        "..."    // 敏感话题、竞争敏感点、信息缺口
  },
  "confidence_assessment": { ... },   // 各维度可信度 high/medium/low
  "sources": [ ... ],                // 来源 URL
  "queries_executed": [ ... ]         // 实际执行搜索词
}
```

## 🔧 配置扩展

- **换 LLM**：改 `config.yaml` 的 `llm.base_url` 与 `llm.model`
- **换搜索引擎**：在 `src/search/` 下新增 adapter，实现 `SearchAdapter.search()`，在 `create_search()` 注册
- **调整 Prompt**：直接编辑 `prompts/*.txt`，无需改代码
- **搜索预算**：`engine.max_queries_total`
- **新颖性阈值**：`engine.novelty_stale_rounds`

更详细的架构与扩展说明见 [`SKILL.md`](./SKILL.md)。

## 📁 项目结构

```
├── src/
│   ├── engine.py          # 三阶段 Agent 循环核心
│   ├── api.py             # FastAPI REST + SSE
│   ├── schemas.py         # 输入输出数据模型
│   ├── llm/               # LLM Adapter（OpenAI 兼容）
│   ├── search/            # Search Adapter 抽象 + 实现
│   ├── config.py          # 配置加载
│   └── wiki_client.py      # 可选：画像回写 wiki
├── prompts/               # 三阶段 Prompt（热改）
├── static/                # WebUI
├── main.py                # CLI 入口
├── server.py              # 服务入口
├── config.yaml.example    # 配置模板
└── SKILL.md               # 架构与扩展文档
```

## 📄 License

MIT — 详见 [`LICENSE`](./LICENSE)。
