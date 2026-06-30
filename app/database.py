from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./plant_dashboard_v2.db")

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
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=True)

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

    # MTTR & failure classification (matches RAG_april schema)
    mttr_hours = Column(Float, nullable=True)           # Mean Time To Repair in hours
    severity_level = Column(String, nullable=True)      # Critical | High | Medium | Low
    failure_type = Column(String, nullable=True)        # Electrical | Mechanical | Hydraulic | Pneumatic | Software | Structural | Other

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
    component_name = Column(String, nullable=True, index=True)

    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="breakdown_logs")


class CAPA(Base):
    __tablename__ = "capas"

    id = Column(Integer, primary_key=True, index=True)
    breakdown_log_id = Column(Integer, ForeignKey("breakdown_logs.id"), nullable=True)
    action_type = Column(String, default="Corrective")   # Corrective | Preventive | Both
    actions = Column(Text, nullable=True)                 # newline-separated action steps
    owner = Column(String, nullable=True)
    due_date = Column(String, nullable=True)              # ISO date string
    priority = Column(String, nullable=True)              # High | Medium | Low
    impact_level = Column(String, nullable=True)          # High | Medium | Low
    status = Column(String, default="Open")               # Open | In Progress | Pending Validation | Completed
    root_cause = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)         # set when status -> Completed; powers CAPA effectiveness (before/after)

    tasks = relationship("CAPATask", back_populates="capa", cascade="all, delete-orphan")
    comments = relationship("CAPAComment", back_populates="capa", cascade="all, delete-orphan")


class CAPATask(Base):
    __tablename__ = "capa_tasks"

    id = Column(Integer, primary_key=True, index=True)
    capa_id = Column(Integer, ForeignKey("capas.id", ondelete="CASCADE"))
    task_title = Column(String)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    capa = relationship("CAPA", back_populates="tasks")


class CAPAComment(Base):
    __tablename__ = "capa_comments"

    id = Column(Integer, primary_key=True, index=True)
    capa_id = Column(Integer, ForeignKey("capas.id", ondelete="CASCADE"))
    comment_text = Column(Text)
    author_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    capa = relationship("CAPA", back_populates="comments")


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    asset_tag = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, nullable=True)
    location = Column(String, nullable=True)
    criticality = Column(String, default="Medium")  # Critical | High | Medium | Low
    asset_health_score = Column(Integer, default=100)  # 0–100
    created_at = Column(DateTime, default=datetime.utcnow)

    components = relationship("EquipmentComponent", back_populates="equipment", cascade="all, delete-orphan")


class EquipmentComponent(Base):
    __tablename__ = "equipment_components"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="components")


class Conversation(Base):
    """A ProdAI Assistant chat thread (ChatGPT-style library entry)."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship(
        "ChatMessage", back_populates="conversation",
        cascade="all, delete-orphan", order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    """A single message within a Conversation."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role = Column(String)                       # 'user' | 'assistant'
    content = Column(Text)
    sources = Column(Text, nullable=True)       # JSON: {"manuals": [...], "web": [...]}
    attachments = Column(Text, nullable=True)   # JSON: [{type, name, url}] for persisted uploads
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialised.")
