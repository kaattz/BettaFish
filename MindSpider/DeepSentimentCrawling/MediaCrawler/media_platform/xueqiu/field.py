from enum import Enum

class SearchSortType(Enum):
    """search sort type"""
    # 按时间
    TIME = "time"
    # 按相关性
    RELEVANCE = "relevance"
