import configparser
import os


__all__ = ['DB_CONN_STR', 'read_config']


currentdir = os.path.dirname(__file__)
configfile = os.path.join(currentdir, 'config.ini')


DB_CONN_STR = ''


def _get_connection_str():
    global DB_CONN_STR
    parser = configparser.ConfigParser()
    parser.read(configfile)
    DB_CONN_STR = ';'.join(
            '%s=%s' % item for item in parser['Connection'].items())


def read_config():
    _get_connection_str()


read_config()
