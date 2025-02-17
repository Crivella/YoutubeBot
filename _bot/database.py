import os
from functools import wraps

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Create a database engine
DATABASE_ENGINE = os.getenv("DATABASE_ENGINE")
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_USERNAME = os.getenv("DATABASE_USERNAME")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")

if DATABASE_ENGINE == "sqlite":
    DATABASE_URL = f"sqlite:///{DATABASE_URL}"
elif DATABASE_ENGINE == "postgresql":
    DATABASE_URL = (
        f"postgresql+psycopg2://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_URL}"
    )


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    username = sqlalchemy.Column(sqlalchemy.String, unique=True)
    password = sqlalchemy.Column(sqlalchemy.String)
    email = sqlalchemy.Column(sqlalchemy.String)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)
    updated_at = sqlalchemy.Column(sqlalchemy.DateTime)


class Database:
    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        # self.session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.session = Session(self.engine)

    @staticmethod
    def commit_session(func):
        """Decorator to commit session after function execution"""

        @wraps(func)
        def wrapper(cls: "Database", *args, **kwargs):
            result = func(cls, *args, **kwargs)
            cls.session.commit()
            return result

        return wrapper

    def execute_in_session(self, func):
        with Session(self.engine) as session:
            return func(session)
