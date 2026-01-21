import asyncio
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable

from playwright.async_api import BrowserContext, Page

import config
from base.base_crawler import AbstractApiClient
from tools import utils


class GubaClient(AbstractApiClient):
    """
    东方财富股吧爬虫客户端
    
    股吧搜索页面: https://so.eastmoney.com/guba?keyword=xxx
    股吧帖子页面: https://guba.eastmoney.com/news,xxx,yyy.html
    股票股吧页面: https://guba.eastmoney.com/list,600547.html
    """
    
    def __init__(self,
                 timeout=10,
                 headers: Optional[Dict] = None,
                 playwright_page: Optional[Page] = None):
        self.timeout = timeout
        self.headers = headers
        self.playwright_page = playwright_page
        self._cookies_initialized = False
        
        # 时间过滤：获取配置的天数
        self.max_days = getattr(config, 'CRAWLER_MAX_DAYS', 0)
        if self.max_days > 0:
            self.cutoff_date = datetime.now() - timedelta(days=self.max_days)
            utils.logger.info(f"[GubaClient] 时间过滤已启用：只爬取 {self.max_days} 天内的帖子（{self.cutoff_date.strftime('%Y-%m-%d')} 之后）")
        else:
            self.cutoff_date = None
            utils.logger.info("[GubaClient] 时间过滤未启用")
    
    def _parse_time_string(self, time_str: str) -> Optional[datetime]:
        """
        解析股吧的时间字符串
        
        常见格式：
        - "10:30" (今天)
        - "01-15" (今年)
        - "01-15 10:30" (今年)
        - "2024-01-15" (完整日期)
        - "5分钟前"
        - "2小时前"
        - "今天 10:30"
        - "昨天 10:30"
        """
        if not time_str or time_str == "Unknown":
            return None
        
        time_str = time_str.strip()
        now = datetime.now()
        
        try:
            # "X分钟前"
            match = re.search(r'(\d+)\s*分钟前', time_str)
            if match:
                minutes = int(match.group(1))
                return now - timedelta(minutes=minutes)
            
            # "X小时前"
            match = re.search(r'(\d+)\s*小时前', time_str)
            if match:
                hours = int(match.group(1))
                return now - timedelta(hours=hours)
            
            # "X天前"
            match = re.search(r'(\d+)\s*天前', time_str)
            if match:
                days = int(match.group(1))
                return now - timedelta(days=days)
            
            # "今天 HH:MM" 或 "今天HH:MM"
            if '今天' in time_str:
                match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                if match:
                    hour, minute = int(match.group(1)), int(match.group(2))
                    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return now
            
            # "昨天 HH:MM"
            if '昨天' in time_str:
                yesterday = now - timedelta(days=1)
                match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                if match:
                    hour, minute = int(match.group(1)), int(match.group(2))
                    return yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
                return yesterday
            
            # "HH:MM" (今天)
            match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
            if match:
                hour, minute = int(match.group(1)), int(match.group(2))
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # "MM-DD" 或 "MM-DD HH:MM" (今年)
            match = re.match(r'^(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$', time_str)
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                hour = int(match.group(3)) if match.group(3) else 0
                minute = int(match.group(4)) if match.group(4) else 0
                return datetime(now.year, month, day, hour, minute)
            
            # "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM"
            match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?', time_str)
            if match:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                hour = int(match.group(4)) if match.group(4) else 0
                minute = int(match.group(5)) if match.group(5) else 0
                return datetime(year, month, day, hour, minute)
            
        except Exception as e:
            utils.logger.debug(f"[GubaClient._parse_time_string] Failed to parse '{time_str}': {e}")
        
        return None
    
    def _is_within_time_range(self, time_str: str) -> bool:
        """
        检查帖子时间是否在允许的范围内
        """
        if not self.cutoff_date:
            return True  # 未启用时间过滤
        
        post_time = self._parse_time_string(time_str)
        if not post_time:
            # 无法解析时间，默认保留
            return True
        
        return post_time >= self.cutoff_date

    async def request(self, method, url, **kwargs):
        pass

    async def update_cookies(self, browser_context: BrowserContext):
        pass
    
    async def _ensure_cookies(self):
        """
        确保已经获取了股吧的cookies，并检查是否需要登录
        """
        if self._cookies_initialized:
            return
            
        utils.logger.info("[GubaClient] Initializing - visiting homepage...")
        
        # 访问股吧首页
        await self.playwright_page.goto("https://guba.eastmoney.com/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        # 检查是否需要登录（东方财富的登录按钮）
        login_selectors = [
            'a[href*="passport.eastmoney.com"]',
            '.login-btn',
            'text=登录',
            '[class*="login"]'
        ]
        
        for selector in login_selectors:
            try:
                login_btn = await self.playwright_page.query_selector(selector)
                if login_btn:
                    is_visible = await login_btn.is_visible()
                    if is_visible:
                        login_text = await login_btn.inner_text()
                        if "登录" in login_text or "登陆" in login_text:
                            utils.logger.warning("[GubaClient] 检测到登录按钮，股吧可能需要登录")
                            utils.logger.info("[GubaClient] 如需登录，请在浏览器窗口中手动登录...")
                            
                            # 等待一段时间让用户登录（可选）
                            await asyncio.sleep(5)
                            break
            except:
                pass
        
        self._cookies_initialized = True
        utils.logger.info("[GubaClient] Cookies initialized")
    
    async def _handle_captcha(self):
        """
        检测并处理验证码
        如果出现验证码，等待用户手动完成
        """
        captcha_selectors = [
            '#captcha',
            '.captcha',
            '[class*="captcha"]',
            '[class*="verify"]',
            'text=验证',
            'text=请完成验证',
            'text=滑动',
            '#nc_1_wrapper',
            '.nc-container'
        ]
        
        for selector in captcha_selectors:
            try:
                captcha = await self.playwright_page.query_selector(selector)
                if captcha:
                    is_visible = await captcha.is_visible()
                    if is_visible:
                        utils.logger.warning("[GubaClient] 检测到验证码！")
                        utils.logger.info("[GubaClient] 请在浏览器窗口中手动完成验证...")
                        
                        # 等待验证码消失（最多等待2分钟）
                        for i in range(120):
                            await asyncio.sleep(1)
                            
                            # 检查验证码是否还存在
                            still_exists = False
                            for sel in captcha_selectors:
                                try:
                                    el = await self.playwright_page.query_selector(sel)
                                    if el and await el.is_visible():
                                        still_exists = True
                                        break
                                except:
                                    pass
                            
                            if not still_exists:
                                utils.logger.info("[GubaClient] 验证完成！")
                                await asyncio.sleep(2)
                                return
                            
                            if i % 15 == 0 and i > 0:
                                utils.logger.info(f"[GubaClient] 等待验证中... ({i}秒)")
                        
                        utils.logger.warning("[GubaClient] 验证超时")
                        return
            except:
                pass

    async def _crawl_stock_guba(self, stock_code: str, page: int) -> tuple[List[Dict], bool]:
        """
        爬取特定股票的股吧帖子列表
        
        股票股吧URL格式: https://guba.eastmoney.com/list,600547.html
        分页: https://guba.eastmoney.com/list,600547_2.html (第2页)
        
        返回: (帖子列表, 是否继续爬取下一页)
        """
        utils.logger.info(f"[GubaClient._crawl_stock_guba] Crawling stock {stock_code}, page {page}")
        
        # 确保cookies已初始化
        await self._ensure_cookies()
        
        # 构建股票股吧URL
        if page == 1:
            guba_url = f"https://guba.eastmoney.com/list,{stock_code}.html"
        else:
            guba_url = f"https://guba.eastmoney.com/list,{stock_code}_{page}.html"
        
        posts = []
        should_continue = True  # 是否继续爬取下一页
        old_posts_count = 0     # 超出时间范围的帖子数量
        
        try:
            utils.logger.info(f"[GubaClient._crawl_stock_guba] Visiting: {guba_url}")
            await self.playwright_page.goto(guba_url, wait_until="domcontentloaded")
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 检查是否有验证码
            await self._handle_captcha()
            
            # 保存调试信息
            import os
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            # 截图
            screenshot_path = os.path.join(debug_dir, f"guba_{stock_code}_debug.png")
            await self.playwright_page.screenshot(path=screenshot_path)
            utils.logger.info(f"[GubaClient._crawl_stock_guba] Screenshot saved to: {screenshot_path}")
            
            # 保存HTML用于调试
            html_path = os.path.join(debug_dir, f"guba_{stock_code}_debug.html")
            html_content = await self.playwright_page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            utils.logger.info(f"[GubaClient._crawl_stock_guba] HTML saved to: {html_path}")
            
            # 尝试解析帖子列表（股吧通常用表格展示）
            # 先尝试找到帖子行
            row_selectors = [
                ".listitem",           # 新版股吧
                ".articleh",           # 旧版股吧
                "tr[class*='list']",   # 表格行
                ".post_list li",       # 列表项
                "#articlelistnew .normal_post"  # 普通帖子
            ]
            
            rows = []
            for selector in row_selectors:
                rows = await self.playwright_page.query_selector_all(selector)
                if rows:
                    utils.logger.info(f"[GubaClient._crawl_stock_guba] Found {len(rows)} rows with selector: {selector}")
                    break
            
            total_rows = 0
            if rows:
                # 解析每一行
                for row in rows[:30]:
                    total_rows += 1
                    try:
                        post = await self._parse_guba_row(row, stock_code)
                        if post:
                            posts.append(post)
                        elif self.cutoff_date:
                            # 帖子被时间过滤掉了
                            old_posts_count += 1
                    except Exception as e:
                        utils.logger.debug(f"[GubaClient._crawl_stock_guba] Error parsing row: {e}")
                        continue
            else:
                # 备用方案：直接找链接
                utils.logger.info("[GubaClient._crawl_stock_guba] No rows found, trying link-based parsing...")
                all_links = await self.playwright_page.query_selector_all("a")
                utils.logger.info(f"[GubaClient._crawl_stock_guba] Total links on page: {len(all_links)}")
                
                seen_urls = set()
                
                for link in all_links:
                    try:
                        href = await link.get_attribute("href")
                        if not href:
                            continue
                        
                        # 股吧帖子链接格式: /news,600547,1234567890.html
                        if not re.search(r'news,\w+,\d+\.html', href):
                            continue
                        
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)
                        
                        # 补全URL
                        if href.startswith("//"):
                            href = "https:" + href
                        elif href.startswith("/"):
                            href = "https://guba.eastmoney.com" + href
                        elif not href.startswith("http"):
                            href = "https://guba.eastmoney.com/" + href
                        
                        # 获取标题
                        title = await link.inner_text()
                        title = title.strip() if title else ""
                        
                        if len(title) < 3:
                            continue
                        
                        # 跳过无关链接
                        skip_texts = ['回复', '评论', '阅读', '转发', '分享', '更多']
                        if any(skip in title for skip in skip_texts) and len(title) < 10:
                            continue
                        
                        posts.append({
                            "note_id": href,
                            "title": title[:100],
                            "content": title,
                            "user_nickname": "Unknown",
                            "create_time": "Unknown",
                            "note_url": href
                        })
                        
                        if len(posts) >= 30:
                            break
                            
                    except Exception as e:
                        utils.logger.debug(f"[GubaClient._crawl_stock_guba] Error parsing link: {e}")
                        continue
            
            # 判断是否应该继续爬取下一页
            # 如果这一页超过一半的帖子都超出时间范围，就停止
            if self.cutoff_date and total_rows > 0:
                if old_posts_count > total_rows * 0.5:
                    should_continue = False
                    utils.logger.info(f"[GubaClient._crawl_stock_guba] 超过一半帖子({old_posts_count}/{total_rows})超出时间范围，停止爬取")
                    
        except Exception as e:
            utils.logger.error(f"[GubaClient._crawl_stock_guba] Error: {e}")
            
        utils.logger.info(f"[GubaClient._crawl_stock_guba] Found {len(posts)} posts for stock {stock_code}, continue={should_continue}")
        return posts, should_continue
    
    async def _parse_guba_row(self, row, stock_code: str) -> Optional[Dict]:
        """
        解析股吧帖子列表的一行
        
        股吧列表通常包含：标题、作者、时间、阅读数、评论数
        """
        try:
            # 获取标题链接
            title_link = await row.query_selector("a[href*='news,']")
            if not title_link:
                title_link = await row.query_selector("a.title, .title a, a")
            
            if not title_link:
                return None
            
            href = await title_link.get_attribute("href")
            if not href or 'news,' not in href:
                return None
            
            # 补全URL
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://guba.eastmoney.com" + href
            elif not href.startswith("http"):
                href = "https://guba.eastmoney.com/" + href
            
            title = await title_link.inner_text()
            title = title.strip() if title else ""
            
            if len(title) < 3:
                return None
            
            # 尝试获取作者
            author = "Unknown"
            author_selectors = [".author", ".user", "a[href*='people']", ".name"]
            for sel in author_selectors:
                try:
                    author_el = await row.query_selector(sel)
                    if author_el:
                        author = await author_el.inner_text()
                        author = author.strip()
                        if author:
                            break
                except:
                    pass
            
            # 尝试获取时间
            create_time = "Unknown"
            time_selectors = [".time", ".date", ".pubtime", "span[class*='time']", "td:last-child"]
            for sel in time_selectors:
                try:
                    time_el = await row.query_selector(sel)
                    if time_el:
                        time_text = await time_el.inner_text()
                        time_text = time_text.strip()
                        # 检查是否像时间格式
                        if time_text and (re.search(r'\d{1,2}:\d{2}', time_text) or 
                                         re.search(r'\d{1,2}-\d{1,2}', time_text) or
                                         '分钟' in time_text or '小时' in time_text or
                                         '今天' in time_text or '昨天' in time_text):
                            create_time = time_text
                            break
                except:
                    pass
            
            utils.logger.info(f"[GubaClient._parse_guba_row] Found: {title[:30]}... | {author} | {create_time}")
            
            # 时间过滤
            if not self._is_within_time_range(create_time):
                utils.logger.debug(f"[GubaClient._parse_guba_row] Skipped (too old): {title[:30]}... | {create_time}")
                return None
            
            return {
                "note_id": href,
                "title": title[:100],
                "content": title,
                "user_nickname": author,
                "create_time": create_time,
                "note_url": href
            }
            
        except Exception as e:
            utils.logger.debug(f"[GubaClient._parse_guba_row] Error: {e}")
            return None

    async def search_posts(self, keyword: str, page: int) -> tuple[List[Dict], bool]:
        """
        在东方财富股吧搜索帖子
        
        如果keyword是6位数字股票代码，直接访问该股票的股吧页面
        股票股吧URL: https://guba.eastmoney.com/list,600547.html
        
        否则使用搜索功能
        搜索URL: https://so.eastmoney.com/guba?keyword=xxx&page=n
        
        返回: (帖子列表, 是否继续爬取下一页)
        """
        utils.logger.info(f"[GubaClient.search_posts] Searching keyword: {keyword}, page: {page}")
        
        # 检查是否是股票代码（6位数字）
        if re.match(r'^\d{6}$', keyword.strip()):
            return await self._crawl_stock_guba(keyword.strip(), page)
        
        # 确保cookies已初始化
        await self._ensure_cookies()
        
        # 东方财富搜索URL
        encoded_keyword = urllib.parse.quote(keyword)
        search_url = f"https://so.eastmoney.com/guba?keyword={encoded_keyword}&page={page}"
        
        posts = []
        
        try:
            await self.playwright_page.goto(search_url, wait_until="domcontentloaded")
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 检查是否有验证码
            await self._handle_captcha()
            
            # 保存调试信息
            import os
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            # 截图
            screenshot_path = os.path.join(debug_dir, "guba_debug.png")
            await self.playwright_page.screenshot(path=screenshot_path)
            utils.logger.info(f"[GubaClient.search_posts] Screenshot saved to: {screenshot_path}")
            
            # 保存HTML用于调试
            html_path = os.path.join(debug_dir, "guba_debug.html")
            html_content = await self.playwright_page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            utils.logger.info(f"[GubaClient.search_posts] HTML saved to: {html_path}")
            
            # 打印页面上的一些链接用于调试
            all_links = await self.playwright_page.query_selector_all("a")
            utils.logger.info(f"[GubaClient.search_posts] Total links on page: {len(all_links)}")
            
            # 打印前30个链接
            for i, link in enumerate(all_links[:30]):
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    text = text.strip()[:50] if text else "N/A"
                    utils.logger.info(f"[GubaClient.search_posts] Link {i}: href={href}, text={text}")
                except:
                    pass
            
            # 尝试等待搜索结果加载
            try:
                await self.playwright_page.wait_for_selector(".search-result-list, .news_list, .list_item, .search_list, .guba_list", timeout=10000)
            except:
                utils.logger.warning("[GubaClient.search_posts] Timeout waiting for search results")
            
            # 获取所有链接，分析股吧帖子链接格式
            all_a = await self.playwright_page.query_selector_all("a")
            seen_urls = set()
            
            for link in all_a:
                try:
                    href = await link.get_attribute("href")
                    if not href:
                        continue
                    
                    # 股吧帖子链接格式：
                    # 1. https://guba.eastmoney.com/news,股票代码,帖子ID.html
                    # 2. //guba.eastmoney.com/news,xxx,yyy.html
                    # 3. /news,xxx,yyy.html
                    
                    # 检查是否是股吧帖子链接
                    is_post_link = False
                    
                    # 格式1: news,xxx,yyy.html
                    if re.search(r'news,\w+,\d+\.html', href):
                        is_post_link = True
                    # 格式2: news/xxx/yyy.html 或类似
                    elif re.search(r'news/\w+/\d+', href):
                        is_post_link = True
                    # 格式3: 包含guba和数字ID
                    elif 'guba' in href and re.search(r'/\d{6,}', href):
                        is_post_link = True
                    
                    if not is_post_link:
                        continue
                    
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    
                    # 补全URL
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = "https://guba.eastmoney.com" + href
                    elif not href.startswith("http"):
                        href = "https://guba.eastmoney.com/" + href
                    
                    # 获取标题
                    title = await link.inner_text()
                    title = title.strip() if title else ""
                    
                    # 跳过空标题或太短的标题
                    if len(title) < 3:
                        # 尝试从父元素获取文本
                        try:
                            parent = await link.evaluate_handle("el => el.parentElement")
                            if parent:
                                title = await parent.evaluate("el => el.innerText")
                                title = title.strip()[:100] if title else ""
                        except:
                            pass
                    
                    if len(title) < 3:
                        continue
                    
                    posts.append({
                        "note_id": href,
                        "title": title[:100],
                        "content": title,
                        "user_nickname": "Unknown",
                        "create_time": "Unknown",
                        "note_url": href
                    })
                    
                    utils.logger.info(f"[GubaClient.search_posts] Found post: {title[:30]}... -> {href}")
                    
                    if len(posts) >= 20:
                        break
                        
                except Exception as e:
                    utils.logger.debug(f"[GubaClient.search_posts] Error parsing link: {e}")
                    continue
                    
        except Exception as e:
            utils.logger.error(f"[GubaClient.search_posts] Error: {e}")
            
        utils.logger.info(f"[GubaClient.search_posts] Found {len(posts)} posts")
        return posts, True  # 搜索模式默认继续爬取

    async def get_note_detail(self, note_url: str) -> Dict:
        """
        获取股吧帖子详情
        
        帖子URL格式: https://guba.eastmoney.com/news,xxx,yyy.html
        """
        utils.logger.info(f"[GubaClient.get_note_detail] Fetching {note_url}")
        
        try:
            await self.playwright_page.goto(note_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # 提取内容 - 尝试多种选择器
            content = ""
            content_selectors = [
                "#zwconbody",
                ".article-body",
                ".stockcodec",
                ".post_content",
                ".newstext",
                "[class*='content']"
            ]
            
            for selector in content_selectors:
                try:
                    content_el = await self.playwright_page.query_selector(selector)
                    if content_el:
                        content = await content_el.inner_text()
                        if content.strip():
                            break
                except:
                    continue
                
            # 提取标题
            title = ""
            title_selectors = [
                "#zwconttbt",
                ".article-title",
                ".post_title",
                "h1",
                ".title"
            ]
            
            for selector in title_selectors:
                try:
                    title_el = await self.playwright_page.query_selector(selector)
                    if title_el:
                        title = await title_el.inner_text()
                        if title.strip():
                            break
                except:
                    continue

            # 提取作者
            author = "Unknown"
            author_selectors = [
                "#zwconttbn .auth",
                ".author-name",
                ".user-name",
                "[class*='author']"
            ]
            
            for selector in author_selectors:
                try:
                    author_el = await self.playwright_page.query_selector(selector)
                    if author_el:
                        author = await author_el.inner_text()
                        if author.strip():
                            break
                except:
                    continue
                
            return {
                "note_id": note_url,
                "title": title.strip() if title else "",
                "content": content.strip() if content else "",
                "user_nickname": author.strip() if author else "Unknown",
                "note_url": note_url,
                "create_time": 0,
                "comments": []
            }
            
        except Exception as e:
            utils.logger.error(f"[GubaClient.get_note_detail] Error: {e}")
            return {}

    async def get_note_comments(self, note_url: str) -> List[Dict]:
        """
        获取股吧帖子评论
        """
        comments = []
        
        try:
            # 假设我们已经在帖子页面上
            comment_selectors = [
                ".zwlitxt",
                ".comment_item",
                ".reply_item",
                "[class*='comment']"
            ]
            
            for selector in comment_selectors:
                comment_els = await self.playwright_page.query_selector_all(selector)
                if comment_els:
                    for el in comment_els[:30]:
                        try:
                            text = await el.inner_text()
                            if text and text.strip():
                                comments.append({
                                    "content": text.strip()[:500],
                                    "create_time": 0,
                                    "user_nickname": "Unknown"
                                })
                        except:
                            continue
                    break
                    
        except Exception as e:
            utils.logger.error(f"[GubaClient.get_note_comments] Error: {e}")
            
        return comments
