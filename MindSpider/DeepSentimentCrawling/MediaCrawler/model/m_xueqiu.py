# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field

class XueqiuNote(BaseModel):
    """
    雪球帖子/文章
    """
    note_id: str = Field(..., description="帖子ID/链接")
    title: str = Field(..., description="帖子标题")
    content: str = Field(default="", description="帖子内容")
    note_url: str = Field(..., description="帖子链接")
    publish_time: str = Field(default="", description="发布时间")
    user_nickname: str = Field(default="", description="用户昵称")
    user_link: str = Field(default="", description="用户链接")
    read_count: int = Field(default=0, description="阅读数")
    comment_count: int = Field(default=0, description="评论数")
    source_keyword: str = Field(default="", description="来源关键词")

class XueqiuComment(BaseModel):
    """
    雪球评论
    """
    comment_id: str = Field(default="", description="评论ID")
    content: str = Field(..., description="评论内容")
    publish_time: str = Field(default="", description="发布时间")
    user_nickname: str = Field(default="", description="用户昵称")
    note_id: str = Field(..., description="帖子ID")
    note_url: str = Field(..., description="帖子链接")
