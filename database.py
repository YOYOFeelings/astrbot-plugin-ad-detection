import os
from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

Base = declarative_base()

class ViolationRecord(Base):
    __tablename__ = "violation_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    group_id = Column(String, nullable=False)
    violation_count = Column(Integer, default=1)
    last_violation_time = Column(DateTime, default=datetime.now)

class UserWhitelist(Base):
    __tablename__ = "user_whitelist"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    group_id = Column(String, nullable=False)
    added_time = Column(DateTime, default=datetime.now)

class GroupWhitelist(Base):
    __tablename__ = "group_whitelist"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String, unique=True, nullable=False)
    added_time = Column(DateTime, default=datetime.now)

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.create_tables()
    
    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def add_violation(self, user_id: str, group_id: str) -> ViolationRecord:
        session = self.get_session()
        try:
            record = session.query(ViolationRecord).filter(
                ViolationRecord.user_id == user_id,
                ViolationRecord.group_id == group_id
            ).first()
            
            if record:
                record.violation_count += 1
                record.last_violation_time = datetime.now()
            else:
                record = ViolationRecord(
                    user_id=user_id,
                    group_id=group_id
                )
                session.add(record)
            
            session.commit()
            session.refresh(record)
            return record
        finally:
            session.close()
    
    def get_violation(self, user_id: str, group_id: str) -> Optional[ViolationRecord]:
        session = self.get_session()
        try:
            return session.query(ViolationRecord).filter(
                ViolationRecord.user_id == user_id,
                ViolationRecord.group_id == group_id
            ).first()
        finally:
            session.close()
    
    def reset_violation(self, user_id: str, group_id: str) -> bool:
        session = self.get_session()
        try:
            record = session.query(ViolationRecord).filter(
                ViolationRecord.user_id == user_id,
                ViolationRecord.group_id == group_id
            ).first()
            
            if record:
                session.delete(record)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def add_user_to_whitelist(self, user_id: str, group_id: str) -> bool:
        session = self.get_session()
        try:
            existing = session.query(UserWhitelist).filter(
                UserWhitelist.user_id == user_id,
                UserWhitelist.group_id == group_id
            ).first()
            
            if existing:
                return False
            
            whitelist = UserWhitelist(
                user_id=user_id,
                group_id=group_id
            )
            session.add(whitelist)
            session.commit()
            return True
        finally:
            session.close()
    
    def is_user_whitelisted(self, user_id: str, group_id: str) -> bool:
        session = self.get_session()
        try:
            return session.query(UserWhitelist).filter(
                UserWhitelist.user_id == user_id,
                UserWhitelist.group_id == group_id
            ).first() is not None
        finally:
            session.close()
    
    def remove_user_from_whitelist(self, user_id: str, group_id: str) -> bool:
        session = self.get_session()
        try:
            record = session.query(UserWhitelist).filter(
                UserWhitelist.user_id == user_id,
                UserWhitelist.group_id == group_id
            ).first()
            
            if record:
                session.delete(record)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def add_group_to_whitelist(self, group_id: str) -> bool:
        session = self.get_session()
        try:
            existing = session.query(GroupWhitelist).filter(
                GroupWhitelist.group_id == group_id
            ).first()
            
            if existing:
                return False
            
            whitelist = GroupWhitelist(group_id=group_id)
            session.add(whitelist)
            session.commit()
            return True
        finally:
            session.close()
    
    def is_group_whitelisted(self, group_id: str) -> bool:
        session = self.get_session()
        try:
            return session.query(GroupWhitelist).filter(
                GroupWhitelist.group_id == group_id
            ).first() is not None
        finally:
            session.close()
    
    def remove_group_from_whitelist(self, group_id: str) -> bool:
        session = self.get_session()
        try:
            record = session.query(GroupWhitelist).filter(
                GroupWhitelist.group_id == group_id
            ).first()
            
            if record:
                session.delete(record)
                session.commit()
                return True
            return False
        finally:
            session.close()
