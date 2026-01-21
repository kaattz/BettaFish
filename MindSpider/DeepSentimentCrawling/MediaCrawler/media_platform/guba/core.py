import asyncio
import os
from typing import List

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import create_ip_pool, IpInfoModel
from store import guba as guba_store
from model.m_guba import GubaNote, GubaComment
from tools import utils
from var import crawler_type_var, source_keyword_var

from .client import GubaClient
from .login import GubaLogin


class GubaCrawler(AbstractCrawler):
    context_page: Page
    guba_client: GubaClient
    browser_context: BrowserContext

    def __init__(self) -> None:
        self.index_url = "https://guba.eastmoney.com/"
        self.user_agent = utils.get_user_agent()

    async def start(self) -> None:
        playwright_proxy_format = None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, _ = utils.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium,
                playwright_proxy_format,
                self.user_agent,
                headless=config.HEADLESS
            )
            
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.guba_client = GubaClient(playwright_page=self.context_page)

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                await self.search()
            
            utils.logger.info("[GubaCrawler] Finished.")

    async def search(self) -> None:
        utils.logger.info("[GubaCrawler] Begin search...")
        keywords = config.KEYWORDS.split(",")
        for keyword in keywords:
            source_keyword_var.set(keyword)
            utils.logger.info(f"[GubaCrawler] Keyword: {keyword}")
            
            # 爬取多页，直到没有帖子或时间过滤停止
            max_pages = 20  # 最多爬取20页
            for page in range(1, max_pages + 1): 
                posts, should_continue = await self.guba_client.search_posts(keyword, page)
                if not posts:
                    utils.logger.info(f"[GubaCrawler] No posts found on page {page}, stopping")
                    break
                    
                for post_dict in posts:
                    # Save Post
                    note = GubaNote(**post_dict)
                    note.source_keyword = keyword
                    await guba_store.update_guba_note(note)
                    
                    # Get Details (update content)
                    detail_dict = await self.guba_client.get_note_detail(note.note_url)
                    if detail_dict:
                         # Update note with full content
                         note.content = detail_dict.get("content", "")
                         note.user_nickname = detail_dict.get("user_nickname", "")
                         await guba_store.update_guba_note(note)

                    # Get Comments
                    comments_list = await self.guba_client.get_note_comments(note.note_url)
                    for comment_dict in comments_list:
                        comment = GubaComment(
                            content=comment_dict.get("content"),
                            user_nickname=comment_dict.get("user_nickname"),
                            publish_time=str(comment_dict.get("create_time")),
                            note_id=note.note_id,
                            note_url=note.note_url
                        )
                        await guba_store.update_guba_note_comment(comment)
                    
                    utils.logger.info(f"[GubaCrawler] Crawled {note.title}")
                    await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                
                # 检查是否应该继续爬取下一页
                if not should_continue:
                    utils.logger.info(f"[GubaCrawler] Time filter triggered, stopping at page {page}")
                    break

    async def launch_browser(self, chromium: BrowserType, playwright_proxy, user_agent, headless=True) -> BrowserContext:
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % "guba")
            return await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                proxy=playwright_proxy,
                user_agent=user_agent
            )
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)
            return await browser.new_context(user_agent=user_agent)
