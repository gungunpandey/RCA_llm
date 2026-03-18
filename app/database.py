from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./plant_dashboard_v2.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    name = Column(String)
    # Admin sees all divisions; any other value restricts to that division only
    division = Column(String, default="Admin")

    breakdown_logs = relationship("BreakdownLog", back_populates="author")


class BreakdownLog(Base):
    __tablename__ = "breakdown_logs"

    id = Column(Integer, primary_key=True, index=True)
    machine_name = Column(String, index=True)
    division = Column(String, default="Unknown", index=True)
    description = Column(String)
    downtime_minutes = Column(Integer, default=0)
    status = Column(String, default="Open")   # Open | In Progress | Incomplete | Preventive | Not Approved | Resolved | Completed
    logged_at = Column(DateTime, default=datetime.utcnow)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    feed_loss = Column(Boolean, default=False)
    attached_doc = Column(String, nullable=True)
    doc_description = Column(String, nullable=True)
    revenue_loss = Column(Float, nullable=True)

    # Stores RCA JSON. Two supported formats:
    #
    # AI-generated:
    #   {"type": "ai_generated", "timestamp": "...", "five_whys_analysis": {...},
    #    "domain_insights": {...}, "final_root_cause": "...", "final_confidence": 0.85,
    #    "team_list": "...", "capa": [{"action":"","responsibility":"","targetDate":""}]}
    #
    # Manual tree:
    #   {"type": "manual_tree", "timestamp": "...", "nodes": [{id, parentId, text}]}
    #
    # Legacy (raw array, auto-detected on read):
    #   [{id, parentId, text}, ...]
    rca_data = Column(Text, nullable=True)

    extended_info = Column(String, nullable=True)  # used for CSV-import RCA details

    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="breakdown_logs")


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialised.")
