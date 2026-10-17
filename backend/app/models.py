from sqlalchemy import (
    Column, Integer, String, DateTime, Date, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    short_name = Column(String)
    logo_url = Column(String)


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    position = Column(String)
    shirt_number = Column(Integer)
    team_id = Column(Integer, ForeignKey("teams.id"))
    team = relationship("Team")
    stats = relationship("PlayerStat", back_populates="player")


class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True)
    competition = Column(String, nullable=False)  # super_lig | uefa_el
    matchday = Column(Integer)
    kickoff = Column(DateTime, nullable=False)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    home_score = Column(Integer)
    away_score = Column(Integer)
    status = Column(String, default="scheduled")  # scheduled | live | finished
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    absences = relationship("Absence", back_populates="match")


class PlayerStat(Base):
    __tablename__ = "player_stats"
    __table_args__ = (UniqueConstraint("player_id", "season"),)
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season = Column(String, default="2026-27")
    appearances = Column(Integer, default=0)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    player = relationship("Player", back_populates="stats")


class Absence(Base):
    __tablename__ = "absences"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    type = Column(String, nullable=False)  # injury | suspension
    reason = Column(String)
    expected_return = Column(Date, nullable=True)
    player = relationship("Player")
    match = relationship("Match", back_populates="absences")


class Standing(Base):
    __tablename__ = "standings"
    __table_args__ = (UniqueConstraint("competition", "season", "team_id"),)
    id = Column(Integer, primary_key=True)
    competition = Column(String, nullable=False)
    season = Column(String, default="2026-27")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    drawn = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    points = Column(Integer, default=0)
    team = relationship("Team")