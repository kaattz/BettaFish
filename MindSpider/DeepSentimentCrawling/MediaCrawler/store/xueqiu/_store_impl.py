# -*- coding: utf-8 -*-
import asyncio
from typing import Dict

from sqlalchemy import select

import config
from base.base_crawler import AbstractStore
from database.models import XueqiuNote as DBXueqiuNote, XueqiuComment as DBXueqiuComment
from database.db_session import get_session
from tools.async_file_writer import AsyncFileWriter
from var import crawler_type_var

class XueqiuCsvStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="xueqiu", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        await self.writer.write_to_csv(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        await self.writer.write_to_csv(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        pass

class XueqiuDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        note_id = content_item.get("note_id")
        async with get_session() as session:
            stmt = select(DBXueqiuNote).where(DBXueqiuNote.note_id == note_id)
            res = await session.execute(stmt)
            db_note = res.scalar_one_or_none()
            if db_note:
                for key, value in content_item.items():
                    setattr(db_note, key, value)
            else:
                db_note = DBXueqiuNote(**content_item)
                session.add(db_note)
            await session.commit()

    async def store_comment(self, comment_item: Dict):
        async with get_session() as session:
            # Simple append for comments
            db_comment = DBXueqiuComment(**comment_item)
            session.add(db_comment)
            await session.commit()

    async def store_creator(self, creator: Dict):
        pass

class XueqiuJsonStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="xueqiu", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        await self.writer.write_single_item_to_json(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        await self.writer.write_single_item_to_json(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        pass

class XueqiuSqliteStoreImplement(XueqiuDbStoreImplement):
    pass
