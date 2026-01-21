# -*- coding: utf-8 -*-
from typing import List

import config
from base.base_crawler import AbstractStore
from model.m_guba import GubaNote, GubaComment
from tools import utils
from var import source_keyword_var

from ._store_impl import *

class GubaStoreFactory:
    STORES = {
        "csv": GubaCsvStoreImplement,
        "db": GubaDbStoreImplement,
        "json": GubaJsonStoreImplement,
        "sqlite": GubaSqliteStoreImplement,
        "postgresql": GubaDbStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        store_class = GubaStoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError("[GubaStoreFactory.create_store] Invalid save option")
        return store_class()

async def update_guba_note(note_item: GubaNote):
    note_item.source_keyword = source_keyword_var.get()
    save_note_item = note_item.model_dump()
    save_note_item.update({"last_modify_ts": utils.get_current_timestamp()})
    utils.logger.info(f"[store.guba.update_guba_note] note: {save_note_item.get('title')}")
    await GubaStoreFactory.create_store().store_content(save_note_item)

async def update_guba_note_comment(comment_item: GubaComment):
    save_comment_item = comment_item.model_dump()
    save_comment_item.update({"last_modify_ts": utils.get_current_timestamp()})
    await GubaStoreFactory.create_store().store_comment(save_comment_item)
