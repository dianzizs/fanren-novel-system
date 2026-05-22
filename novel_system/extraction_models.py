from __future__ import annotations
from pydantic import BaseModel, Field

class CharacterExtraction(BaseModel):
    name: str = Field(description="角色姓名")
    aliases: list[str] = Field(default_factory=list, description="该角色在本段文本中的其他称呼或别名")
    description: str = Field(description="关于该角色的简短特征或行为描述")

class RelationshipExtraction(BaseModel):
    source: str = Field(description="源角色姓名")
    target: str = Field(description="目标角色姓名")
    description: str = Field(description="两者关系的具体描述")

class EventExtraction(BaseModel):
    description: str = Field(description="事件的具体描述")
    participants: list[str] = Field(default_factory=list, description="参与该事件的角色姓名列表")

class ChapterChunkExtraction(BaseModel):
    characters: list[CharacterExtraction] = Field(default_factory=list, description="本段提取出的所有角色")
    relationships: list[RelationshipExtraction] = Field(default_factory=list, description="本段提取出的所有角色关系")
    events: list[EventExtraction] = Field(default_factory=list, description="本段提取出的所有事件")
