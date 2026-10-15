"""Reset the database and generate demo data. Run: .venv/bin/python -m scripts.seed"""
from app.analytics import synth

if __name__ == "__main__":
    print(synth.seed())
