# customer-portrait — 展厅接待客户画像生成

## 用途
根据客户单位名称、行业、主宾姓名和参观需求，通过多轮互联网搜索自动生成多维客户画像，用于展厅接待准备。

## 前置条件
1. 已存在 `config.yaml`（从 `config.yaml.example` 复制并填写 LLM 和搜索 API 配置）
2. 已安装依赖：`pip install -r requirements.txt`
3. API keys 已设置（config.yaml 中直接填写，或通过 `.env` 文件 / 环境变量注入）

## 使用方法

### 直接传参
```bash
python main.py --config config.yaml \
  --org "XX集团有限公司" \
  --industry "新能源汽车" \
  --guest "张伟" \
  --needs "考察智能制造产线和数字化转型方案" \
  --pretty
```

### 传入 JSON 文件
```bash
python main.py --config config.yaml --input customer.json --output portrait.json --pretty
```

`customer.json` 格式：
```json
{
  "org_name": "XX集团有限公司",
  "industry": "新能源汽车",
  "guest_name": "张伟",
  "visit_needs": "考察智能制造产线和数字化转型方案"
}
```

### 作为库调用（供中控系统集成）
```python
from dotenv import load_dotenv
load_dotenv()

from src.config import load_config
from src.schemas import CustomerInput
from src.llm import create_llm
from src.search import create_search
from src.engine import PortraitEngine

config = load_config("config.yaml")
customer = CustomerInput(
    org_name="XX集团有限公司",
    industry="新能源汽车",
    guest_name="张伟",
    visit_needs="考察智能制造产线和数字化转型方案",
)
engine = PortraitEngine(config, create_llm(config["llm"]), create_search(config["search"]))
result = engine.run(customer)
print(result.portrait)
```

## 运行阶段（三阶段 Loop 架构）

**阶段1 — 调研规划**（`keyword_extraction.txt`）
LLM 根据客户信息分析调研方向，按四个维度生成初始搜索词列表和背景判断。

**阶段2 — 多维研究循环**（`portrait.txt`）
LLM 自主搜索，维护四个维度的采集台账：
- `unit_background`（单位背景）
- `industry_status`（行业地位）
- `guest_profile`（主宾背景）
- `visit_needs`（来访动机）

每个维度满足验收标准后，LLM 调用 `mark_dimension_done` 标记完成。
内置新颖性检测：连续多轮无新 URL 时自动标记剩余维度穷举。
循环终止条件：所有维度解决 OR 达到 `max_queries_total` 次搜索上限。

**阶段3 — 画像合成**（`portrait_synthesis.txt`）
独立 LLM 调用，基于所有搜索结果和维度状态生成最终画像 JSON。

## 输出结构
返回 JSON 包含：
- `portrait.org_profile` — 单位规模、业务、近期动态
- `portrait.industry_position` — 行业地位、竞争格局
- `portrait.guest_profile` — 主宾身份、决策权限、公开立场
- `portrait.visit_motivation` — 明面需求 + 潜在动机 + 决策阶段
- `portrait.reception_focus` — 话题切入点、展示重点、互动建议
- `portrait.risk_alerts` — 敏感话题、竞争敏感点、信息缺口
- `confidence_assessment` — 各维度可信度（high/medium/low）
- `sources` — 来源 URL 列表
- `queries_executed` — 实际执行的搜索词

## 配置扩展
- **换 LLM**：修改 `config.yaml` 中 `llm.base_url` 和 `llm.model` 即可切换到任意 OpenAI-compatible 接口
- **换搜索引擎**：在 `src/search/` 下新增 adapter 类，实现 `SearchAdapter.search()` 接口，在 `create_search()` 中注册
- **调整 Prompt**：直接编辑 `prompts/` 下的 txt 文件，无需改代码（三个文件对应三个阶段）
- **调整搜索预算**：`engine.max_queries_total`（总搜索次数上限）
- **调整新颖性阈值**：`engine.novelty_stale_rounds`（连续无新URL多少轮后强制退出）
