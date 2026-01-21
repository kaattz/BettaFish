import asyncio
import functools
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

from . import config
from base.base_crawler import AbstractLogin
from tools import utils


class GubaLogin(AbstractLogin):
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
        """Start login Guba"""
        utils.logger.info("[GubaLogin.begin] Begin login Guba ...")
        if self.login_type == "qrcode":
            await self.login_by_qrcode()
        elif self.login_type == "phone":
            await self.login_by_mobile()
        elif self.login_type == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[GubaLogin.begin] Invalid Login Type ...")

    async def login_by_qrcode(self):
        """login Guba website by qrcode"""
        utils.logger.info("[GubaLogin.login_by_qrcode] Begin login Guba by qrcode ...")
        
        # Navigate to login page
        await self.context_page.goto("https://passport.eastmoney.com/pub/login")
        
        # Wait for QR code element
        # Eastmoney login page might have different structure, this is a generic attempt
        # Usually it's an image or canvas
        try:
            # Check if we need to switch to QR code tab
            # Some login pages default to phone/password
            # Example selector for switch to QR code
            # await self.context_page.click("selector_for_qrcode_tab") 
            pass
        except Exception:
            pass

        # Assuming standard implementation, waiting for user to scan
        utils.logger.info(f"[GubaLogin.login_by_qrcode] Please scan the QR code on the browser ...")
        
        # We can implement auto-QR detection if selectors are known, 
        # but for now, we rely on user interaction in non-headless mode 
        # or checking cookies loop.
        
        try:
            await self.check_login_state()
        except RetryError:
            utils.logger.info("[GubaLogin.login_by_qrcode] Login failed ...")
            sys.exit()

        utils.logger.info("[GubaLogin.login_by_qrcode] Login successful!")

    async def login_by_cookies(self):
        """login by cookies"""
        utils.logger.info("[GubaLogin.login_by_cookies] Begin login by cookie ...")
        for key, value in utils.convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".eastmoney.com",
                'path': "/"
            }])

    async def login_by_mobile(self):
        pass

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self) -> bool:
        """Check if logged in by looking for specific cookies"""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)
        # Check for specific Eastmoney auth cookie, e.g., 'pi' or 'u'
        if cookie_dict.get("pi") or cookie_dict.get("u"):
            return True
        return False
