import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://maliki:localdev123@localhost:5432/clinical_agent")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        row = result.fetchone()
        version = row[0][:50] if row else "unknown"
        print(f"[OK] PostgreSQL: {version}")

if __name__ == "__main__":
    test_connection()
