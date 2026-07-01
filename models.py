"""
EV Finder — Modelos Pydantic para validação dos dados da API.
Garante que mudanças no formato da The Odds API sejam detectadas cedo.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Outcome(BaseModel):
    name:  str
    price: float
    point: Optional[float] = None

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"preço inválido: {v}")
        return v


class Market(BaseModel):
    key:      str
    outcomes: list[Outcome] = Field(default_factory=list)


class Bookmaker(BaseModel):
    key:     str
    title:   str = ""
    markets: list[Market] = Field(default_factory=list)


class Event(BaseModel):
    id:             str
    sport_key:      str
    sport_title:    str = ""
    commence_time:  str
    home_team:      str
    away_team:      str
    bookmakers:     list[Bookmaker] = Field(default_factory=list)
