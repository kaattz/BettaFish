from enum import Enum

class SearchSortType(Enum):
    """search sort type"""
    # 按时间倒序
    TIME_DESC = "time"
    # 按相关性
    RELEVANCE = "relevance"
