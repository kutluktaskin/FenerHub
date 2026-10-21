"""SQLAlchemy modelleri. Şema değişiklikleri Alembic ile yapılır (migrations/versions)."""
from sqlalchemy import (
    Boolean, Column, Float, Integer, String, Text, Date, Time, ForeignKey, Index, UniqueConstraint, false
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
    api_id = Column(Integer)               # SportsAPI oyuncu kimliği (fotoğraf: img/players/<api_id>.png)
    team = relationship("Team")
    stats = relationship("PlayerStat", back_populates="player")


class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True)
    competition = Column(String, nullable=False)  # super_lig | uefa
    matchday = Column(Integer)
    match_date = Column(Date)          # "Sezon Sonu" gibi belirsizse boş
    kickoff_time = Column(Time)        # saat belirlenmediyse boş
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    home_score = Column(Integer)
    away_score = Column(Integer)
    status = Column(String, default="scheduled")  # scheduled | live | finished
    minute = Column(String)            # canlı maçta: "89'"
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    absences = relationship("Absence", back_populates="match")
    status_code = Column(Integer)
    period_start = Column(Integer)
    period_initial = Column(Integer)
    api_id = Column(Integer)

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
    """match_id boşsa genel sakatlık/ceza raporu, doluysa o maçın eksikleri."""
    __tablename__ = "absences"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    type = Column(String, nullable=False)  # injury | suspension | returned
    reason = Column(String)
    return_note = Column(String)           # "Mart 2027", "2 Hafta"
    # api: kadro verisindeki missingPlayers'tan otomatik (app/absences_sync.py)
    # manual: elle girildi (scripts/add_absence.py); otomatik güncelleme bunlara dokunmaz
    source = Column(String(10), nullable=False, default="manual", server_default="manual")
    player = relationship("Player")
    match = relationship("Match", back_populates="absences")


class Standing(Base):
    __tablename__ = "standings"
    __table_args__ = (UniqueConstraint("competition", "season", "team_id"),)
    id = Column(Integer, primary_key=True)
    competition = Column(String, nullable=False)  # super_lig | uefa
    season = Column(String, default="2026-27")
    position = Column(Integer, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    drawn = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    goal_difference = Column(Integer, default=0)
    points = Column(Integer, default=0)
    team = relationship("Team")


class ForumPost(Base):
    """12. Adam forum mesajı (eskiden ayrı forum.db'deydi)."""
    __tablename__ = "posts"
    __table_args__ = (Index("ix_posts_room_id", "room", "id"),)
    id = Column(Integer, primary_key=True)
    room = Column(String(64), nullable=False)
    nick = Column(String(40), nullable=False)
    body = Column(Text, nullable=False)
    fire = Column(Integer, nullable=False, default=0, server_default="0")
    heart = Column(Integer, nullable=False, default=0, server_default="0")
    ts = Column(Integer, nullable=False)                 # Unix zamanı (saniye)
    owner = Column(String(64))                           # gizli sahiplik anahtarı, API'ye verilmez
    parent_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"))
    deleted = Column(Boolean, nullable=False, default=False, server_default=false())
    hidden = Column(Boolean, nullable=False, default=False, server_default=false())   # bildirimle gizlendi


class PostReport(Base):
    """Mesaj bildirimi. reporter: bildirenin IP'sinin özeti (IP'nin kendisi saklanmaz)."""
    __tablename__ = "post_reports"
    __table_args__ = (UniqueConstraint("post_id", "reporter", name="uq_post_reports_post_reporter"),)
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    reporter = Column(String(64), nullable=False)
    ts = Column(Integer, nullable=False)


class ApiCache(Base):
    """SportsAPI cevaplarının önbelleği (eskiden pages_fb/, detail_cache/ ve *_cache.json
    dosyalarıydı; Render'ın diski kalıcı olmadığı için her uyanışta kayboluyordu)."""
    __tablename__ = "api_cache"
    key = Column(String(128), primary_key=True)          # "pages:next_0", "detail:16938965:incidents"
    data = Column(Text, nullable=False)                  # JSON metni
    fetched_at = Column(Float, nullable=False, default=0)  # Unix zamanı; 0 = bir sonraki turda yenile


class Prediction(Base):
    """Skor tahmini. player: cihaz anahtarının özeti (anahtarın kendisi saklanmaz);
    "model" ise istatistik modelinin tahminidir. points maç bitince hesaplanır."""
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("match_id", "player", name="uq_predictions_match_player"),
                      Index("ix_predictions_player", "player"))
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    player = Column(String(64), nullable=False)
    nick = Column(String(40), nullable=False)
    home = Column(Integer, nullable=False)
    away = Column(Integer, nullable=False)
    ts = Column(Integer, nullable=False)
    points = Column(Integer)
    match = relationship("Match")


class MotmVote(Base):
    """Maçın oyuncusu oyu: maç bitince 24 saat açık, kişi başı bir oy."""
    __tablename__ = "motm_votes"
    __table_args__ = (UniqueConstraint("match_id", "player", name="uq_motm_match_player"),)
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    player = Column(String(64), nullable=False)
    choice = Column(String(80), nullable=False)
    ts = Column(Integer, nullable=False)
