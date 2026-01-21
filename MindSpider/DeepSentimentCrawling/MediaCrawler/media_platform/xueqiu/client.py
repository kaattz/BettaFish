import asyncio
import json
import urllib.parse
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from playwright.async_api import BrowserContext, Page

import config
from base.base_crawler import AbstractApiClient
from tools import utils


class XueqiuClient(AbstractApiClient):
    """
    雪球爬虫客户端
    
    雪球网站使用Vue.js动态加载内容，需要等待JavaScript执行完成。
    我们通过拦截网络请求来获取API返回的数据。
    
    股票讨论页面: https://xueqiu.com/S/SH600547 (上海) 或 https://xueqiu.com/S/SZ000001 (深圳)
    搜索页面: https://xueqiu.com/k?q=关键词#/timeline
    """
    
    def __init__(self,
                 timeout=10,
                 headers: Optional[Dict] = None,
                 playwright_page: Optional[Page] = None):
        self.timeout = timeout
        self.headers = headers
        self.playwright_page = playwright_page
        self._cookies_initialized = False
        self._api_data = None
        
        # 时间过滤：获取配置的天数
        self.max_days = getattr(config, 'CRAWLER_MAX_DAYS', 0)
        if self.max_days > 0:
            self.cutoff_date = datetime.now() - timedelta(days=self.max_days)
            utils.logger.info(f"[XueqiuClient] 时间过滤已启用：只爬取 {self.max_days} 天内的帖子（{self.cutoff_date.strftime('%Y-%m-%d')} 之后）")
        else:
            self.cutoff_date = None
            utils.logger.info("[XueqiuClient] 时间过滤未启用")

    async def request(self, method, url, **kwargs):
        pass

    async def update_cookies(self, browser_context: BrowserContext):
        pass
    
    def _parse_time(self, time_value) -> Optional[datetime]:
        """
        解析雪球的时间
        
        雪球API返回的时间是毫秒时间戳，如 1705123456000
        也可能是字符串格式
        """
        if not time_value or time_value == "Unknown":
            return None
        
        try:
            # 如果是数字（毫秒时间戳）
            if isinstance(time_value, (int, float)) and time_value > 0:
                # 雪球返回的是毫秒时间戳
                return datetime.fromtimestamp(time_value / 1000)
            
            # 如果是字符串
            if isinstance(time_value, str):
                time_str = time_value.strip()
                now = datetime.now()
                
                # "X分钟前"
                match = re.search(r'(\d+)\s*分钟前', time_str)
                if match:
                    return now - timedelta(minutes=int(match.group(1)))
                
                # "X小时前"
                match = re.search(r'(\d+)\s*小时前', time_str)
                if match:
                    return now - timedelta(hours=int(match.group(1)))
                
                # "X天前"
                match = re.search(r'(\d+)\s*天前', time_str)
                if match:
                    return now - timedelta(days=int(match.group(1)))
                
                # "今天 HH:MM"
                if '今天' in time_str:
                    match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                    if match:
                        return now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0)
                    return now
                
                # "昨天"
                if '昨天' in time_str:
                    return now - timedelta(days=1)
                
                # "MM-DD" 或 "MM-DD HH:MM"
                match = re.match(r'^(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$', time_str)
                if match:
                    month, day = int(match.group(1)), int(match.group(2))
                    hour = int(match.group(3)) if match.group(3) else 0
                    minute = int(match.group(4)) if match.group(4) else 0
                    return datetime(now.year, month, day, hour, minute)
                
        except Exception as e:
            utils.logger.debug(f"[XueqiuClient._parse_time] Failed to parse '{time_value}': {e}")
        
        return None
    
    def _is_within_time_range(self, time_value) -> bool:
        """检查帖子时间是否在允许的范围内"""
        if not self.cutoff_date:
            return True
        
        post_time = self._parse_time(time_value)
        if not post_time:
            return True  # 无法解析时间，默认保留
        
        return post_time >= self.cutoff_date
    
    def _stock_code_to_symbol(self, code: str) -> str:
        """
        将股票代码转换为雪球的股票符号
        
        6开头 -> SH (上海)
        0/3开头 -> SZ (深圳)
        """
        code = code.strip()
        if code.startswith('6'):
            return f"SH{code}"
        elif code.startswith('0') or code.startswith('3'):
            return f"SZ{code}"
        else:
            # 默认上海
            return f"SH{code}"
    
    async def _ensure_cookies(self):
        """
        确保已经获取了雪球的cookies，并检查是否已登录
        雪球讨论区内容需要登录才能查看
        """
        if self._cookies_initialized:
            return
            
        utils.logger.info("[XueqiuClient] Initializing - visiting homepage...")
        
        # 访问雪球首页
        await self.playwright_page.goto("https://xueqiu.com/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        # 检查是否已登录（查找登录按钮或用户头像）
        login_btn = await self.playwright_page.query_selector('.loginBtn, a[class*="login"]')
        if login_btn:
            login_text = await login_btn.inner_text()
            if "登录" in login_text:
                utils.logger.warning("[XueqiuClient] 未登录！雪球讨论区需要登录才能查看内容")
                utils.logger.info("[XueqiuClient] 请在浏览器窗口中扫码登录...")
                
                # 点击登录按钮弹出登录框
                try:
                    await login_btn.click()
                    await asyncio.sleep(1)
                except:
                    pass
                
                # 等待用户登录（最多等待5分钟）
                for i in range(300):
                    await asyncio.sleep(1)
                    
                    login_btn = await self.playwright_page.query_selector('.loginBtn, a[class*="login"]')
                    if not login_btn:
                        utils.logger.info("[XueqiuClient] 登录成功！")
                        break
                    
                    login_text = await login_btn.inner_text()
                    if "登录" not in login_text:
                        utils.logger.info("[XueqiuClient] 登录成功！")
                        break
                    
                    if i % 30 == 0 and i > 0:
                        utils.logger.info(f"[XueqiuClient] 等待登录中... ({i}秒)")
                else:
                    utils.logger.warning("[XueqiuClient] 登录超时，将尝试继续（可能无法获取讨论内容）")
        
        self._cookies_initialized = True
        utils.logger.info("[XueqiuClient] Cookies initialized")
    
    async def _handle_slider_captcha(self):
        """检测并处理滑块验证码"""
        captcha_selectors = [
            '#captcha-element',
            '.nc-container',
            '#nc_1_wrapper',
            '[class*="captcha"]',
            'text=访问验证',
            'text=请按住滑块',
            'text=拖动到最右边'
        ]
        
        for selector in captcha_selectors:
            try:
                captcha = await self.playwright_page.query_selector(selector)
                if captcha:
                    is_visible = await captcha.is_visible()
                    if is_visible:
                        utils.logger.warning("[XueqiuClient] 检测到滑块验证码！")
                        utils.logger.info("[XueqiuClient] 请在浏览器窗口中手动完成滑块验证...")
                        
                        for i in range(120):
                            await asyncio.sleep(1)
                            
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
                                utils.logger.info("[XueqiuClient] 滑块验证完成！")
                                await asyncio.sleep(2)
                                return
                            
                            if i % 15 == 0 and i > 0:
                                utils.logger.info(f"[XueqiuClient] 等待滑块验证中... ({i}秒)")
                        
                        utils.logger.warning("[XueqiuClient] 滑块验证超时")
                        return
            except:
                pass

    async def search_posts(self, keyword: str, page: int) -> Tuple[List[Dict], bool]:
        """
        搜索帖子
        
        如果keyword是6位数字股票代码，直接访问该股票的讨论页面
        否则使用搜索功能
        
        返回: (帖子列表, 是否继续爬取下一页)
        """
        utils.logger.info(f"[XueqiuClient.search_posts] Searching keyword: {keyword}, page: {page}")
        
        # 检查是否是股票代码（6位数字）
        if re.match(r'^\d{6}$', keyword.strip()):
            return await self._crawl_stock_discussion(keyword.strip(), page)
        
        # 普通搜索
        return await self._search_keyword(keyword, page)

    async def _crawl_stock_discussion(self, stock_code: str, page: int) -> Tuple[List[Dict], bool]:
        """
        爬取特定股票的讨论帖子
        
        雪球股票讨论页面: https://xueqiu.com/S/SH600547 (上海) 或 https://xueqiu.com/S/SZ000001 (深圳)
        """
        symbol = self._stock_code_to_symbol(stock_code)
        utils.logger.info(f"[XueqiuClient._crawl_stock_discussion] Crawling stock {stock_code} ({symbol}), page {page}")
        
        await self._ensure_cookies()
        
        posts = []
        should_continue = True
        old_posts_count = 0
        total_posts = 0
        
        try:
            # 雪球股票讨论页面
            stock_url = f"https://xueqiu.com/S/{symbol}"
            
            # 设置网络请求拦截，捕获API响应
            api_responses = []
            
            async def handle_response(response):
                url = response.url
                # 雪球股票讨论API
                if "statuses/stock_timeline.json" in url or f"/S/{symbol}" in url:
                    try:
                        if response.headers.get("content-type", "").startswith("application/json"):
                            json_data = await response.json()
                            api_responses.append(json_data)
                            utils.logger.info(f"[XueqiuClient] Captured API response: {url}")
                    except:
                        pass
            
            self.playwright_page.on("response", handle_response)
            
            utils.logger.info(f"[XueqiuClient._crawl_stock_discussion] Visiting: {stock_url}")
            await self.playwright_page.goto(stock_url, wait_until="domcontentloaded")
            
            await asyncio.sleep(3)
            await self._handle_slider_captcha()
            await asyncio.sleep(2)
            
            # 点击"讨论"标签
            try:
                discussion_tab = await self.playwright_page.query_selector('a[href*="discussion"], [class*="discussion"]')
                if discussion_tab:
                    await discussion_tab.click()
                    await asyncio.sleep(2)
                    await self._handle_slider_captcha()
            except:
                pass
            
            # 如果需要翻页，滚动页面加载更多
            if page > 1:
                for _ in range(page - 1):
                    await self.playwright_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
            
            self.playwright_page.remove_listener("response", handle_response)
            
            # 保存调试信息
            import os
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            screenshot_path = os.path.join(debug_dir, f"xueqiu_{stock_code}_debug.png")
            await self.playwright_page.screenshot(path=screenshot_path)
            utils.logger.info(f"[XueqiuClient] Screenshot saved: {screenshot_path}")
            
            # 从API响应解析数据
            for api_data in api_responses:
                if isinstance(api_data, dict) and "list" in api_data:
                    utils.logger.info(f"[XueqiuClient] Parsing API data with {len(api_data['list'])} items")
                    for item in api_data["list"]:
                        total_posts += 1
                        try:
                            post = self._parse_api_item(item)
                            if post:
                                # 时间过滤
                                if self._is_within_time_range(post.get("create_time")):
                                    posts.append(post)
                                    utils.logger.info(f"[XueqiuClient] Found: {post['title'][:30]}...")
                                else:
                                    old_posts_count += 1
                                    utils.logger.debug(f"[XueqiuClient] Skipped (too old): {post['title'][:30]}...")
                        except Exception as e:
                            utils.logger.debug(f"[XueqiuClient] Error parsing API item: {e}")
            
            # 如果API没有数据，尝试从页面DOM解析
            if not posts and not api_responses:
                utils.logger.info("[XueqiuClient] No API data, trying DOM parsing...")
                dom_posts = await self._parse_page_content()
                for post in dom_posts:
                    total_posts += 1
                    if self._is_within_time_range(post.get("create_time")):
                        posts.append(post)
                    else:
                        old_posts_count += 1
            
            # 判断是否继续爬取
            if self.cutoff_date and total_posts > 0:
                if old_posts_count > total_posts * 0.5:
                    should_continue = False
                    utils.logger.info(f"[XueqiuClient] 超过一半帖子({old_posts_count}/{total_posts})超出时间范围，停止爬取")
                    
        except Exception as e:
            utils.logger.error(f"[XueqiuClient._crawl_stock_discussion] Error: {e}")
        
        utils.logger.info(f"[XueqiuClient._crawl_stock_discussion] Found {len(posts)} posts, continue={should_continue}")
        return posts, should_continue
    
    async def _search_keyword(self, keyword: str, page: int) -> Tuple[List[Dict], bool]:
        """普通关键词搜索"""
        await self._ensure_cookies()
        
        posts = []
        should_continue = True
        old_posts_count = 0
        total_posts = 0
        
        try:
            api_responses = []
            
            async def handle_response(response):
                url = response.url
                if "search/status.json" in url or "statuses/search" in url:
                    try:
                        json_data = await response.json()
                        api_responses.append(json_data)
                        utils.logger.info(f"[XueqiuClient] Captured API response: {url}")
                    except:
                        pass
            
            self.playwright_page.on("response", handle_response)
            
            encoded_keyword = urllib.parse.quote(keyword)
            search_url = f"https://xueqiu.com/k?q={encoded_keyword}#/timeline"
            
            utils.logger.info(f"[XueqiuClient._search_keyword] Visiting: {search_url}")
            await self.playwright_page.goto(search_url, wait_until="domcontentloaded")
            
            await asyncio.sleep(3)
            await self._handle_slider_captcha()
            await asyncio.sleep(3)
            
            # 点击"讨论"标签
            try:
                timeline_tab = await self.playwright_page.query_selector('a[href="#/timeline"]')
                if timeline_tab:
                    await timeline_tab.click()
                    await asyncio.sleep(3)
                    await self._handle_slider_captcha()
            except:
                pass
            
            self.playwright_page.remove_listener("response", handle_response)
            
            # 保存调试信息
            import os
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            screenshot_path = os.path.join(debug_dir, "xueqiu_debug.png")
            await self.playwright_page.screenshot(path=screenshot_path)
            
            # 从API响应解析
            for api_data in api_responses:
                if isinstance(api_data, dict) and "list" in api_data:
                    utils.logger.info(f"[XueqiuClient] Parsing API data with {len(api_data['list'])} items")
                    for item in api_data["list"]:
                        total_posts += 1
                        try:
                            post = self._parse_api_item(item)
                            if post:
                                if self._is_within_time_range(post.get("create_time")):
                                    posts.append(post)
                                else:
                                    old_posts_count += 1
                        except:
                            continue
            
            # 如果API没有数据，尝试DOM解析
            if not posts:
                utils.logger.info("[XueqiuClient] No API data, trying DOM parsing...")
                dom_posts = await self._parse_page_content()
                for post in dom_posts:
                    total_posts += 1
                    if self._is_within_time_range(post.get("create_time")):
                        posts.append(post)
                    else:
                        old_posts_count += 1
            
            # 判断是否继续
            if self.cutoff_date and total_posts > 0:
                if old_posts_count > total_posts * 0.5:
                    should_continue = False
                    utils.logger.info(f"[XueqiuClient] 超过一半帖子超出时间范围，停止爬取")
                    
        except Exception as e:
            utils.logger.error(f"[XueqiuClient._search_keyword] Error: {e}")
        
        utils.logger.info(f"[XueqiuClient._search_keyword] Found {len(posts)} posts")
        return posts, should_continue
    
    def _parse_api_item(self, item: Dict) -> Optional[Dict]:
        """解析API返回的单个帖子数据"""
        try:
            user_id = item.get("user_id", "")
            status_id = item.get("id", "")
            note_url = f"https://xueqiu.com/{user_id}/{status_id}" if user_id and status_id else ""
            
            content = item.get("text", "") or item.get("description", "") or item.get("title", "")
            content = re.sub(r'<[^>]+>', '', content)
            
            title = content[:50].replace("\n", " ").strip()
            if len(content) > 50:
                title += "..."
            
            user = item.get("user", {})
            user_nickname = user.get("screen_name", "Unknown") if isinstance(user, dict) else "Unknown"
            
            create_time = item.get("created_at", 0)
            
            return {
                "note_id": str(status_id) if status_id else note_url,
                "title": title,
                "content": content[:500],
                "user_nickname": user_nickname,
                "create_time": create_time,
                "note_url": note_url
            }
        except:
            return None

    async def _parse_page_content(self) -> List[Dict]:
        """从页面DOM解析帖子列表"""
        posts = []
        
        try:
            selectors = [
                ".timeline__item",
                ".status-item", 
                ".AnonymousHome__timeline__item",
                "[class*='timeline'] article",
                "[class*='status']"
            ]
            
            items = []
            for selector in selectors:
                items = await self.playwright_page.query_selector_all(selector)
                if items:
                    utils.logger.info(f"[XueqiuClient] Found {len(items)} items with selector: {selector}")
                    break
            
            if not items:
                all_links = await self.playwright_page.query_selector_all('a[href^="/"][href*="/"]')
                utils.logger.info(f"[XueqiuClient] Found {len(all_links)} potential post links")
                
                seen_urls = set()
                for link in all_links:
                    try:
                        href = await link.get_attribute("href")
                        if not href or not re.match(r'^/\d+/\d+', href):
                            continue
                        
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)
                        
                        full_url = "https://xueqiu.com" + href
                        
                        text = await link.inner_text()
                        if not text or len(text.strip()) < 5:
                            parent = await link.evaluate_handle("el => el.parentElement")
                            if parent:
                                try:
                                    text = await parent.evaluate("el => el.innerText")
                                except:
                                    pass
                        
                        if text and len(text.strip()) >= 5:
                            content = text.strip()[:500]
                            title = content[:50].replace("\n", " ").strip()
                            if len(content) > 50:
                                title += "..."
                            
                            posts.append({
                                "note_id": href,
                                "title": title,
                                "content": content,
                                "user_nickname": "Unknown",
                                "create_time": "Unknown",
                                "note_url": full_url
                            })
                            
                            if len(posts) >= 20:
                                break
                                
                    except Exception as e:
                        utils.logger.debug(f"[XueqiuClient] Error parsing link: {e}")
                        continue
            else:
                for item in items[:20]:
                    try:
                        link = await item.query_selector('a[href^="/"]')
                        if not link:
                            continue
                        
                        href = await link.get_attribute("href")
                        if not href or not re.match(r'^/\d+/\d+', href):
                            continue
                        
                        full_url = "https://xueqiu.com" + href
                        
                        content = await item.inner_text()
                        content = content.strip()[:500] if content else ""
                        
                        if content:
                            title = content[:50].replace("\n", " ").strip()
                            if len(content) > 50:
                                title += "..."
                            
                            posts.append({
                                "note_id": href,
                                "title": title,
                                "content": content,
                                "user_nickname": "Unknown",
                                "create_time": "Unknown",
                                "note_url": full_url
                            })
                            
                    except Exception as e:
                        utils.logger.debug(f"[XueqiuClient] Error parsing item: {e}")
                        continue
                        
        except Exception as e:
            utils.logger.error(f"[XueqiuClient._parse_page_content] Error: {e}")
            
        return posts

    async def get_note_detail(self, note_url: str) -> Dict:
        """获取帖子详情"""
        utils.logger.info(f"[XueqiuClient.get_note_detail] Fetching {note_url}")
        
        try:
            await self._ensure_cookies()
            
            match = re.search(r'/(\d{10,})/(\d+)', note_url)
            
            if match:
                status_id = match.group(2)
                api_url = f"https://xueqiu.com/statuses/show.json?id={status_id}"
                
                response = await self.playwright_page.goto(api_url, wait_until="domcontentloaded")
                
                if response and response.ok:
                    try:
                        json_text = await self.playwright_page.evaluate("() => document.body.innerText")
                        data = json.loads(json_text)
                        
                        if "status" in data:
                            status = data["status"]
                            
                            content = status.get("text", "") or status.get("description", "")
                            content = re.sub(r'<[^>]+>', '', content)
                            
                            title = status.get("title", "")
                            if not title:
                                title = content[:30] + "..." if len(content) > 30 else content
                            
                            user = status.get("user", {})
                            author = user.get("screen_name", "Unknown") if isinstance(user, dict) else "Unknown"
                            
                            create_time = status.get("created_at", 0)
                            
                            return {
                                "note_id": str(status_id),
                                "title": title.strip(),
                                "content": content.strip(),
                                "user_nickname": author,
                                "note_url": note_url,
                                "create_time": create_time,
                                "comments": []
                            }
                    except json.JSONDecodeError:
                        pass
            
            # 备用方案：直接解析页面
            await self.playwright_page.goto(note_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            content = ""
            for selector in [".article__bd__detail", ".status-content", ".detail__content", '[class*="content"]']:
                try:
                    content_el = await self.playwright_page.query_selector(selector)
                    if content_el:
                        content = await content_el.inner_text()
                        if content.strip():
                            break
                except:
                    continue
            
            title = ""
            try:
                title_el = await self.playwright_page.query_selector(".article__bd__title, .status-title")
                if title_el:
                    title = await title_el.inner_text()
            except:
                pass
            
            if not title:
                title = content[:30] + "..." if content and len(content) > 30 else content

            author = "Unknown"
            try:
                author_el = await self.playwright_page.query_selector(".avatar__name, .user-name, [class*='author']")
                if author_el:
                    author = await author_el.inner_text()
            except:
                pass
                
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
            utils.logger.error(f"[XueqiuClient.get_note_detail] Error: {e}")
            return {}

    async def get_note_comments(self, note_url: str) -> List[Dict]:
        """获取帖子评论"""
        comments = []
        
        try:
            await self._ensure_cookies()
            
            match = re.search(r'/(\d{10,})/(\d+)', note_url)
            
            if match:
                status_id = match.group(2)
                api_url = f"https://xueqiu.com/statuses/comments.json?id={status_id}&count=50&page=1"
                
                response = await self.playwright_page.goto(api_url, wait_until="domcontentloaded")
                
                if response and response.ok:
                    try:
                        json_text = await self.playwright_page.evaluate("() => document.body.innerText")
                        data = json.loads(json_text)
                        
                        if "comments" in data:
                            for item in data["comments"]:
                                text = item.get("text", "")
                                text = re.sub(r'<[^>]+>', '', text)
                                
                                user = item.get("user", {})
                                user_name = user.get("screen_name", "Unknown") if isinstance(user, dict) else "Unknown"
                                
                                if text.strip():
                                    comments.append({
                                        "content": text.strip(),
                                        "create_time": item.get("created_at", 0),
                                        "user_nickname": user_name
                                    })
                    except json.JSONDecodeError:
                        pass
            
            if not comments:
                comment_els = await self.playwright_page.query_selector_all(".comment-item, .comment-detail, [class*='comment']")
                for el in comment_els[:20]:
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
                        
        except Exception as e:
            utils.logger.error(f"[XueqiuClient.get_note_comments] Error: {e}")
            
        return comments
