"""
依赖安装：
    pip install -U selenium webdriver-manager beautifulsoup4
"""

import logging
import math
import os
import re
import time
from typing import Optional
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# ======================= 配置区（集中可调参数） =======================
BASE_URL = "http://www.especies.cn/baike/taxon/sp2000TaxaTree_2023/"

# 先用鲟形目测试，确认没问题后再改成整个脊索动物门或节肢动物门
TARGET_TAXA = [
    #"Aves",  # 脊索动物门（正式跑全量时启用）
    #"Chondrichthyes",  # 软骨鱼纲
    #"Leptochordata",  # 狭心纲
    "Mammalia",  # 哺乳纲
    #"Myxini",  # 盲鳗纲
    #"Petromyzontia",  # 七鳃鳗纲
    "Reptilia"  # 爬行纲
]

OUTPUT_DIR = "species_data"
CRAWLED_RECORD_FILE = "crawled_species_urls.txt"

REQUEST_DELAY_SECONDS = 1  # 至少 2 秒
PAGE_WAIT_SECONDS = 18
MAX_RETRIES = 3
HEADLESS = True
EDGEDRIVER_PATH = "C:/Users/Lenovo/Desktop/animal_info/msedgedriver.exe"  # 如离线无法下载驱动，请手动填写本地 msedgedriver.exe 路径
EDGEDRIVER_VERSION = ""  # 可选：指定驱动版本，避免每次联网获取最新版本
EDGE_BINARY_PATH = ""  # 可选：Edge 安装在非默认路径时填写
DETAIL_EXTRA_WAIT_SECONDS = 6  # 详情页额外等待，避免 JS 渲染未完成
DEBUG_SAVE_HTML = True  # 详情页抓不到内容时，保存 HTML 便于排查
DEBUG_DIR = "debug_pages"
DESCRIPTION_PAGE_SIZE = 5
DESCRIPTION_MAX_PAGES = 3
DESCRIPTION_REQUEST_TIMEOUT_SECONDS = 8
DESCRIPTION_SCRIPT_TIMEOUT_SECONDS = 10
DESCRIPTION_DOM_WAIT_SECONDS = 6
SKIP_DOM_FALLBACK_WHEN_EMPTY = True  # 描述接口返回空时跳过 DOM fallback
PAGINATION_WAIT_SECONDS = 2
LOG_PAGINATION_SUMMARY = True  # 打印分页总数与实际条目数
SKIP_EXISTING_OUTPUT = True  # 发现已有非空输出文件时跳过

# ======================= 日志配置 =======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("especies_crawler")


# ----------------------- 工具函数 -----------------------
def clear_proxy_env() -> None:
    """强制清理系统代理环境变量，避免被重定向到首页。"""
    for key in [
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    ]:
        os.environ.pop(key, None)


def sanitize_filename(name: str) -> str:
    """去除 Windows 非法文件名字符。"""
    if not name:
        return ""
    name = re.sub(r"[\\/:*?\"<>|]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def build_taxon_url(latin_name: str) -> str:
    """按照规则拼接分类或物种 URL，空格必须编码为 %20。"""
    safe_name = quote(latin_name.strip(), safe="")
    return f"{BASE_URL}{safe_name}"


def normalize_taxon_url(url: str, latin_name: str) -> str:
    """统一 URL：强制 http 并处理空格编码。"""
    if not url:
        return build_taxon_url(latin_name)
    if url.startswith("https://"):
        url = "http://" + url[len("https://") :]
    if " " in url:
        url = url.replace(" ", "%20")
    return url


def load_done_urls(file_path: str) -> set:
    """加载已爬取的物种 URL，用于断点续爬。"""
    if not os.path.exists(file_path):
        return set()
    with open(file_path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_done_url(file_path: str, url: str) -> None:
    """追加记录已完成的物种 URL。"""
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def save_debug_html(tag: str, url: str, title: str, html: str) -> None:
    """保存调试 HTML，便于定位页面是否被重定向或未渲染。"""
    if not DEBUG_SAVE_HTML:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    safe_tag = sanitize_filename(tag) or "unknown"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_name = f"{safe_tag}_{timestamp}.html"
    file_path = os.path.join(DEBUG_DIR, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"<!-- URL: {url} -->\n")
        f.write(f"<!-- TITLE: {title} -->\n")
        f.write(html or "")
    logger.info("已保存调试页面：%s", file_path)


def setup_driver() -> webdriver.Edge:
    """启动 Selenium Edge，并尽可能模拟真实浏览器访问。"""
    clear_proxy_env()

    edge_options = webdriver.EdgeOptions()
    if HEADLESS:
        edge_options.add_argument("--headless=new")
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument("--window-size=1920,1080")
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_argument("--disable-features=msSmartScreenProtection,msSmartScreenFilter")
    edge_options.add_argument("--proxy-server=direct://")
    edge_options.add_argument("--proxy-bypass-list=*")

    if EDGE_BINARY_PATH:
        edge_options.binary_location = EDGE_BINARY_PATH

    # 模拟常见 Edge 请求头
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
    )
    edge_options.add_argument(f"--user-agent={user_agent}")
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option("useAutomationExtension", False)

    driver_service = None
    if EDGEDRIVER_PATH:
        driver_service = EdgeService(EDGEDRIVER_PATH)
    else:
        try:
            if EDGEDRIVER_VERSION:
                try:
                    driver_path = EdgeChromiumDriverManager(version=EDGEDRIVER_VERSION).install()
                except TypeError:
                    driver_path = EdgeChromiumDriverManager(driver_version=EDGEDRIVER_VERSION).install()
            else:
                driver_path = EdgeChromiumDriverManager().install()
            driver_service = EdgeService(driver_path)
        except Exception as exc:
            logger.warning("webdriver_manager 获取驱动失败，将尝试 Selenium Manager：%s", exc)

    try:
        if driver_service:
            driver = webdriver.Edge(service=driver_service, options=edge_options)
        else:
            # Selenium 4.6+ 自带 Selenium Manager，可在部分网络下自动管理驱动
            driver = webdriver.Edge(options=edge_options)
    except Exception:
        logger.exception("EdgeDriver 启动失败，请检查驱动或网络连接。")
        raise

    # 通过 CDP 设置额外请求头，贴近真实浏览器访问
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd(
        "Network.setExtraHTTPHeaders",
        {
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Upgrade-Insecure-Requests": "1",
            }
        },
    )
    driver.set_script_timeout(DESCRIPTION_SCRIPT_TIMEOUT_SECONDS)
    return driver


def load_page(driver: webdriver.Edge, url: str, wait_xpath: str) -> Optional[str]:
    """加载页面并返回 HTML，包含重试与等待逻辑。"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY_SECONDS)
            driver.get(url)

            if driver.current_url and "sp2000TaxaTree_2023" not in driver.current_url:
                logger.warning("疑似被重定向：%s -> %s", url, driver.current_url)

            if wait_xpath:
                try:
                    WebDriverWait(driver, PAGE_WAIT_SECONDS).until(
                        EC.presence_of_element_located((By.XPATH, wait_xpath))
                    )
                except TimeoutException:
                    logger.warning("等待页面关键元素超时，仍尝试解析：%s", url)

            return driver.page_source
        except WebDriverException as exc:
            logger.warning("页面加载失败（%s/%s）：%s", attempt, MAX_RETRIES, url)
            if attempt == MAX_RETRIES:
                logger.error("放弃该页面：%s", url)
                return None
            time.sleep(REQUEST_DELAY_SECONDS)
    return None


def find_taxon_table(soup: BeautifulSoup):
    """找到包含中文表头的分类表格。"""
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if {"分类等级", "拉丁名", "中文名"}.issubset(set(headers)):
            return table

    marker = soup.find(string=lambda t: t and "下级分类" in t)
    if marker:
        parent = marker.find_parent()
        if parent:
            candidate = parent.find_next("table")
            if candidate:
                return candidate

    rank_keywords = ["门", "纲", "目", "科", "属", "种", "物种", "亚种"]
    best_table = None
    best_score = 0
    for table in soup.find_all("table"):
        score = 0
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            rank_text = cols[0].get_text(strip=True)
            if any(keyword in rank_text for keyword in rank_keywords):
                score += 1
        if score > best_score:
            best_score = score
            best_table = table

    return best_table


def parse_children(html: str) -> list:
    """解析分类页面的子级列表。"""
    soup = BeautifulSoup(html, "html.parser")
    table = find_taxon_table(soup)
    if not table:
        return []

    children = []
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        rank = cols[0].get_text(strip=True)
        latin_cell = cols[1]
        latin_name = latin_cell.get_text(" ", strip=True)
        cn_name = cols[2].get_text(" ", strip=True)

        if not latin_name:
            continue

        link_tag = latin_cell.find("a")
        href = link_tag.get("href") if link_tag else None
        if href:
            if href.startswith("http://"):
                taxon_url = href
            elif href.startswith("/"):
                taxon_url = urljoin("http://www.especies.cn", href)
            elif "sp2000TaxaTree_2023/" in href:
                taxon_url = urljoin("http://www.especies.cn/baike/taxon/", href)
            else:
                taxon_url = urljoin(BASE_URL, href)
        else:
            taxon_url = build_taxon_url(latin_name)

        taxon_url = normalize_taxon_url(taxon_url, latin_name)

        children.append(
            {
                "rank": rank,
                "latin": latin_name,
                "cn": cn_name,
                "url": taxon_url,
            }
        )
    return children


def parse_children_with_retry(driver: webdriver.Edge, retries: int = 2) -> list:
    """等待表格渲染后再解析子级列表。"""
    for _ in range(retries + 1):
        html = driver.page_source
        children = parse_children(html)
        if children:
            return children
        time.sleep(1.0)
    return []


def get_table_page_count(driver: webdriver.Edge) -> int:
    """获取分类表格的页数（支持 DataTables）。"""
    script = """
        function findTable() {
            const tables = Array.from(document.querySelectorAll('table'));
            for (const table of tables) {
                const headers = Array.from(table.querySelectorAll('th')).map(
                    th => th.textContent.trim()
                );
                if (headers.includes('分类等级') && headers.includes('拉丁名') && headers.includes('中文名')) {
                    return table;
                }
            }
            const rankKeywords = ['门','纲','目','科','属','种','物种','亚种'];
            let best = null;
            let bestScore = 0;
            for (const table of tables) {
                let score = 0;
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const cols = row.querySelectorAll('td');
                    if (cols.length >= 3) {
                        const text = cols[0].textContent.trim();
                        if (rankKeywords.some(k => text.includes(k))) score += 1;
                    }
                });
                if (score > bestScore) {
                    bestScore = score;
                    best = table;
                }
            }
            return best;
        }
        const table = findTable();
        if (!table) return 1;
        if (window.jQuery && jQuery.fn && jQuery.fn.dataTable) {
            if (jQuery.fn.dataTable.isDataTable(table)) {
                const info = jQuery(table).DataTable().page.info();
                return info && info.pages ? info.pages : 1;
            }
        }
        if (table.id) {
            const paginate = document.getElementById(table.id + '_paginate');
            if (paginate) {
                const nums = Array.from(paginate.querySelectorAll('a'))
                    .map(a => a.textContent.trim())
                    .filter(t => /^\d+$/.test(t))
                    .map(t => parseInt(t, 10));
                if (nums.length) return Math.max.apply(null, nums);
            }
        }
        const wrapper = table.closest('.dataTables_wrapper');
        if (wrapper) {
            const paginate = wrapper.querySelector('.dataTables_paginate');
            if (paginate) {
                const nums = Array.from(paginate.querySelectorAll('a'))
                    .map(a => a.textContent.trim())
                    .filter(t => /^\d+$/.test(t))
                    .map(t => parseInt(t, 10));
                if (nums.length) return Math.max.apply(null, nums);
            }
        }
        const globalNums = Array.from(document.querySelectorAll('a.page-link, .pagination a'))
            .map(a => {
                const text = a.textContent.trim();
                if (/^\d+$/.test(text)) return parseInt(text, 10);
                const label = a.getAttribute('aria-label') || '';
                const match = label.match(/第\s*(\d+)\s*页/);
                return match ? parseInt(match[1], 10) : null;
            })
            .filter(n => Number.isInteger(n));
        if (globalNums.length) return Math.max.apply(null, globalNums);
        const infoNode = document.querySelector('.pagination-info');
        if (infoNode) {
            const text = infoNode.textContent || '';
            const match = text.match(/显示第\s*(\d+)\s*到第\s*(\d+)\s*条记录[，,]?\s*总共\s*(\d+)\s*条记录/);
            if (match) {
                const start = parseInt(match[1], 10);
                const end = parseInt(match[2], 10);
                const total = parseInt(match[3], 10);
                if (start === 1 && end >= start) {
                    const perPage = end - start + 1;
                    if (perPage > 0) return Math.max(1, Math.ceil(total / perPage));
                }
            }
        }
        return 1;
    """
    try:
        pages = driver.execute_script(script)
        if isinstance(pages, int) and pages > 0:
            return pages
    except WebDriverException:
        logger.exception("获取分页信息失败。")
    try:
        html = driver.page_source
        total_match = re.search(r"总共\s*(\d+)\s*条记录", html)
        per_match = re.search(r"每页显示\s*(\d+)\s*条记录", html)
        range_match = re.search(r"显示第\s*(\d+)\s*到第\s*(\d+)\s*条记录", html)
        if total_match and per_match:
            total = int(total_match.group(1))
            per_page = int(per_match.group(1))
            if per_page > 0:
                return max(1, math.ceil(total / per_page))
        if total_match and range_match:
            total = int(total_match.group(1))
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start == 1 and end >= start:
                per_page = end - start + 1
                if per_page > 0:
                    return max(1, math.ceil(total / per_page))
    except Exception:
        logger.exception("解析分页信息失败。")
    return 1


def get_current_table_page_index(driver: webdriver.Edge) -> int:
    """获取当前分类表格页码（0-based）。"""
    script = """
        function findTable() {
            const tables = Array.from(document.querySelectorAll('table'));
            for (const table of tables) {
                const headers = Array.from(table.querySelectorAll('th')).map(
                    th => th.textContent.trim()
                );
                if (headers.includes('分类等级') && headers.includes('拉丁名') && headers.includes('中文名')) {
                    return table;
                }
            }
            const rankKeywords = ['门','纲','目','科','属','种','物种','亚种'];
            let best = null;
            let bestScore = 0;
            for (const table of tables) {
                let score = 0;
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const cols = row.querySelectorAll('td');
                    if (cols.length >= 3) {
                        const text = cols[0].textContent.trim();
                        if (rankKeywords.some(k => text.includes(k))) score += 1;
                    }
                });
                if (score > bestScore) {
                    bestScore = score;
                    best = table;
                }
            }
            return best;
        }
        const table = findTable();
        if (!table) return 0;
        if (window.jQuery && jQuery.fn && jQuery.fn.dataTable) {
            if (jQuery.fn.dataTable.isDataTable(table)) {
                const info = jQuery(table).DataTable().page.info();
                return info && typeof info.page === 'number' ? info.page : 0;
            }
        }
        if (table.id) {
            const paginate = document.getElementById(table.id + '_paginate');
            if (paginate) {
                const active = paginate.querySelector('a.current') || paginate.querySelector('li.active a');
                if (active) {
                    const text = active.textContent.trim();
                    if (/^\d+$/.test(text)) return parseInt(text, 10) - 1;
                }
            }
        }
        const wrapper = table.closest('.dataTables_wrapper');
        if (wrapper) {
            const paginate = wrapper.querySelector('.dataTables_paginate');
            if (paginate) {
                const active = paginate.querySelector('a.current') || paginate.querySelector('li.active a');
                if (active) {
                    const text = active.textContent.trim();
                    if (/^\d+$/.test(text)) return parseInt(text, 10) - 1;
                }
            }
        }
        const globalActive = document.querySelector(
            'a.page-link[aria-current="page"], a.page-link.active, li.active a.page-link, .pagination li.active a, .pagination a[aria-current="page"]'
        );
        if (globalActive) {
            const text = globalActive.textContent.trim();
            if (/^\d+$/.test(text)) return parseInt(text, 10) - 1;
            const label = globalActive.getAttribute('aria-label') || '';
            const match = label.match(/第\s*(\d+)\s*页/);
            if (match) return parseInt(match[1], 10) - 1;
        }
        return 0;
    """
    try:
        page_index = driver.execute_script(script)
        if isinstance(page_index, int) and page_index >= 0:
            return page_index
    except WebDriverException:
        logger.exception("获取当前页码失败。")
    return 0


def set_table_page(driver: webdriver.Edge, page_index: int) -> bool:
    """切换分类表格页码（0-based）。"""
    script = """
        function findTable() {
            const tables = Array.from(document.querySelectorAll('table'));
            for (const table of tables) {
                const headers = Array.from(table.querySelectorAll('th')).map(
                    th => th.textContent.trim()
                );
                if (headers.includes('分类等级') && headers.includes('拉丁名') && headers.includes('中文名')) {
                    return table;
                }
            }
            const rankKeywords = ['门','纲','目','科','属','种','物种','亚种'];
            let best = null;
            let bestScore = 0;
            for (const table of tables) {
                let score = 0;
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const cols = row.querySelectorAll('td');
                    if (cols.length >= 3) {
                        const text = cols[0].textContent.trim();
                        if (rankKeywords.some(k => text.includes(k))) score += 1;
                    }
                });
                if (score > bestScore) {
                    bestScore = score;
                    best = table;
                }
            }
            return best;
        }
        const table = findTable();
        if (!table) return false;
        const pageIndex = arguments[0];
        if (window.jQuery && jQuery.fn && jQuery.fn.dataTable) {
            if (jQuery.fn.dataTable.isDataTable(table)) {
                jQuery(table).DataTable().page(pageIndex).draw('page');
                return true;
            }
        }
        if (table.id) {
            const paginate = document.getElementById(table.id + '_paginate');
            if (paginate) {
                const targetText = String(pageIndex + 1);
                const link = Array.from(paginate.querySelectorAll('a'))
                    .find(a => a.textContent.trim() === targetText);
                if (link) {
                    link.click();
                    return true;
                }
            }
        }
        const wrapper = table.closest('.dataTables_wrapper');
        if (wrapper) {
            const paginate = wrapper.querySelector('.dataTables_paginate');
            if (paginate) {
                const targetText = String(pageIndex + 1);
                const link = Array.from(paginate.querySelectorAll('a'))
                    .find(a => a.textContent.trim() === targetText);
                if (link) {
                    link.click();
                    return true;
                }
            }
        }
        const targetText = String(pageIndex + 1);
        const link = Array.from(document.querySelectorAll('a.page-link, .pagination a'))
            .find(a => {
                const text = a.textContent.trim();
                if (text === targetText) return true;
                const label = a.getAttribute('aria-label') || '';
                return new RegExp('第\\s*' + targetText + '\\s*页').test(label);
            });
        if (link) {
            link.click();
            return true;
        }
        return false;
    """
    try:
        return bool(driver.execute_script(script, page_index))
    except WebDriverException:
        logger.exception("切换分页失败。")
        return False


def collect_children_with_pagination(
    driver: webdriver.Edge,
    taxon_url: str,
    table_xpath: str,
) -> list:
    """收集当前分类下所有分页的子级列表。"""
    html = load_page(driver, taxon_url, table_xpath)
    if not html:
        return []

    all_children = parse_children_with_retry(driver)
    pages = get_table_page_count(driver)
    if pages > 1:
        for page_index in range(1, pages):
            if not set_table_page(driver, page_index):
                break
            try:
                WebDriverWait(driver, PAGINATION_WAIT_SECONDS).until(
                    lambda d: get_current_table_page_index(d) == page_index
                )
            except TimeoutException:
                time.sleep(PAGINATION_WAIT_SECONDS)
            all_children.extend(parse_children_with_retry(driver))

    unique_children = {}
    for child in all_children:
        unique_children[child["url"]] = child
    if LOG_PAGINATION_SUMMARY:
        logger.info(
            "分页总数: %s 实际条目: %s URL: %s",
            pages,
            len(unique_children),
            taxon_url,
        )
    return list(unique_children.values())


def clean_section_text(text: str, titles: list) -> str:
    """清理段落前缀标题，保留段落内容。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    for title in titles:
        pattern = rf"^{re.escape(title)}[\s：:]*"
        if re.match(pattern, text):
            text = re.sub(pattern, "", text, count=1).lstrip()
            break
    return text.strip() if text.strip() else "无"


def strip_html_text(value: str) -> str:
    """去除 HTML 标签并保留换行。"""
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return soup.get_text("\n", strip=True)


def extract_from_description_area(soup: BeautifulSoup) -> dict:
    """从“描述”标签页渲染后的区块提取字段。"""
    result = {
        "形态描述": "无",
        "生物学": "无",
        "生态学": "无",
    }
    blocks = soup.select("#descriptionArea .species-info")
    if not blocks:
        return result

    for block in blocks:
        title_node = block.select_one(".species-info-title")
        body_node = block.select_one(".species-info-body span")
        if not title_node or not body_node:
            continue
        title_text = title_node.get_text(strip=True)
        body_text = body_node.get_text("\n", strip=True)
        body_text = body_text.strip() if body_text.strip() else "无"

        if result["形态描述"] == "无" and ("形态描述" in title_text or "形态" in title_text):
            result["形态描述"] = body_text
        if result["生物学"] == "无" and "生物学" in title_text:
            result["生物学"] = body_text
        if result["生态学"] == "无" and "生态学" in title_text:
            result["生态学"] = body_text

    return result


def extract_from_description_json(description_list: list) -> dict:
    """从描述接口返回的数据中提取字段。"""
    result = {
        "形态描述": "无",
        "生物学": "无",
        "生态学": "无",
    }
    if not description_list:
        return result

    for item in description_list:
        title_text = str(item.get("descriptiontypeName", "")).strip()
        content_html = str(item.get("descontent", "")).strip()
        content_text = strip_html_text(content_html)
        content_text = clean_section_text(
            content_text, ["形态描述", "形态", "生物学", "生态学"]
        )
        if not content_text or content_text == "无":
            continue

        if result["形态描述"] == "无" and ("形态描述" in title_text or "形态" in title_text):
            result["形态描述"] = content_text
        if result["生物学"] == "无" and "生物学" in title_text:
            result["生物学"] = content_text
        if result["生态学"] == "无" and ("生态学" in title_text or "生态" in title_text):
            result["生态学"] = content_text

    return result


def fetch_description_json(
    driver: webdriver.Edge, sciname: str, size: int, number: int
) -> Optional[dict]:
    """在浏览器内直接调用描述接口，避免等待前端渲染。"""
    script = """
        const callback = arguments[0];
        const sciname = arguments[1];
        const size = arguments[2];
        const number = arguments[3];
        const timeoutMs = arguments[4];
        let done = false;
        function finish(payload) {
            if (done) return;
            done = true;
            callback(payload);
        }
        const tokenEl = document.querySelector('meta[name="_csrf"]');
        const headerEl = document.querySelector('meta[name="_csrf_header"]');
        const token = tokenEl ? tokenEl.getAttribute('content') : '';
        const headerName = headerEl ? headerEl.getAttribute('content') : 'X-CSRF-TOKEN';
        const payload = {
            sciname: sciname,
            size: size,
            sortType: 'ASC',
            number: number,
            fields: ['orderNum']
        };
        const controller = new AbortController();
        const timer = setTimeout(() => {
            controller.abort();
            finish({ok: false, error: 'timeout'});
        }, timeoutMs);
        fetch('/v1/traitdb/description/page', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                [headerName]: token
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin',
            signal: controller.signal
        })
        .then(resp => resp.json())
        .then(data => {
            clearTimeout(timer);
            finish({ok: true, data: data});
        })
        .catch(err => {
            clearTimeout(timer);
            finish({ok: false, error: String(err)});
        });
    """
    try:
        return driver.execute_async_script(
            script,
            sciname,
            size,
            number,
            DESCRIPTION_REQUEST_TIMEOUT_SECONDS * 1000,
        )
    except TimeoutException:
        logger.warning("描述接口脚本执行超时：%s", sciname)
        return None
    except WebDriverException:
        logger.exception("描述接口请求失败：%s", sciname)
        return None


def fetch_description_list(driver: webdriver.Edge, sciname: str) -> tuple:
    """分页获取描述数据列表，返回 (列表, 是否成功请求)。"""
    all_items = []
    page_num = 0
    request_ok = False
    while page_num < DESCRIPTION_MAX_PAGES:
        result = fetch_description_json(driver, sciname, DESCRIPTION_PAGE_SIZE, page_num)
        if not result or not result.get("ok"):
            if result and result.get("error"):
                logger.warning("描述接口返回错误：%s", result.get("error"))
            break

        request_ok = True

        payload = result.get("data")
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            payload = payload.get("data")

        if not isinstance(payload, dict):
            break

        description_list = payload.get("descriptionList") or []
        if description_list:
            all_items.extend(description_list)

        total_pages = payload.get("totalPages")
        if isinstance(total_pages, int) and total_pages > 0:
            if page_num >= total_pages - 1:
                break
        else:
            if not description_list:
                break

        page_num += 1

    return all_items, request_ok


def load_description_tab(driver: webdriver.Edge) -> None:
    """触发“描述”标签页加载，等待内容渲染。"""
    try:
        driver.execute_script(
            "var tab=document.querySelector('#description-tab'); if(tab){tab.click();}"
        )
        WebDriverWait(driver, DESCRIPTION_DOM_WAIT_SECONDS).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#descriptionArea .species-info-body span")
            )
        )
    except TimeoutException:
        logger.warning("描述数据加载超时，继续尝试解析页面。")
    except WebDriverException:
        logger.exception("触发描述加载失败。")


def extract_field(soup: BeautifulSoup, titles: list) -> str:
    """按规则提取指定字段：优先标题后的 span，兼容标题位于同一 span 的情况。"""
    try:
        roots = soup.select("div.species-info-body")
        if not roots:
            roots = [soup]

        for root in roots:
            for title in titles:
                text_node = root.find(string=lambda t: t and title in t)
                if not text_node:
                    continue

                parent = text_node.parent
                if parent and parent.name == "b":
                    span = parent.find_parent("span")
                    if span:
                        return clean_section_text(span.get_text("\n", strip=True), titles)

                if parent and parent.name == "span":
                    value = clean_section_text(parent.get_text("\n", strip=True), titles)
                    if value != "无":
                        return value

                span = parent.find_next("span") if parent else None
                if span:
                    return clean_section_text(span.get_text("\n", strip=True), titles)
    except Exception:
        return "无"
    return "无"


def get_species_file_path(cn_name: str, latin_name: str) -> str:
    """根据物种名生成输出文件路径。"""
    safe_cn = sanitize_filename(cn_name)
    if not safe_cn:
        safe_cn = sanitize_filename(latin_name) or "未知物种"
    return os.path.join(OUTPUT_DIR, f"{safe_cn}.txt")


def is_nonempty_file(file_path: str) -> bool:
    """判断文件是否存在且非空。"""
    try:
        return os.path.exists(file_path) and os.path.getsize(file_path) > 0
    except OSError:
        return False


def save_species_file(cn_name: str, latin_name: str, fields: dict) -> str:
    """保存物种信息为独立 TXT 文件。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_path = get_species_file_path(cn_name, latin_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("【形态描述】\n")
        f.write(fields.get("形态描述", "无") + "\n\n")
        f.write("【生物学】\n")
        f.write(fields.get("生物学", "无") + "\n\n")
        f.write("【生态学】\n")
        f.write(fields.get("生态学", "无") + "\n")
    return file_path


def crawl_species(
    driver: webdriver.Edge,
    species_url: str,
    cn_name: str,
    latin_name: str,
) -> bool:
    """抓取单个物种详情页并保存。"""
    file_path = get_species_file_path(cn_name, latin_name)
    if SKIP_EXISTING_OUTPUT and is_nonempty_file(file_path):
        logger.info("已存在且非空，跳过：%s", file_path)
        return True

    detail_xpath = "//*[@id='taxonInfoTab']"
    html = load_page(driver, species_url, detail_xpath)
    if not html:
        return False

    description_list, request_ok = fetch_description_list(driver, latin_name)
    fields = extract_from_description_json(description_list)
    all_empty = all(value == "无" for value in fields.values())
    skip_dom_fallback = (
        SKIP_DOM_FALLBACK_WHEN_EMPTY
        and request_ok
        and not description_list
        and all_empty
    )

    if not skip_dom_fallback and any(value == "无" for value in fields.values()):
        load_description_tab(driver)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        dom_fields = extract_from_description_area(soup)
        for key, value in dom_fields.items():
            if fields[key] == "无" and value != "无":
                fields[key] = value

    if not skip_dom_fallback and any(value == "无" for value in fields.values()):
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        fallback_fields = {
            "形态描述": extract_field(soup, ["形态描述", "形态"]),
            "生物学": extract_field(soup, ["生物学"]),
            "生态学": extract_field(soup, ["生态学"]),
        }
        for key, value in fallback_fields.items():
            if fields[key] == "无" and value != "无":
                fields[key] = value

    if all(value == "无" for value in fields.values()):
        save_debug_html(cn_name or latin_name, driver.current_url or species_url, driver.title, html)

    saved_path = save_species_file(cn_name, latin_name, fields)
    logger.info("已保存：%s", saved_path)
    return True


def crawl_taxon(
    driver: webdriver.Edge,
    taxon_url: str,
    done_species_urls: set,
    visited_taxa_urls: set,
) -> None:
    """递归遍历分类树，直到物种级别。"""
    if taxon_url in visited_taxa_urls:
        return
    visited_taxa_urls.add(taxon_url)

    table_xpath = "//*[contains(text(),'分类等级') or contains(text(),'下级分类')]"
    children = collect_children_with_pagination(driver, taxon_url, table_xpath)
    if not children:
        logger.warning("未找到子分类表格：%s", taxon_url)
        return

    for child in children:
        try:
            rank = child["rank"]
            latin_name = child["latin"]
            cn_name = child["cn"]
            child_url = child["url"]

            is_species = rank == "物种" or "种" in rank
            if is_species:
                if child_url in done_species_urls:
                    logger.info("跳过已完成物种：%s", child_url)
                    continue

                logger.info("抓取物种：%s / %s", cn_name, latin_name)
                ok = crawl_species(driver, child_url, cn_name, latin_name)
                if ok:
                    done_species_urls.add(child_url)
                    append_done_url(CRAWLED_RECORD_FILE, child_url)
                else:
                    logger.warning("物种抓取失败：%s", child_url)
                continue

            # 继续向下递归
            logger.info("进入下级分类：%s / %s", cn_name, latin_name)
            crawl_taxon(driver, child_url, done_species_urls, visited_taxa_urls)
        except Exception:
            logger.exception("处理子节点失败：%s", child)


def main() -> None:
    if not TARGET_TAXA:
        logger.error("未设置目标门类/分类，TARGET_TAXA 为空。")
        return

    done_species_urls = load_done_urls(CRAWLED_RECORD_FILE)
    visited_taxa_urls = set()
    driver = setup_driver()

    try:
        for taxon in TARGET_TAXA:
            start_url = build_taxon_url(taxon)
            logger.info("开始遍历：%s", start_url)
            crawl_taxon(driver, start_url, done_species_urls, visited_taxa_urls)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

"""
运行说明：
1) 直接运行：python get_info.py
2) 测试阶段默认爬取鲟形目（Acipenseriformes），确认成功后：
   - 将 TARGET_TAXA 改为 ["Chordata"] 可爬脊索动物门全量
   - 将 TARGET_TAXA 改为 ["Arthropoda"] 可爬节肢动物门（建议分批）
3) 若触发反爬：增大 REQUEST_DELAY_SECONDS 或暂停后再重试
"""