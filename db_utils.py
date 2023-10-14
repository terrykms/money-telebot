import os
import logging

import pymysql

from telegram.ext import ConversationHandler

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


ENDPOINT = os.environ.get('ENDPOINT')
RDS_USERNAME = os.environ.get('RDS_USERNAME')
RDS_PASSWORD = os.environ.get('RDS_PASSWORD')
DATABASE = os.environ.get('DATABASE')
PORT = 3306


def connect_to_database():
    # returns connection object if successful, error message & state if unsuccessful.
    try:
        connection = pymysql.connect(
            host=ENDPOINT,
            port=PORT,
            user=RDS_USERNAME,
            password=RDS_PASSWORD,
            database=DATABASE
        )
    except pymysql.Error as e:
        return None, {
            'error': e,
            'message': "Could not connect to database, try again later. /start",
            'state': ConversationHandler.END
        }

    return connection, {'state': "successful"}
