# Species 2000 China 动物信息爬取脚本

本项目用于自动化爬取 Species 2000 China / CoL China 相关网页中的动物物种信息，重点采集物种详情页中的 **形态描述**、**生物学** 和 **生态学** 三类文本字段，并将每个物种保存为独立的 TXT 文件，便于后续知识抽取、语料整理和知识图谱构建。

项目面向 `http://col.especies.cn/CoLChina` 及其对应的 Species 2000 China 物种分类树页面设计。脚本中的默认分类树入口为 `http://www.especies.cn/baike/taxon/sp2000TaxaTree_2023/`，可通过配置目标分类名称，递归遍历指定动物类群下的多级分类页面。

## 功能特点

- 支持从指定分类节点开始递归遍历物种分类树。
- 支持多级分类页面解析，可从纲、目、科等层级逐级进入下级分类，直到物种级别。
- 支持分类表格自动翻页，避免遗漏同一分类页面中的分页数据。
- 支持断点续爬，通过已爬取 URL 记录文件跳过已完成物种。
- 使用 Selenium Edge 模拟真实浏览器访问，降低访问限制、超时、重定向等问题带来的影响。
- 支持页面加载重试、关键元素等待、请求延迟和调试 HTML 保存。
- 支持从接口数据和页面 DOM 中提取描述字段，提高字段获取成功率。
- 对 HTML 标签、冗余标题、特殊符号和空内容进行清洗与规范化。
- 按物种中文名生成独立 TXT 文件，输出格式统一、便于后续处理。

## 技术栈

- Python 3
- Selenium
- Microsoft Edge WebDriver
- webdriver-manager
- BeautifulSoup4
- 正则表达式
- JavaScript DOM / Fetch 调用

## 项目结构

```text
.
|-- get_info.py                  # 主爬虫脚本
|-- species_data/                # 默认输出目录，保存物种 TXT 文件
|-- crawled_species_urls.txt     # 断点续爬记录文件
`-- debug_pages/                 # 调试页面保存目录
```

以上目录中，`species_data/`、`crawled_species_urls.txt` 和 `debug_pages/` 会在脚本运行过程中按需生成。

## 安装依赖

```bash
pip install -U selenium webdriver-manager beautifulsoup4
```

运行前请确保本机已安装 Microsoft Edge 浏览器，并准备与浏览器版本匹配的 Edge WebDriver。脚本既支持手动指定本地 `msedgedriver.exe`，也支持通过 `webdriver-manager` 自动获取驱动。

## 运行方式

```bash
python get_info.py
```

脚本启动后会按照 `TARGET_TAXA` 中配置的目标分类依次构建起始 URL，并递归遍历其下级分类与物种详情页。

## 关键配置

可在 `get_info.py` 顶部配置区调整以下参数：

```python
BASE_URL = "http://www.especies.cn/baike/taxon/sp2000TaxaTree_2023/"

TARGET_TAXA = [
    "Mammalia",
    "Reptilia",
]

OUTPUT_DIR = "species_data"
CRAWLED_RECORD_FILE = "crawled_species_urls.txt"

REQUEST_DELAY_SECONDS = 1
PAGE_WAIT_SECONDS = 18
MAX_RETRIES = 3
HEADLESS = True
EDGEDRIVER_PATH = "C:/path/to/msedgedriver.exe"
```

常用配置说明：

- `TARGET_TAXA`：目标分类列表。可填写 `Mammalia`、`Reptilia`、`Chordata`、`Arthropoda` 等分类拉丁名。
- `OUTPUT_DIR`：物种文本文件输出目录。
- `CRAWLED_RECORD_FILE`：已完成物种 URL 记录文件，用于断点续爬。
- `REQUEST_DELAY_SECONDS`：请求间隔。若触发访问限制，可适当调大。
- `PAGE_WAIT_SECONDS`：等待页面关键元素加载的最长时间。
- `MAX_RETRIES`：页面加载失败后的最大重试次数。
- `HEADLESS`：是否使用无头浏览器模式。
- `EDGEDRIVER_PATH`：本地 EdgeDriver 路径。若留空，脚本会尝试使用 `webdriver-manager` 或 Selenium Manager。

## 输出格式

每个物种会生成一个独立的 TXT 文件，文件名优先使用物种中文名。文件内容格式如下：

```text
【形态描述】
...

【生物学】
...

【生态学】
...
```

当某个字段没有抓取到有效内容时，脚本会写入空值占位，确保所有输出文件结构保持一致。

## 实现思路

### 1. 多级分类递归遍历与自动翻页

脚本先加载目标分类页面，使用 BeautifulSoup 解析页面中的分类表格，提取分类等级、拉丁名、中文名和详情链接。对于非物种节点，脚本继续递归访问下级分类；对于物种节点，进入详情页抓取描述字段。

由于同一分类页面可能包含多页数据，脚本会通过 DataTables 分页信息、分页按钮或页面文本中的总数信息计算页数，并逐页切换、汇总所有子级条目。爬取过程中会对 URL 去重，避免重复处理同一节点。

### 2. 反爬与页面加载稳定性处理

脚本使用 Microsoft Edge Selenium 作为拟真浏览器，并配置真实 User-Agent、请求头、窗口大小、自动化特征隐藏、代理清理等参数，以提升页面访问稳定性。

同时，脚本加入了请求延迟、页面加载重试、关键元素等待、超时处理和疑似重定向日志记录。当物种详情页无法提取到内容时，可将页面 HTML 保存到 `debug_pages/` 目录，方便后续排查。

### 3. 描述字段抽取、清洗与标准化输出

物种详情页中的描述内容可能来自异步接口或前端渲染后的 DOM。脚本优先通过浏览器上下文调用描述接口获取结构化数据；若字段不完整，再尝试点击描述标签页并从 DOM 中提取内容。

提取后，脚本使用 BeautifulSoup 去除 HTML 标签，使用正则表达式清理字段标题、冗余前缀和特殊符号，并按固定格式写入 TXT 文件。脚本还会检查已有非空输出文件，避免重复写入。

## 断点续爬

脚本会将已成功处理的物种 URL 追加写入 `crawled_species_urls.txt`。再次运行时，脚本会读取该文件并跳过已完成物种，从而支持中断后继续爬取。

如果需要重新爬取全部数据，可以删除：

```text
crawled_species_urls.txt
species_data/
```

## 注意事项

- 请遵守目标网站的 robots 协议、访问频率限制和数据使用规范。
- 大规模爬取时建议适当增大 `REQUEST_DELAY_SECONDS`，分批设置 `TARGET_TAXA`。
- 若页面频繁超时或被重定向，可关闭无头模式观察页面状态，或延长等待时间。
- 若 EdgeDriver 无法启动，请检查 Edge 浏览器版本、驱动版本和 `EDGEDRIVER_PATH` 配置。
- 上传 GitHub 时建议不要提交大规模爬取结果、调试 HTML 或本机路径相关文件。

## 适用场景

- 动物物种描述语料采集
- 生物学文本数据整理
- 知识抽取前置语料构建
- 物种知识图谱原始数据准备
- 分类树结构化遍历与网页爬取实验

