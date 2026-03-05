#!/usr/bin/env python3
"""
LLM Client Module for China Political Interpretation
=====================================================

This module provides a unified interface for calling Gemini 3.1 Pro (or other LLMs)
for all analysis tasks in the political interpretation pipeline.

Configuration:
- Set GEMINI_API_KEY and GEMINI_API_URL in environment variables
- Or pass them directly to the client constructor
"""

import os
import json
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
from enum import Enum

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    from pathlib import Path
    env_file = Path(__file__).parent.parent.parent / "config" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


class AnalysisTask(Enum):
    """Types of analysis tasks that the LLM can perform."""
    # Content Understanding
    MATERIAL_UNDERSTANDING = "material_understanding"
    EXTRACT_KEY_ELEMENTS = "extract_key_elements"
    
    # Search Strategy
    GENERATE_SEARCH_STRATEGY = "generate_search_strategy"
    IDENTIFY_HISTORICAL_PEERS = "identify_historical_peers"
    IDENTIFY_REGIONAL_PEERS = "identify_regional_peers"
    
    # Deep Analysis
    POLICY_ANALYSIS = "policy_analysis"
    SEMANTIC_DIFF = "semantic_diff"
    TEMPORAL_COMPARISON = "temporal_comparison"  # 新增：纵向时间对比
    KEYWORD_EVOLUTION = "keyword_evolution"  # 新增：关键词演进分析
    POWER_ANALYSIS = "power_analysis"
    RISK_SCENARIO = "risk_scenario"
    BUSINESS_IMPACT = "business_impact"
    KPI_EXTRACTION = "kpi_extraction"
    CADRE_ANALYSIS = "cadre_analysis"
    DOCUMENT_CHUNKING = "document_chunking"
    
    # Report Generation
    GENERATE_HTML_REPORT = "generate_html_report"
    GENERATE_PDF_CONTENT = "generate_pdf_content"
    GENERATE_EXECUTIVE_SUMMARY = "generate_executive_summary"


@dataclass
class LLMConfig:
    """Configuration for the LLM client."""
    api_key: str
    api_url: str = "https://generativelanguage.googleapis.com/v1beta"
    model: str = "gemini-3-flash-preview"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: int = 120
    provider: str = "openai"  # "gemini" or "openai"


class LLMClient:
    """
    Unified LLM client for all analysis tasks.
    
    Usage:
        client = LLMClient()
        result = await client.analyze(
            task=AnalysisTask.MATERIAL_UNDERSTANDING,
            content="政策文件内容...",
            context={"additional": "context"}
        )
    """
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize the LLM client with configuration."""
        if config:
            self.config = config
        else:
            # Load from environment variables
            api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
            api_url = os.environ.get("LLM_API_URL") or os.environ.get("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta")
            model = os.environ.get("LLM_MODEL") or os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
            provider = os.environ.get("LLM_PROVIDER", "gemini")  # Default to Gemini
            
            self.config = LLMConfig(
                api_key=api_key,
                api_url=api_url,
                model=model,
                provider=provider
            )
        
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Token usage tracking
        self.last_token_usage: Optional[int] = None
        self.total_token_usage: int = 0
        
        # Prompt templates for different tasks
        self._prompts = self._load_prompt_templates()
    
    def _load_prompt_templates(self) -> Dict[AnalysisTask, str]:
        """Load prompt templates for different analysis tasks."""
        return {
            AnalysisTask.MATERIAL_UNDERSTANDING: """你是一位资深的中国政治分析专家。请仔细阅读以下政治材料，并提取关键信息。

## 材料内容
{content}

## 任务要求
请识别并提取以下信息：
1. **原始标题**：材料的原始标题是什么？（必须提取文章的真实标题，不要自己编造）
2. **发布日期**：材料的发布日期是哪一天？（格式：YYYY年M月D日）
3. **材料类型**：这是什么类型的文件？（会议文件/政策文件/讲话/公报/通知/新闻报道等）
4. **发布主体**：发布机构是什么？（中央/国务院/部委/地方/媒体等）
5. **时间信息**：明确的时间点或时间范围
6. **核心主题**：这份材料在讨论什么核心议题？
7. **关键人物**：提到了哪些重要人物？
8. **关键机构**：涉及哪些机构？
9. **政策信号**：传递了什么政策信号？
10. **新提法/新表述**：有哪些新的术语或表述？
11. **定量指标**：提取材料中所有具体的数字、百分比、金额、目标数量等量化信息

## 例行公文判断（重要！优先执行）

首先判断：这份材料是否是一份毫无实质性增量信息的例行表态文件？
- 如果是（如普通的地方学习贯彻会议、纯表态性发言），将 `is_routine_boilerplate` 设为 `true`，后续信号字段填空数组 `[]`
- **不要为了填表而强行捏造政策信号。政治分析的最高境界是敢于确认"没有变化"。**

## 上下文敏感分析原则（重要）

### 动态豁免机制
在识别政策信号和新表述时，必须注意以下规则：

1. **套话不等于废话**：以下常见表述如果在特定上下文中出现，可能含有重要信号：
   - "统筹推进"：如果后面跟着新的名词实体（如"统筹推进低空经济标准制定"），则这是新政策信号，必须保留
   - "底线思维"：如果在特定行业风险背景下出现（如"房地产领域底线思维"），则代表监管态度变化
   - "稳中求进"：如果搭配新领域（如"稳中求进发展量子科技"），则代表新方向

2. **上下文依存分析**：
   - 对每个"套话"进行依存句法分析
   - 判断其后是否跟着新的名词实体、新的修饰语、新的时间节点
   - 如果有上述要素，触发豁免规则，予以保留

3. **时间节点锚定**：
   - 某些在常规语境下是套话的句子，如果在特定时间节点（如行业危机后、重大会议后）出现，则属于"定调语"
   - 需要结合文档背景判断其重要性

4. "不变也是信号"：
   - 如果过去两年某行业经历了剧烈变化，但最新政策中关于该行业的表述与两年前一字不差
   - 这本身就是一个重要信号：政策滞后或高层共识未达成
   - 请在政策信号中标注这种"异常僵化"

请以JSON格式输出，结构如下：
```json
{{
    "is_routine_boilerplate": false,
    "original_title": "材料的原始标题（必须提取真实标题）",
    "publish_date": "YYYY年M月D日",
    "material_type": "材料类型",
    "issuing_body": "发布主体",
    "time_info": "时间信息",
    "core_topic": "核心主题",
    "key_persons": ["人物1", "人物2"],
    "key_institutions": ["机构1", "机构2"],
    "policy_signals": [
        {{
            "signal": "政策信号内容",
            "context": "上下文背景",
            "is_exempted": true/false,
            "exemption_reason": "如果是套话但被保留，说明原因"
        }}
    ],
    "new_expressions": ["新表述1", "新表述2"],
    "anomalous_static": [
        {{
            "content": "僵化表述内容",
            "context": "为何这是异常信号"
        }}
    ],
    "quantitative_kpis": [
        {{
            "indicator_name": "指标名称（如GDP增速目标、赤字率、专项债额度等）",
            "value": "本材料中的数值",
            "unit": "单位（%、亿元、万人等）",
            "context": "该数字出现的上下文"
        }}
    ],
    "summary": "一句话概括这份材料的核心内容"
}}
```""",

            AnalysisTask.GENERATE_SEARCH_STRATEGY: """你是一位资深的中国政治分析专家。基于对材料的理解，请生成智能检索策略。

## 材料理解
{material_understanding}

## 原始材料
{content}

## 任务要求
请生成横向和纵向的检索策略：

### 纵向检索（时间维度）
- 识别该材料对应的历史同类文件（如：历年同一会议的文件）
- 识别前序政策文件和后续执行文件
- 时间跨度建议覆盖3-5年

### 横向检索（空间维度）
- 识别各省市自治区同类会议/文件
- 识别相关部委的配套文件
- 识别官方媒体的解读文章

请以JSON格式输出，结构如下：
```json
{{
    "vertical_queries": [
        {{
            "query": "检索关键词",
            "description": "为什么要检索这个",
            "time_range": "时间范围",
            "expected_sources": ["预期信源"]
        }}
    ],
    "horizontal_queries": [
        {{
            "query": "检索关键词",
            "description": "为什么要检索这个",
            "scope": "检索范围（全国/特定省市/特定部委）",
            "expected_sources": ["预期信源"]
        }}
    ],
    "key_comparison_points": ["需要重点对比的内容点"]
}}
```""",

            AnalysisTask.IDENTIFY_HISTORICAL_PEERS: """你是一位资深的中国政治分析专家。请识别与当前材料相关的历史同类文件。

## 当前材料信息
{material_understanding}

## 任务要求
基于材料类型和主题，请列出应该检索的历史同类文件：
1. 如果是年度会议文件（如全国宣传部长会议），列出过去3-5年的同类会议文件
2. 如果是政策文件，列出该政策领域的前序文件
3. 如果是讲话，列出同一人物在同类场合的历史讲话

请以JSON格式输出：
```json
{{
    "meeting_type": "会议/文件类型",
    "historical_peers": [
        {{
            "year": "年份",
            "title": "预期标题",
            "search_query": "建议检索词",
            "importance": "为什么重要"
        }}
    ],
    "predecessor_policies": [
        {{
            "title": "政策名称",
            "year": "年份",
            "relevance": "与当前材料的关系"
        }}
    ]
}}
```""",

            AnalysisTask.IDENTIFY_REGIONAL_PEERS: """你是一位资深的中国政治分析专家。请识别与当前材料相关的地方/部门同类文件。

## 当前材料信息
{material_understanding}

## 任务要求
基于材料类型和主题，请列出应该检索的地方/部门文件：
1. 如果是中央会议，列出各省市自治区的对应会议
2. 如果是中央政策，列出相关部委的配套文件
3. 识别可能存在差异化执行的地区

请以JSON格式输出：
```json
{{
    "regional_peers": [
        {{
            "region": "省/市/自治区",
            "expected_document": "预期文件类型",
            "search_query": "建议检索词",
            "priority": "high/medium/low"
        }}
    ],
    "departmental_peers": [
        {{
            "department": "部委名称",
            "expected_document": "预期文件类型",
            "search_query": "建议检索词"
        }}
    ],
    "focus_regions": ["重点关注地区及原因"]
}}
```""",

            AnalysisTask.POLICY_ANALYSIS: """你是一位资深的中国政治分析专家。请对以下材料进行深度政策分析。

## 原始材料
{content}

## 检索到的横向材料
{horizontal_context}

## 检索到的纵向材料
{vertical_context}

## 重要约束（必须遵守）
1. **防幻觉**：如果上述横向材料或纵向材料为空、不相关或不足以支撑对比分析，请在相关字段输出 "N/A" 或空列表 []。**绝不允许基于你的预训练记忆自行编造历史文件或政策内容进行对比。**
2. **长文档分段分析**：如果材料超过5000字（如政府工作报告），请自动按核心领域（宏观经济/产业科技/民生就业/外交国防等）分段分析每个领域的政策信号，避免细节遗漏。

## 分析框架
请按照以下框架进行分析：

### 1. 核心判断（3-5条关键结论）
- 这份材料最重要的政策信号是什么？
- 标注每条判断的证据类型：F（事实）/I（推断）/S（情景）

### 2. 政策意图分析
- 显性目标：文件明确表述的目标
- 隐性目标：可能的政治考量
- 标注证据来源和置信度

### 3. 制度地图
- 牵头机构
- 协调机构
- 潜在否决点
- 执行路径

### 4. 权力信号与人事分析
- 人事信号：如涉及人事任免、领导分工等，请提取 [职务, 姓名, 分管领域] 三元组
- 运动式语言
- 中央-地方指令线索
- 派系/路线信号
- **世界知识补充通道**：结合公开资料，简述上述关键人物近6个月的履历变动背景。如果你不确定，请标注"无法确认"。

### 5. 定量指标对比
- 提取材料中的核心经济、产业、环保等量化指标（金额、百分比、目标数量）
- 与历史材料中的对应数值进行比对（升高/降低/持平/新设）

## 关键分析原则

### 词汇平替检测
对比历史材料，检测以下变化：
1. **概念替换（replacement）**：如"供给侧改革"→"新质生产力"，这代表政策框架的演进
2. **强度升级（strengthened）**：如"支持"→"大力推进"→"全面加速"，这代表政策力度升级
3. **强度降级（weakened）**：如"加快推进"→"稳妥推进"，这代表政策收紧或缓行
4. **消失表述**：某些表述完全消失，可能代表政策方向调整

### 政策强度判断标准
- **一级（关注）**：首次提及、列入规划、"探索"、"研究"
- **二级（推进）**："积极发展"、"稳步推进"、试点展开
- **三级（加码）**："大力发展"、"加快推进"、扩大试点
- **四级（强制）**："必须"、"严格执行"、全面推广、设置KPI

### 异常信号识别
1. **缺席信号**：该出现但未出现的表述（如某关键人物缺席重要会议）
2. **时滞异常**：地方响应速度明显慢于/快于常态
3. **表述僵化**：在环境剧变时表述未变，可能暗示政策滞后

请以JSON格式输出完整分析：
```json
{{
    "core_judgments": [
        {{
            "judgment": "判断内容",
            "evidence_type": "F/I/S",
            "confidence": "high/medium/low",
            "sources": ["证据来源"]
        }}
    ],
    "policy_intent": {{
        "explicit_goals": ["显性目标"],
        "implicit_goals": ["隐性目标"],
        "political_logic": "政治逻辑解释"
    }},
    "institutional_map": {{
        "lead_agency": "牵头机构",
        "coordination_bodies": ["协调机构"],
        "veto_points": ["否决点"],
        "execution_path": "执行路径"
    }},
    "power_signals": {{
        "personnel_signals": ["人事信号"],
        "cadre_tracking": [
            {{
                "name": "姓名",
                "position": "现任职务",
                "portfolio": "分管领域",
                "background": "近期履历背景（如有，不确定则填N/A）"
            }}
        ],
        "campaign_language": ["运动式语言"],
        "center_local_clues": ["中央地方线索"],
        "faction_signals": ["派系信号"]
    }},
    "vocabulary_changes": [
        {{
            "old_term": "旧表述",
            "new_term": "新表述",
            "change_type": "replacement/strengthened/weakened（只能从这三个词中选择）",
            "interpretation": "解读"
        }}
    ],
    "quantitative_kpis": [
        {{
            "indicator_name": "指标名称",
            "current_value": "本材料数值",
            "historical_value": "历史材料数值（如有，否则填N/A）",
            "trend": "up/down/flat/new",
            "policy_signal": "数字变化释放了什么信号"
        }}
    ],
    "policy_strength": {{
        "overall_level": "1-4",
        "key_indicators": ["判断依据"]
    }},
    "anomaly_signals": [
        {{
            "type": "absence/delay/rigidity",
            "content": "异常内容",
            "interpretation": "解读"
        }}
    ],
    "local_deviation": [
        {{
            "region": "地区",
            "type": "over-compliance/under-compliance/strict-alignment",
            "evidence": "具体形变证据",
            "interpretation": "解读"
        }}
    ]
}}
```""",
            AnalysisTask.SEMANTIC_DIFF: """你是一位资深的中国政治分析专家，擅长政治话语分析。请对比当前材料与历史材料的语义变化。

## 当前材料
{content}

## 历史对比材料
{historical_content}

## 重要约束
如果上述历史对比材料为空或不相关，请在所有对比字段中输出空列表 []，并在 overall_shift 中说明"无历史材料可供对比"。
**绝不允许基于你的预训练记忆自行编造历史文件进行对比。**

## 分析要求
请进行精细的话语对比分析：

1. **新增表述**：当前材料中出现但历史材料中没有的新表述
2. **消失表述**：历史材料中有但当前材料中消失的表述
3. **修饰语变化**：同一概念的修饰语强度变化（strengthened/weakened，只能从这两个词中选择）
4. **语序/结构变化**：议题排序或结构的变化
5. **政治含义解读**：这些变化背后可能的政治意图

请以JSON格式输出：
```json
{{
    "new_expressions": [
        {{
            "expression": "新表述",
            "context": "出现的上下文",
            "political_meaning": "可能的政治含义"
        }}
    ],
    "dropped_expressions": [
        {{
            "expression": "消失的表述",
            "original_context": "原来的上下文",
            "political_meaning": "消失可能意味着什么"
        }}
    ],
    "modifier_changes": [
        {{
            "concept": "概念",
            "old_modifier": "原修饰语",
            "new_modifier": "新修饰语",
            "direction": "strengthened/weakened",
            "interpretation": "解读"
        }}
    ],
    "structural_changes": [
        {{
            "change": "变化描述",
            "interpretation": "解读"
        }}
    ],
    "overall_shift": "总体语义变化方向及政治解读"
}}
```""",

            AnalysisTask.TEMPORAL_COMPARISON: """你是一位资深的中国政治分析专家，擅长纵向历史对比分析。请对比当前材料与历史同类文件。

## 当前材料
{current_content}

## 历史同类文件
{historical_content}

## 重要约束
如果上述历史同类文件为空或不相关，请在所有对比字段中输出空列表 []，并在 key_insights 中说明"无历史材料可供对比"。
**绝不允许基于你的预训练记忆自行编造历史文件进行对比。**

## 分析框架

### 1. 结构变化分析
- 议题排序变化：哪些议题被提前/延后？
- 新增章节：哪些新内容被纳入？
- 删减章节：哪些内容被移除？

### 2. 表述变化分析
- 词汇平替：同一概念使用不同表述（如"供给侧改革"→"新质生产力"）
- 强度变化：修饰语的强化或弱化
- 新提法：首次出现的重要表述

### 3. 政策信号演变
- 连续性：哪些政策方向保持不变？
- 转向：哪些政策方向发生转变？
- 加速：哪些政策被提到更高优先级？
- 放缓：哪些政策优先级下降？

### 4. 时滞分析
- 从中央到地方的传导时间
- 从政策发布到落地执行的时间差

请以JSON格式输出：
```json
{{
    "structural_changes": [
        {{
            "change_type": "added/removed/reordered",
            "content": "变化内容",
            "interpretation": "解读"
        }}
    ],
    "vocabulary_evolution": [
        {{
            "old_term": "旧表述",
            "new_term": "新表述",
            "year_first_appeared": "首次出现年份",
            "political_meaning": "政治含义"
        }}
    ],
    "policy_trajectory": {{
        "continued": ["延续的方向"],
        "pivoted": ["转向的方向"],
        "accelerated": ["加速的方向"],
        "slowed": ["放缓的方向"]
    }},
    "time_lag": {{
        "central_to_local_days": 天数,
        "policy_to_implementation_days": 天数,
        "interpretation": "时滞解读"
    }},
    "key_insights": ["核心洞察1", "核心洞察2"]
}}
```""",

            AnalysisTask.KEYWORD_EVOLUTION: """你是一位资深的中国政治分析专家。请分析关键词在不同时期的使用频率和语义变化。

## 关键词列表
{keywords}

## 历史使用情况
{historical_usage}

## 分析要求

### 1. 频率变化
- 统计每个关键词在不同年份的出现频率
- 识别频率显著上升/下降的关键词

### 2. 语义演变
- 同一关键词在不同时期的含义变化
- 搭配词语的变化

### 3. 新旧替代
- 哪些新关键词替代了旧关键词？
- 替代的政治逻辑是什么？

请以JSON格式输出：
```json
{{
    "frequency_changes": [
        {{
            "keyword": "关键词",
            "trend": "rising/falling/stable",
            "frequency_by_year": {{"2022": 10, "2023": 15, "2024": 25}},
            "interpretation": "解读"
        }}
    ],
    "semantic_shifts": [
        {{
            "keyword": "关键词",
            "old_meaning": "旧含义",
            "new_meaning": "新含义",
            "context_change": "上下文变化"
        }}
    ],
    "replacements": [
        {{
            "old_keyword": "旧关键词",
            "new_keyword": "新关键词",
            "replacement_year": "替代年份",
            "political_logic": "政治逻辑"
        }}
    ],
    "emerging_keywords": ["新兴关键词1", "新兴关键词2"],
    "fading_keywords": ["消退关键词1", "消退关键词2"]
}}
```""",

            AnalysisTask.RISK_SCENARIO: """你是一位资深的中国政治分析专家。请基于分析结果，构建风险情景树。

## 政策分析结果
{policy_analysis}

## 任务要求
请构建未来3-12个月的情景分析：

1. **基准情景**（概率最高）
2. **乐观情景**（政策超预期推进）
3. **悲观情景**（政策遇阻或收紧）
4. **尾部风险**（概率<10%的极端情况）

每个情景需要包含：
- 触发条件
- 发展路径
- 关键指标
- 影响评估

请以JSON格式输出：
```json
{{
    "scenarios": [
        {{
            "name": "情景名称",
            "type": "baseline/optimistic/pessimistic/tail_risk",
            "probability": "概率估计",
            "trigger_conditions": ["触发条件"],
            "development_path": "发展路径描述",
            "key_indicators": ["关键观察指标"],
            "impact_assessment": "影响评估",
            "timeline": "时间窗口"
        }}
    ],
    "watch_list": [
        {{
            "indicator": "观察指标",
            "threshold": "阈值/触发点",
            "scenario_triggered": "触发哪个情景"
        }}
    ]
}}
```""",

            AnalysisTask.BUSINESS_IMPACT: """你是一位资深的中国政治分析专家，同时具备商业战略视角。请分析政策对商业的影响。

## 政策分析结果
{policy_analysis}

## 任务要求
请从商业和合规角度分析：

1. **受益行业/企业**
2. **受损行业/企业**
3. **合规风险点**
4. **商业机会**
5. **行动建议**
6. **影响时效**：每个受益/受损判断需标注时间刻度 — immediate（3个月内）/ short_term（1年内）/ long_term（3-5年）

请以JSON格式输出：
```json
{{
    "winners": [
        {{
            "sector": "行业/领域",
            "reason": "受益原因",
            "specific_opportunities": ["具体机会"],
            "impact_timeline": "immediate/short_term/long_term"
        }}
    ],
    "losers": [
        {{
            "sector": "行业/领域",
            "reason": "受损原因",
            "risk_level": "high/medium/low",
            "impact_timeline": "immediate/short_term/long_term"
        }}
    ],
    "compliance_risks": [
        {{
            "risk": "风险描述",
            "affected_entities": ["受影响主体"],
            "mitigation": "缓解措施"
        }}
    ],
    "action_items": [
        {{
            "urgency": "immediate/short_term/medium_term",
            "action": "建议行动",
            "rationale": "理由"
        }}
    ]
}}
```""",

            AnalysisTask.GENERATE_EXECUTIVE_SUMMARY: """你是一位资深的中国政治分析专家。请生成执行摘要。

## 完整分析结果
{full_analysis}

## 任务要求
请生成一份简洁有力的执行摘要，适合高管快速阅读：

1. **核心结论**（3条以内）
2. **关键风险**（2条以内）
3. **行动建议**（2条以内）
4. **观察清单**（3条以内）

请以JSON格式输出：
```json
{{
    "title": "分析标题",
    "date": "分析日期",
    "core_conclusions": ["结论1", "结论2"],
    "key_risks": ["风险1", "风险2"],
    "action_items": ["建议1", "建议2"],
    "watch_list": ["观察点1", "观察点2", "观察点3"],
    "one_liner": "一句话总结"
}}
```""",

            AnalysisTask.GENERATE_HTML_REPORT: """你是一位专业的前端开发者和中国政治分析专家。请基于分析结果生成现代化的HTML报告。

## 完整分析数据
{analysis_data}

## 设计要求
生成一个现代化、可交互的HTML报告，要求：

### 1. 视觉设计
- 现代简洁的设计风格，使用 Tailwind CSS（通过 CDN 引入）
- 深色/浅色主题切换（使用 CSS 变量实现）
- 专业的配色方案：主色调使用深蓝色系，强调色使用金色/橙色
- 清晰的视觉层次，使用卡片式布局

### 2. 必须包含的可视化组件

#### 政策演进时间轴
- 使用纯 HTML/CSS 实现垂直时间轴
- 显示政策从提出到当前的关键节点
- 每个节点显示：日期、事件、政策强度（用颜色深浅表示）
- **重要布局规则**：时间轴线必须在最左侧，内容区域必须有足够的左边距（至少 40px），确保文字不会与线条重叠
- 示例结构和样式：
```html
<style>
.timeline {{ position: relative; padding-left: 20px; }}
.timeline::before {{ 
  content: ''; 
  position: absolute; 
  left: 8px; 
  top: 0; 
  bottom: 0; 
  width: 2px; 
  background: #e5e7eb; 
}}
.timeline-item {{ position: relative; padding-left: 40px; margin-bottom: 24px; }}
.timeline-marker {{ 
  position: absolute; 
  left: 0; 
  top: 4px; 
  width: 16px; 
  height: 16px; 
  border-radius: 50%; 
  background: #3b82f6;
}}
.timeline-content {{ padding-left: 8px; }}
</style>
<div class="timeline">
  <div class="timeline-item">
    <div class="timeline-marker"></div>
    <div class="timeline-content">
      <span class="date font-semibold text-blue-600">2024年1月</span>
      <h4 class="font-bold mt-1">政策发布</h4>
      <p class="text-gray-600 mt-1">描述内容</p>
    </div>
  </div>
</div>
```

#### 词汇变化热力图
- 使用简单的 HTML 表格实现
- 显示关键词在不同时期的出现频率变化
- 频率用颜色深浅表示（浅=低频，深=高频）
- 示例结构：
```html
<table class="heatmap">
  <thead><tr><th>关键词</th><th>2022</th><th>2023</th><th>2024</th></tr></thead>
  <tbody>
    <tr><td>新质生产力</td><td class="freq-0">-</td><td class="freq-2">提及</td><td class="freq-4">高频</td></tr>
  </tbody>
</table>
```

#### 核心判断卡片
- 每个判断使用独立卡片
- 左侧显示证据类型标签（F/I/S）
- 不同证据类型用不同颜色：F=蓝色、I=橙色、S=紫色
- 置信度用进度条或星级表示

### 3. 交互功能
- 可折叠/展开的章节（使用 details/summary 标签）
- 悬浮导航栏（固定在顶部）
- 平滑滚动（scroll-behavior: smooth）
- 证据标签悬浮提示
- 表格排序功能（可选）

### 4. 内容结构
```
1. 执行摘要（置顶，带背景色高亮）
2. 核心判断（卡片式布局）
3. 政策演进时间轴
4. 词汇变化热力图
5. 政策意图分析
6. 制度地图
7. 权力信号分析
8. 风险情景树
9. 商业影响分析
10. 附录：证据表格
```

### 5. 技术要求
- 使用 Tailwind CSS CDN: <script src="https://cdn.tailwindcss.com"></script>
- 所有 CSS 内联或使用 Tailwind 类
- 可以使用简单的 JavaScript 实现交互
- 确保报告可以独立打开，无需外部依赖

请直接输出完整的HTML代码（包含内联CSS和JavaScript），不要使用代码块包裹：""",

            AnalysisTask.GENERATE_PDF_CONTENT: """你是一位专业的文档设计师和中国政治分析专家。请基于分析结果生成结构化的PDF内容。

## 完整分析数据
{analysis_data}

## 标题命名规范（非常重要！）
报告标题必须采用以下格式：
- 格式：「[YYYY年M月D日] [XX会议/事件名称] 解读」
- 示例：「2026年2月27日 中共中央政治局会议解读」
- 从分析数据中提取会议/事件的具体日期和名称
- 不要使用模糊的内容描述作为标题

## 设计要求
生成结构清晰、适合打印的PDF内容，要求：

### 1. 文档结构（按顺序）

#### 封面页
```
【标题】政策分析报告
【副标题】材料主题
【日期】分析日期
【机构】发布主体
```

#### 目录（自动生成）
列出所有章节及页码

#### 执行摘要（独立页）
- 一句话核心结论
- 关键发现（3条以内）
- 风险提示（2条以内）
- 行动建议（2条以内）

#### 正文内容
```
一、材料概况
    1.1 材料类型
    1.2 发布背景
    1.3 核心主题

二、核心判断
    2.1 判断一：[标题]
        - 判断内容
        - 证据类型：F/I/S
        - 置信度：高/中/低
        - 证据来源
    2.2 判断二：[标题]
    ...

三、政策意图分析
    3.1 显性目标
    3.2 隐性目标
    3.3 政治逻辑

四、词汇变化分析
    4.1 新增表述
    4.2 消失表述
    4.3 强度变化
    4.4 语义对比表格

五、制度地图
    5.1 牵头机构
    5.2 协调机制
    5.3 执行路径
    5.4 潜在否决点

六、权力信号分析
    6.1 人事信号
    6.2 运动式语言
    6.3 中央-地方线索

七、风险情景
    7.1 基准情景
    7.2 乐观情景
    7.3 悲观情景
    7.4 尾部风险

八、商业影响
    8.1 受益领域
    8.2 风险领域
    8.3 合规要点

九、附录
    9.1 证据表格
    9.2 检索来源
    9.3 方法说明
```

### 2. 格式要求
- 使用 Markdown 格式输出
- 标题层级：# 一级标题、## 二级标题、### 三级标题
- 重点内容使用 **粗体** 标注
- 列表使用有序编号或无序符号
- 表格使用 Markdown 表格语法

### 3. 表格样式
```markdown
| 项目 | 内容 | 来源 | 置信度 |
|------|------|------|--------|
| 判断1 | ... | [F] | 高 |
```

### 4. 专业性要求
- 避免口语化表达
- 使用专业的政策分析术语
- 每个判断必须有证据支撑
- 保持客观中立的分析立场

请以Markdown格式输出完整的报告内容：""",

            AnalysisTask.KPI_EXTRACTION: """你是一位中国宏观经济分析师。请从材料中精准提取所有核心量化指标，并与历史数据对比。

## 当前材料
{content}

## 历史对比材料（如有）
{historical_content}

## 任务要求
精准提取材料中涉及的所有核心经济、产业、环保等量化指标。

### 重点关注（如存在）
- GDP预期增速目标
- 城镇新增就业人数目标
- 居民消费价格（CPI）涨幅目标
- 赤字率
- 地方政府专项债券额度
- 超长期特别国债发行额度
- 军费预算增幅
- 研发经费投入强度
- 其他任何具体的数字目标或承诺

### 重要约束
如果历史对比材料为空，请在 historical_value 字段填 "N/A"。**绝不允许编造历史数据。**

请以JSON格式输出：
```json
{{
    "macro_kpis": [
        {{
            "indicator_name": "指标名称",
            "current_year_value": "本年度数值",
            "historical_value": "上年度数值（如有，否则N/A）",
            "trend": "up/down/flat/new",
            "policy_signal": "这个数字变化释放了什么信号？"
        }}
    ],
    "total_indicators_found": 0,
    "has_significant_changes": false,
    "key_takeaway": "一句话概括量化指标释放的整体信号"
}}
```""",

            AnalysisTask.CADRE_ANALYSIS: """你是一位资深的中国政治分析专家，专注于人事任命与权力结构分析。

## 材料内容
{content}

## 任务要求
请对这份涉及人事任免/领导分工/组织调整的材料进行结构化分析。

### 1. 人事三元组提取
对材料中每一位涉及的人物，提取 [职务, 姓名, 分管领域] 三元组。

### 2. 变动比对
如有前序分工信息，识别：
- 新增人物：此前不在该班子中的人物
- 退出人物：此前在但现在不在的人物
- 分工调整：同一人物分管领域的变化

### 3. 背景分析（世界知识通道）
结合公开资料，为关键人物补充：
- 此前任何职务？何时到任？
- 年龄/届期信息（如可判断）
- 派系/学历/从政路径特征

如果你不确定某项信息，请标注"无法确认"，**绝不编造**。

请以JSON格式输出：
```json
{{
    "cadre_roster": [
        {{
            "name": "姓名",
            "position": "职务",
            "portfolio": "分管领域",
            "is_new": true/false,
            "previous_position": "此前职务（如有，否则N/A）",
            "background_notes": "背景简述"
        }}
    ],
    "changes_detected": [
        {{
            "change_type": "new_appointment/departure/portfolio_change",
            "person": "涉及人物",
            "detail": "具体变动内容",
            "political_signal": "这个变动释放了什么信号？"
        }}
    ],
    "overall_assessment": "整体人事调整的政治含义评估"
}}
```""",

            AnalysisTask.DOCUMENT_CHUNKING: """你是一位中国政策文件结构化专家。请将以下长篇文件按核心领域切分为独立的分析单元。

## 文件内容
{content}

## 任务要求
将文件内容按以下领域切分（只保留文件中实际涉及的领域，不要凭空创造）：

可能的领域包括但不限于：
- 宏观经济与财政货币政策
- 现代化产业体系与科技创新
- 扩大内需与消费
- 房地产与地方债务风险
- 民生、就业与社会保障
- 乡村振兴与农业
- 生态环保与绿色发展
- 对外开放与外贸
- 外交、国防与安全
- 港澳台
- 党建与反腐

## 输出要求
- 每个切片必须是原文的**精确摘录**（可以略做整理，但不能改变原文措辞）
- 每个切片应独立可读，包含该领域的完整内容
- 如果某段落同时涉及多个领域，放入最主要的那个领域

请以JSON格式输出：
```json
{{
    "chunks": [
        {{
            "domain": "领域名称",
            "title": "该段落的核心议题（一句话）",
            "content": "该领域的原文内容（精确摘录）",
            "char_count": 字符数
        }}
    ],
    "total_chunks": 0,
    "document_type": "文件类型判断"
}}
```""",
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def analyze(
        self,
        task: AnalysisTask,
        content: str = "",
        context: Optional[Dict[str, Any]] = None,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform an analysis task using the LLM.
        
        Args:
            task: The type of analysis to perform
            content: The main content to analyze
            context: Additional context for the analysis
            custom_prompt: Override the default prompt template
            
        Returns:
            Dict containing the analysis results
        """
        if not self.config.api_key:
            raise ValueError("GEMINI_API_KEY is not configured. Please set the environment variable or pass it to the constructor.")
        
        # Extract user_focus before formatting (it's not a prompt template variable)
        user_focus = ""
        if context and "user_focus" in context:
            user_focus = context.pop("user_focus", "")
        
        # Build the prompt
        if custom_prompt:
            prompt = custom_prompt
        else:
            template = self._prompts.get(task, "")
            if not template:
                raise ValueError(f"No prompt template found for task: {task}")
            
            # Format the template with provided content and context
            format_args = {"content": content}
            if context:
                format_args.update(context)
            
            try:
                prompt = template.format(**format_args)
            except KeyError as e:
                raise ValueError(f"Missing required context key: {e}")
        
        # Inject user focus guidance if provided
        if user_focus:
            prompt += f"""

## ⚠️ 用户特别关注
用户希望你在分析中重点关注以下方面：
{user_focus}

请在你的分析中优先、重点回应用户的关注点，围绕用户关心的方向展开深入分析。"""
        
        # Call the LLM
        result = await self._call_gemini(prompt)
        
        # Try to parse JSON response
        return self._parse_response(result, task)
    
    async def _call_gemini(self, prompt: str) -> str:
        """Call the LLM API and return the response text."""
        # Route to appropriate provider
        if self.config.provider == "openai":
            return await self._call_openai_compatible(prompt)
        else:
            return await self._call_gemini_native(prompt)
    
    async def _call_openai_compatible(self, prompt: str) -> str:
        """Call OpenAI-compatible API (e.g., company proxy)."""
        session = await self._get_session()
        
        # Build the API URL for chat completions
        url = f"{self.config.api_url}/chat/completions"
        
        # Build request body (OpenAI format)
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.config.temperature,
        }
        
        if self.config.max_tokens:
            body["max_tokens"] = self.config.max_tokens
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }
        
        try:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error ({response.status}): {error_text}")
                
                data = await response.json()
                
                # Extract token usage from OpenAI response
                if "usage" in data:
                    usage = data["usage"]
                    self.last_token_usage = usage.get("total_tokens", 0)
                    self.total_token_usage += self.last_token_usage or 0
                    print(f"[LLM] Token usage: {self.last_token_usage} (total: {self.total_token_usage})")
                
                # Extract text from OpenAI response format
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        return choice["message"]["content"]
                
                raise Exception(f"Unexpected OpenAI API response format: {data}")
                
        except asyncio.TimeoutError:
            raise Exception(f"OpenAI API timeout after {self.config.timeout} seconds")
    
    async def _call_gemini_native(self, prompt: str) -> str:
        """Call the native Gemini API."""
        session = await self._get_session()
        
        # Build the API URL
        url = f"{self.config.api_url}/models/{self.config.model}:generateContent"
        
        # Build request body
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.config.temperature,
            }
        }
        
        if self.config.max_tokens:
            body["generationConfig"]["maxOutputTokens"] = self.config.max_tokens
        
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.config.api_key
        }
        
        try:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Gemini API error ({response.status}): {error_text}")
                
                data = await response.json()
                
                # Extract token usage from response
                if "usageMetadata" in data:
                    usage = data["usageMetadata"]
                    self.last_token_usage = usage.get("totalTokenCount", 0)
                    self.total_token_usage += self.last_token_usage or 0
                    print(f"[LLM] Token usage: {self.last_token_usage} (total: {self.total_token_usage})")
                
                # Extract text from response
                if "candidates" in data and len(data["candidates"]) > 0:
                    candidate = data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]
                        if len(parts) > 0 and "text" in parts[0]:
                            return parts[0]["text"]
                
                raise Exception(f"Unexpected Gemini API response format: {data}")
                
        except asyncio.TimeoutError:
            raise Exception(f"Gemini API timeout after {self.config.timeout} seconds")
    
    def _parse_response(self, response: str, task: AnalysisTask) -> Dict[str, Any]:
        """Parse the LLM response, extracting JSON if present."""
        # For HTML generation, return the raw response
        if task == AnalysisTask.GENERATE_HTML_REPORT:
            return {"html": response}
        
        # For PDF content, return the raw markdown
        if task == AnalysisTask.GENERATE_PDF_CONTENT:
            return {"markdown": response}
        
        # Try to extract JSON from the response
        try:
            # Look for JSON in code blocks
            import re
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
            # Try to parse the whole response as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw response
            return {"raw_response": response}
    
    async def stream_analyze(
        self,
        task: AnalysisTask,
        content: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream analysis results from the LLM.
        
        Yields chunks of the response as they arrive.
        """
        if not self.config.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        
        template = self._prompts.get(task, "")
        format_args = {"content": content}
        if context:
            format_args.update(context)
        prompt = template.format(**format_args)
        
        session = await self._get_session()
        url = f"{self.config.api_url}/models/{self.config.model}:streamGenerateContent"
        
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.config.temperature}
        }
        
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.config.api_key
        }
        
        async with session.post(url, json=body, headers=headers) as response:
            async for line in response.content:
                if line:
                    try:
                        data = json.loads(line)
                        if "candidates" in data:
                            text = data["candidates"][0]["content"]["parts"][0].get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue


# Convenience functions for direct use
_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


async def analyze_material(content: str) -> Dict[str, Any]:
    """Analyze material to understand its type, topic, and key elements."""
    client = get_client()
    return await client.analyze(AnalysisTask.MATERIAL_UNDERSTANDING, content)


async def generate_search_strategy(content: str, material_understanding: Dict) -> Dict[str, Any]:
    """Generate intelligent search strategy based on material understanding."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.GENERATE_SEARCH_STRATEGY,
        content,
        {"material_understanding": json.dumps(material_understanding, ensure_ascii=False)}
    )


async def identify_historical_peers(material_understanding: Dict) -> Dict[str, Any]:
    """Identify historical peer documents for vertical comparison."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.IDENTIFY_HISTORICAL_PEERS,
        context={"material_understanding": json.dumps(material_understanding, ensure_ascii=False)}
    )


async def identify_regional_peers(material_understanding: Dict) -> Dict[str, Any]:
    """Identify regional/departmental peer documents for horizontal comparison."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.IDENTIFY_REGIONAL_PEERS,
        context={"material_understanding": json.dumps(material_understanding, ensure_ascii=False)}
    )


async def analyze_policy(
    content: str,
    horizontal_context: str,
    vertical_context: str
) -> Dict[str, Any]:
    """Perform deep policy analysis with horizontal and vertical context."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.POLICY_ANALYSIS,
        content,
        {
            "horizontal_context": horizontal_context,
            "vertical_context": vertical_context
        }
    )


async def analyze_semantic_diff(
    content: str,
    historical_content: str
) -> Dict[str, Any]:
    """Analyze semantic differences between current and historical documents."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.SEMANTIC_DIFF,
        content,
        {"historical_content": historical_content}
    )


async def generate_risk_scenarios(policy_analysis: Dict) -> Dict[str, Any]:
    """Generate risk scenarios based on policy analysis."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.RISK_SCENARIO,
        context={"policy_analysis": json.dumps(policy_analysis, ensure_ascii=False)}
    )


async def analyze_business_impact(policy_analysis: Dict) -> Dict[str, Any]:
    """Analyze business and compliance impact."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.BUSINESS_IMPACT,
        context={"policy_analysis": json.dumps(policy_analysis, ensure_ascii=False)}
    )


async def generate_executive_summary(full_analysis: Dict) -> Dict[str, Any]:
    """Generate executive summary from full analysis."""
    client = get_client()
    return await client.analyze(
        AnalysisTask.GENERATE_EXECUTIVE_SUMMARY,
        context={"full_analysis": json.dumps(full_analysis, ensure_ascii=False)}
    )


async def generate_html_report(analysis_data: Dict) -> str:
    """Generate modern interactive HTML report."""
    client = get_client()
    result = await client.analyze(
        AnalysisTask.GENERATE_HTML_REPORT,
        context={"analysis_data": json.dumps(analysis_data, ensure_ascii=False, indent=2)}
    )
    return result.get("html", "")


async def generate_pdf_content(analysis_data: Dict) -> str:
    """Generate structured PDF content in markdown format."""
    client = get_client()
    result = await client.analyze(
        AnalysisTask.GENERATE_PDF_CONTENT,
        context={"analysis_data": json.dumps(analysis_data, ensure_ascii=False, indent=2)}
    )
    return result.get("markdown", "")


# CLI interface for testing
if __name__ == "__main__":
    import argparse
    from pathlib import Path
    
    parser = argparse.ArgumentParser(description="LLM Client for China Political Interpretation")
    parser.add_argument("--test", action="store_true", help="Run a test query")
    parser.add_argument("--content", type=str, help="Content to analyze")
    parser.add_argument("--task", type=str, default="material_understanding", 
                       help="Analysis task to perform")
    
    args = parser.parse_args()
    
    if args.test:
        async def test():
            # Load .env file explicitly
            env_file = Path(__file__).parent.parent.parent / "config" / ".env"
            if env_file.exists():
                from dotenv import load_dotenv
                load_dotenv(env_file)
                print(f"Loaded .env from: {env_file}")
            
            client = LLMClient()
            test_content = """
            2024 年全国宣传部长会议 1 月 5 日至 6 日在京召开。会议强调，要深入学习贯彻习近平文化思想，
            围绕贯彻落实党的二十大精神，聚焦用党的创新理论武装全党、教育人民这个首要政治任务，
            着力加强党对宣传思想文化工作的全面领导，着力建设具有强大凝聚力和引领力的社会主义意识形态。
            """
            
            print("Testing LLM Client...")
            print(f"API Key configured: {'Yes' if client.config.api_key else 'No'}")
            print(f"Model: {client.config.model}")
            print(f"API URL: {client.config.api_url}")
            
            if client.config.api_key:
                result = await client.analyze(
                    AnalysisTask.MATERIAL_UNDERSTANDING,
                    test_content
                )
                print("\n✅ LLM Analysis Result:")
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("\n❌ Please set GEMINI_API_KEY environment variable to test.")
            
            await client.close()
        
        asyncio.run(test())
