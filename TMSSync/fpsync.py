from __future__ import print_function
from . import config
from . import attendance
from . import connection
import pyodbc
import os


Connection = connection.Connection
__DIR__ = os.path.dirname(__file__)
__FPSYNC_QUERY_FILE__ = os.path.join(__DIR__, 'queries', 'FPSync.sql')


def get_fpsync_query():
    with open(__FPSYNC_QUERY_FILE__) as query_file:
        return query_file.read()


def get_new_fp_entries():

    conn = Connection()
    new_fp_entries = None
    cur = conn.cursor()
    cur.execute(get_fpsync_query())

    while True:
        try:
            new_fp_entries = cur.fetchall()
            break
        except pyodbc.ProgrammingError:
            pass
        if not cur.nextset():
            break

    return new_fp_entries


def perform_sync():
    print('Getting new entries ...')
    entries = get_new_fp_entries()

    print('Making %d Entries one by one' % len(entries))
    for entry in (entries if entries else []):
        try:
            attendance.FPEntry(
                    entry[3], entry[2], entry[0], entry[1]).record()
            print (entry, 'success')
        except ValueError as ve:
            print (entry, 'failed: ', str(ve))
