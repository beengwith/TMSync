import pyodbc
from .config import DB_CONN_STR


__all__ = ['Connection']


class Connection(object):
    _conn = None

    def __new__(cls):
        if cls._conn is None:
            cls.create_new()
        return super(Connection, cls).__new__(cls)

    @classmethod
    def create_new(cls):
        if cls._conn is not None:
            cls.close()
        cls._conn = pyodbc.connect(DB_CONN_STR)
        cls._conn.autocommit = True

    def execute(self, query, *args):
        return self._conn.execute(query, *args)

    def cursor(self):
        return self._conn.cursor()

    @classmethod
    def close(cls):
        cls._conn.close()
        cls._conn = None
