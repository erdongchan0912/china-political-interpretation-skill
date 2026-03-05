# 中国政策解读工具 (China Policy Analyzer)

一站式政策文件分析平台，使用大模型自动解读中国政策文件，生成多维度分析报告。

## 功能特性

- **多源内容提取**：支持 URL 链接、PDF 文件、微信公众号文章
- **LLM 深度分析**：政策意图、语义对比、权力信号、风险情景、商业影响
- **智能材料路由**：自动识别经济类/人事类文件，触发专属分析模块
- **可视化报告**：HTML 交互式报告 + PDF 打印版报告
- **浏览器通知**：报告生成后自动推送桌面通知
- **历史记录管理**：所有分析任务的归档与回顾

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/erdongchan0912/china-political-interpretation-skill.git
cd china-political-interpretation-skill
```

### 2. 安装依赖

```bash
# 后端 Python 依赖
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 前端 Node 依赖
cd ../frontend
npm install
```

### 3. 配置 API Keys

```bash
# 复制配置模板
cp config/.env.example config/.env
```

编辑 `config/.env` 文件，填入你的 API Keys：

```env
# Google Gemini API (推荐)
# 从 https://aistudio.google.com/app/apikey 获取
GEMINI_API_KEY=your-gemini-api-key-here

# Tavily Search API
# 从 https://tavily.com/ 获取（免费 1000次/月）
TAVILY_API_KEY=your-tavily-api-key-here
```

### 4. 启动服务

```bash
# 一键启动（前端 + 后端）
./start.sh

# 或分别启动：
# 后端: cd backend && python -m api.app
# 前端: cd frontend && npm run dev
```

启动后访问 http://localhost:5173

## API 配置选项

本项目支持多种 LLM 和搜索引擎配置：

### LLM 提供商

| 提供商 | 配置 | 说明 |
|--------|------|------|
| Google Gemini | `LLM_PROVIDER=gemini` | 推荐，需要 `GEMINI_API_KEY` |
| OpenAI 兼容 API | `LLM_PROVIDER=openai` | 支持任何 OpenAI 格式的 API |

### 搜索引擎

| 引擎 | 配置 | 说明 |
|------|------|------|
| Tavily | `SEARCH_API_PROVIDER=tavily` | 推荐，专为 AI 设计 |
| Google Custom Search | `SEARCH_API_PROVIDER=google` | 需要配置搜索引擎 ID |

## 微信公众号文章提取（可选）

> ⚠️ 如果不安装以下依赖，微信链接仍可用通用 HTTP 方式提取，但效果可能不如专用提取。

```bash
pip install wechat-article-to-markdown
```

**提取策略**：
1. 轻量级优先 — 先用 HTTP + BeautifulSoup 直接解析
2. 浏览器兜底 — 仅当轻量级提取失败时启动 camoufox 浏览器
3. 通用降级 — 如果专用提取失败，自动降级为通用网页提取

## 项目结构

```
.
├── backend/           # Python 后端
│   ├── api/          # FastAPI 服务
│   ├── core/         # 核心分析模块
│   └── reports/      # 报告生成器
├── frontend/          # React 前端
│   └── src/
│       └── components/
├── config/            # 配置文件
│   └── .env.example
└── tests/             # 测试用例
```

## 开发

```bash
# 运行测试
cd tests
python test_simple_api.py

# 重启后端
./restart-backend.sh
```

## 许可证

MIT License

## 致谢

- [Google Gemini](https://ai.google.dev/) - LLM 服务
- [Tavily](https://tavily.com/) - AI 搜索服务
