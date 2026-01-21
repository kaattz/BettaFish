import asyncio
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

from . import config
from base.base_crawler import AbstractLogin
from tools import utils


class XueqiuLogin(AbstractLogin):
    def __init__(self,
                 login_type: str,
                 browser_context: BrowserContext,
                 context_page: Page,
                 login_phone: Optional[str] = "",
                 cookie_str: str = ""
                 ):
        self.login_type = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.login_phone = login_phone
        self.cookie_str = cookie_str

    async def begin(self):
        """Start login Xueqiu"""
        utils.logger.info("[XueqiuLogin.begin] Begin login Xueqiu ...")
        if self.login_type == "qrcode":
            await self.login_by_qrcode()
        elif self.login_type == "phone":
            await self.login_by_mobile()
        elif self.login_type == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[XueqiuLogin.begin] Invalid Login Type ...")

    async def login_by_qrcode(self):
        """login Xueqiu website by qrcode"""
        utils.logger.info("[XueqiuLogin.login_by_qrcode] Begin login Xueqiu by qrcode ...")
        
        # Navigate to home page and trigger login modal
        await self.context_page.goto("https://xueqiu.com/")
        await self.context_page.wait_for_load_state("domcontentloaded")
        
        # Click login button if not automatically popped up
        # Xueqiu often requires clicking "登录"
        try:
             # Try to find a login button (Selector needs verification)
            login_btn = await self.context_page.query_selector(".nav__login__btn, .login-btn")
            if login_btn:
                await login_btn.click()
        except Exception:
            pass

        utils.logger.info(f"[XueqiuLogin.login_by_qrcode] Please scan the QR code using Xueqiu App ...")
        
        try:
            await self.check_login_state()
        except RetryError:
            utils.logger.info("[XueqiuLogin.login_by_qrcode] Login failed ...")
            sys.exit()

        utils.logger.info("[XueqiuLogin.login_by_qrcode] Login successful!")

    async def login_by_cookies(self):
        """login by cookies"""
        utils.logger.info("[XueqiuLogin.login_by_cookies] Begin login by cookie ...")
        for key, value in utils.convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".xueqiu.com",
                'path': "/"
            }])

    async def login_by_mobile(self):
        pass

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self) -> bool:
        """Check if logged in by looking for specific cookies"""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)
        # Check for specific Xueqiu auth cookie, e.g., 'xq_a_token'
        if cookie_dict.get("xq_a_token"):
            return True
        return False
