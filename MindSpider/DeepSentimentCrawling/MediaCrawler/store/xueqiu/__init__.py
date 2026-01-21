# -*- coding: utf-8 -*-
from typing import List

import config
from base.base_crawler import AbstractStore
from model.m_xueqiu import XueqiuNote, XueqiuComment
from tools import utils
from var import source_keyword_var

from ._store_impl import *

class XueqiuStoreFactory:
    STORES = {
        "csv": XueqiuCsvStoreImplement,
        "db": XueqiuDbStoreImplement,
        "json": XueqiuJsonStoreImplement,
        "sqlite": XueqiuSqliteStoreImplement,
        "postgresql": XueqiuDbStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        store_class = XueqiuStoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError("[XueqiuStoreFactory.create_store] Invalid save option")
        return store_class()

async def update_xueqiu_note(note_item: XueqiuNote):
    note_item.source_keyword = source_keyword_var.get()
    save_note_item = note_item.model_dump()
    save_note_item.update({"last_modify_ts": utils.get_current_timestamp()})
    utils.logger.info(f"[store.xueqiu.update_xueqiu_note] note: {save_note_item.get('title')}")
    await XueqiuStoreFactory.create_store().store_content(save_note_item)

async def update_xueqiu_note_comment(comment_item: XueqiuComment):
    save_comment_item = comment_item.model_dump()
    save_comment_item.update({"last_modify_ts": utils.get_current_timestamp()})
    await XueqiuStoreFactory.create_store().store_comment(save_comment_item)
