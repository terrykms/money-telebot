import os
import logging
from datetime import datetime

import json

import pymysql

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (filters, ApplicationBuilder, ContextTypes,
                          MessageHandler, CommandHandler, ConversationHandler)

from dotenv import load_dotenv
load_dotenv()


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# GLOBAL VARIABLES

shift_dict = {
    "E": 8.5,
    "E6": 8.5,
    "E7": 8.5,
    "E8": 8.5,
    "E9": 8.5,
    "CA": 8.5,
    "CA1": 8.5,
    "CAF": 10,
    "F10": 10,
    "F11": 10,
    "F12": 10,
    "F8": 10,
    "F9": 10,
    "M": 8.5,
    "M12": 8.5,
    "L": 8.5,
    "L1": 8.5,
    "L2": 8,
    "L3": 7,
    "L4": 6,
    "L5": 5,
}


ADD_BUTTON_TEXT = '/add'
EDIT_BUTTON_TEXT = '/edit'
SUMMARY_BUTTON_TEXT = '/summary'

INITIATION = 0
CHECK_DATE, CHECK_SHIFT_TYPE, CONFIRM_DATA_ENTRY = range(1, 4)
CHECK_DATE_FOR_EDIT, CHECK_EDIT_OR_DELETE, EDIT_SHIFT_TYPE = range(4, 7)

RATE_PER_HOUR = 15
AUTHORIZED_USERNAMES = ['terrykms', 'q000xd']

# in-memory usage before adding into a database
in_memory_data = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if user.username not in AUTHORIZED_USERNAMES:
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    keyboard = [
        [
            KeyboardButton(text=ADD_BUTTON_TEXT),
            KeyboardButton(text=EDIT_BUTTON_TEXT),

        ],
        [
            KeyboardButton(text=SUMMARY_BUTTON_TEXT),
        ],
    ]

    await update.message.reply_text(
        "Welcome! What do you want to do?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True
        ))
    return INITIATION


# ADD COMMAND LOGIC
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_text = update.message.text

    logger.info("Message sent by %s: %s", user.username, user_text)

    await update.message.reply_text("Date of shift in DD/MM/YYYY (i.e. 01/01/2023).")

    return CHECK_DATE


async def check_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_text = update.message.text

    logger.info("Message sent by %s: %s", user.username, user_text)

    # conditional checks
    date_format = "%d/%m/%Y"
    try:
        datetime.strptime(user_text, date_format)
    except ValueError:
        await update.message.reply_text('Error in recognising date. Please ensure format is in DD/MM/YYYY.')
        return CHECK_DATE

    try:
        connection = pymysql.connect(
            host=os.environ.get('ENDPOINT'),
            port=3306,
            user=os.environ.get('RDS_USERNAME'),
            password=os.environ.get('RDS_PASSWORD'),
            database=os.environ.get('DATABASE')
        )
    except pymysql.Error as e:
        logger.error(e)
        await update.message.reply_text("Could not connect to database, try again later. /start")
        return ConversationHandler.END

    cursor = connection.cursor()

    try:
        check_duplicate_query = 'SELECT * FROM Entries WHERE shift_date=%s and username=%s'
        formatted_date = '-'.join(user_text.split('/')[::-1])
        data_entry = (formatted_date, user.username)
        cursor.execute(check_duplicate_query, data_entry)
        data = cursor.fetchone()
    except pymysql.Error as e:
        logger.error(e)
        cursor.close()
        connection.close()
        await update.message.reply_text("Could not insert data into database, try again later. /start")
        return ConversationHandler.END

    if data:
        fields = [field_md[0] for field_md in cursor.description]
        result = dict(zip(fields, data))
        logger.info('duplicate entry in database, informing user...')
        cursor.close()
        connection.close()
        await update.message.reply_text(f"Duplicate entry exists in records: \n\n Date: {result['shift_date']} \n Shift: {result['shift_type']} \n\n Please press \n/add for a new date entry, or \n/edit if you want to change or delete entry.")
        return INITIATION

    cursor.close()
    connection.close()

    in_memory_data['date'] = user_text
    keyboard = []
    for i, key in enumerate(shift_dict):
        if i % 2 == 0:
            keyboard.append([KeyboardButton(text=key)])
        else:
            keyboard[-1].append(KeyboardButton(text=key))

    await update.message.reply_text("Shift type?",
                                    reply_markup=ReplyKeyboardMarkup(
                                        keyboard, one_time_keyboard=True
                                    ))

    return CHECK_SHIFT_TYPE


async def check_shift_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_text = update.message.text
    in_memory_data['shift'] = user_text

    logger.info("Message sent by %s: %s", user.username, user_text)

    date = in_memory_data['date']
    shift = in_memory_data['shift']
    total_earned = float(shift_dict[shift]) * RATE_PER_HOUR

    message = f"Confirming data entry: \n\n Date: {date} \n Shift: {shift} \n ---------- \n Total earned: ${total_earned:.2f}"

    keyboard = [[
        KeyboardButton(text='Yes'),
        KeyboardButton(text='No')
    ]]

    await update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=True
    ))
    return CONFIRM_DATA_ENTRY


async def confirm_data_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_text = update.message.text

    # converting data entry to mysql-recognized date.
    formatted_date = '-'.join(in_memory_data['date'].split('/')[::-1])

    if user_text == 'Yes':

        try:
            connection = pymysql.connect(
                host=os.environ.get('ENDPOINT'),
                port=3306,
                user=os.environ.get('RDS_USERNAME'),
                password=os.environ.get('RDS_PASSWORD'),
                database=os.environ.get('DATABASE')
            )
        except pymysql.Error as e:
            logger.error(e)
            await update.message.reply_text("Could not connect to database, try again later. /start")
            return ConversationHandler.END

        # INCOMPLETE
        cursor = connection.cursor()

        try:
            insert_data_query = 'INSERT INTO Entries (shift_date, shift_type, username) VALUES (%s, %s, %s);'
            data_entry = (formatted_date,
                          in_memory_data['shift'], user.username)
            cursor.execute(insert_data_query, data_entry)
            connection.commit()
        except pymysql.Error as e:
            logger.error(e)
            cursor.close()
            connection.close()
            await update.message.reply_text("Could not insert data into database, try again later. /start")
            return ConversationHandler.END

        cursor.close()
        connection.close()
        await update.message.reply_text("Successfully updated records! Type /start for other actions.")
        return ConversationHandler.END

    if user_text == 'No':
        await update.message.reply_text("Re-enter date of shift in DD/MM/YYYY format.")
        return CHECK_DATE


# EDIT/REMOVE COMMAND LOGIC
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ask for date to check if data exists
    await update.message.reply_text("Date of shift to edit or delete in DD/MM/YYYY (i.e. 01/01/2023).")

    return CHECK_DATE_FOR_EDIT


async def check_date_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_text = update.message.text
    try:
        connection = pymysql.connect(
            host=os.environ.get('ENDPOINT'),
            port=3306,
            user=os.environ.get('RDS_USERNAME'),
            password=os.environ.get('RDS_PASSWORD'),
            database=os.environ.get('DATABASE')
        )
    except pymysql.Error as e:
        logger.error(e)
        await update.message.reply_text("Could not connect to database, try again later. /start")
        return ConversationHandler.END

    cursor = connection.cursor()

    try:
        select_query = "SELECT * FROM Entries WHERE shift_date=%s and username=%s"
        formatted_date = '-'.join(user_text.split('/')[::-1])
        data_entry = (formatted_date, user.username)
        cursor.execute(select_query, data_entry)
        data = cursor.fetchone()

    except pymysql.Error as e:
        logger.error(e)
        cursor.close()
        connection.close()
        await update.message.reply_text("Could not fetch the relevant data, try again later. /start")
        return ConversationHandler.END

    if not data:
        logger.info(f'no data found for date: {user_text}')
        cursor.close()
        connection.close()
        await update.message.reply_text(f"Did not find data records on {user_text}. \n\n Press /add to key in a new entry, or\n /cancel to end the conversation.")
        return INITIATION

    fields = [field_md[0] for field_md in cursor.description]
    result = dict(zip(fields, cursor.fetchone()))

    in_memory_data['date_to_edit'] = user_text
    in_memory_data['id'] = result['id']

    logger.info(f'Data found for date: {user_text}')
    message = f"Data found: \n\n Date: {user_text}\n Shift: {result['shift_type']} \n\n Edit -> Change Shift Type \n Delete - Remove data \n Cancel - Undo Command"
    keyboard = [[
        KeyboardButton(text='Edit'),
        KeyboardButton(text='Delete'),
        KeyboardButton(text='Cancel')
    ]]

    await update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=True
    ))
    cursor.close()
    connection.close()
    return CHECK_EDIT_OR_DELETE


async def check_edit_or_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if user_text == "Cancel":
        logger.info(f'Cancelling data removal...')
        await update.message.reply_text(f"Did not remove data records on {in_memory_data['date_to_edit']}. Press /add to key in a new entry, or /cancel to end the conversation.")
        return INITIATION

    try:
        connection = pymysql.connect(
            host=os.environ.get('ENDPOINT'),
            port=3306,
            user=os.environ.get('RDS_USERNAME'),
            password=os.environ.get('RDS_PASSWORD'),
            database=os.environ.get('DATABASE')
        )
    except pymysql.Error as e:
        logger.error(e)
        await update.message.reply_text("Could not connect to database, try again later. /start")
        return ConversationHandler.END

    cursor = connection.cursor()

    if user_text == "Delete":
        try:
            remove_query = "DELETE FROM Entries WHERE id=%s"
            data_entry = (in_memory_data['id'])
            cursor.execute(remove_query, data_entry)
            connection.commit()

        except pymysql.Error as e:
            logger.error(e)
            cursor.close()
            connection.close()
            await update.message.reply_text("Could not execute DELETE operation, try again later. /start")
            return ConversationHandler.END

        logger.info(
            f"Successfully deleted entry on {in_memory_data['date_to_edit']}")
        cursor.close()
        connection.close()
        await update.message.reply_text(f"Successfully deleted entry on {in_memory_data['date_to_edit']}. \n\n Press /start for a new set of commands.")
        return ConversationHandler.END

    if user_text == "Edit":
        keyboard = []
        for i, key in enumerate(shift_dict):
            if i % 2 == 0:
                keyboard.append([KeyboardButton(text=key)])
            else:
                keyboard[-1].append(KeyboardButton(text=key))

        await update.message.reply_text("New Shift type?",
                                        reply_markup=ReplyKeyboardMarkup(
                                            keyboard, one_time_keyboard=True
                                        ))
        cursor.close()
        connection.close()
        return EDIT_SHIFT_TYPE


async def edit_shift_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        connection = pymysql.connect(
            host=os.environ.get('ENDPOINT'),
            port=3306,
            user=os.environ.get('RDS_USERNAME'),
            password=os.environ.get('RDS_PASSWORD'),
            database=os.environ.get('DATABASE')
        )
    except pymysql.Error as e:
        logger.error(e)
        await update.message.reply_text("Could not connect to database, try again later. /start")
        return ConversationHandler.END

    cursor = connection.cursor()
    try:
        edit_query = "UPDATE Entries SET shift_type=%s WHERE id=%s"
        data_entry = (user_text, in_memory_data['id'])
        cursor.execute(edit_query, data_entry)
        connection.commit()

    except pymysql.Error as e:
        logger.error(e)
        cursor.close()
        connection.close()
        await update.message.reply_text("Could not execute UPDATE operation, try again later. /start")
        return ConversationHandler.END

    logger.info(
        f"Successfully updated shift type to {user_text} on {in_memory_data['date_to_edit']}")
    await update.message.reply_text(f"Successfully updated shift type to {user_text} on {in_memory_data['date_to_edit']}.\n\n Press /start for a new set of commands.", reply_markup=ReplyKeyboardRemove(),)
    cursor.close()
    connection.close()
    return ConversationHandler.END


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    try:
        connection = pymysql.connect(
            host=os.environ.get('ENDPOINT'),
            port=3306,
            user=os.environ.get('RDS_USERNAME'),
            password=os.environ.get('RDS_PASSWORD'),
            database=os.environ.get('DATABASE')
        )
    except pymysql.Error as e:
        logger.error(e)
        await update.message.reply_text("Could not connect to database, try again later. /start")
        return ConversationHandler.END

    cursor = connection.cursor()

    try:
        fetch_data_query = 'SELECT * FROM Entries WHERE username=%s ORDER BY shift_date;'
        data_condition = (user.username)
        cursor.execute(fetch_data_query, data_condition)
        fields = [field_md[0] for field_md in cursor.description]
        results = [dict(zip(fields, row)) for row in cursor.fetchall()]

    except pymysql.Error as e:
        logger.error(e)
        await update.message.reply_text("Could not fetch the relevant data, try again later. /start")
        return ConversationHandler.END

    message = f'Payroll for {user.first_name} (@{user.username}) \n\n'
    month_total = 0
    payroll_cutoff_date = 15

    for i, result in enumerate(results):
        logger.info(result)

        date = result['shift_date']
        shift = result['shift_type']
        total_earned = float(shift_dict[shift]) * RATE_PER_HOUR

        if i == 0:
            message += f"{date}: ${total_earned:.2f} ({shift})\n"
            month_total += total_earned
            continue

        previous_date = results[i-1]['shift_date']
        if previous_date.day <= payroll_cutoff_date and date.day > payroll_cutoff_date or date.month > previous_date.month:
            # start of new payroll
            message += f"\n MONTH TOTAL: ${month_total:.2f} \n ---------- \n\n"
            month_total = 0

        message += f"{date}: ${total_earned:.2f} ({shift})\n"

        month_total += total_earned

        if i == len(results) - 1:
            message += f"\n MONTH TOTAL: ${month_total:.2f}"

    message += "\n\n Press /start for a new set of commands."
    await update.message.reply_text(message)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info('User pressed cancel.')
    await update.message.reply_text("Bye! Press /start for another command.")
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that command.")


def main():
    application = ApplicationBuilder().token(os.environ.get('BOT_TOKEN')).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INITIATION: [CommandHandler('add', add), CommandHandler('edit', edit), CommandHandler('summary', summary)],
            CHECK_DATE: [MessageHandler(filters.TEXT, check_date)],
            CHECK_SHIFT_TYPE: [MessageHandler(filters.TEXT, check_shift_type)],
            CONFIRM_DATA_ENTRY: [MessageHandler(
                filters.TEXT, confirm_data_entry)],
            CHECK_DATE_FOR_EDIT: [MessageHandler(filters.TEXT, check_date_edit)],
            CHECK_EDIT_OR_DELETE: [MessageHandler(filters.TEXT, check_edit_or_delete)],
            EDIT_SHIFT_TYPE: [MessageHandler(filters.TEXT, edit_shift_type)],
        },
        fallbacks=[CommandHandler("cancel", cancel),
                   MessageHandler(filters.COMMAND, unknown)]
    )

    application.add_handler(conv_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()


# async def check_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user = update.message.from_user
#     user_text = update.message.text

#     logger.info("Message sent by %s: %s", user.username, user_text)

#     time_format = '%H%M'
#     try:
#         datetime.strptime(user_text, time_format)
#     except ValueError:
#         await update.message.reply_text('Error in recognising time. Please ensure format is in 24-HOUR format.')
#         return CHECK_START_TIME

#     await update.message.reply_text("Ending time in 24-HOUR format (i.e. 2000).")
#     return CHECK_END_TIME


# async def check_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user = update.message.from_user
#     user_text = update.message.text

#     logger.info("Message sent by %s: %s", user.username, user_text)

#     time_format = '%H%M'
#     try:
#         datetime.strptime(user_text, time_format)
#     except ValueError:
#         await update.message.reply_text('Error in recognising time. Please ensure format is in 24-HOUR format.')
#         return CHECK_END_TIME


#     await update.message.reply_text("Total break duration in hours. (i.e. 1, 2...)")
#     return CHECK_BREAK_DURATION

# async def check_break_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user = update.message.from_user
#     user_text = update.message.text

#     if

#     logger.info("Message sent by %s: %s", user.username, update.message.text)

#     await update.message.reply_text(f"{user.username}, thanks")
#     return ConversationHandler.END
