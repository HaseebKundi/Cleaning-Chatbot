"""
Run once before first use (and again any time data/faq.json changes):

    python seed_data.py

Creates the SQLite tables and builds the Chroma FAQ index.
"""
from app.database import Base, engine
from app import rag


def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created.")

    count = rag.load_faq_into_chroma()
    print(f"Loaded {count} FAQ entries into Chroma.")


if __name__ == "__main__":
    main()
