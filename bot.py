import os
import logging
from datetime import datetime

import json


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
REMOVE_BUTTON_TEXT = '/remove'
EDIT_BUTTON_TEXT = '/edit'
SUMMARY_BUTTON_TEXT = '/summary'

INITIATION, CHECK_DATE, CHECK_SHIFT_TYPE, CONFIRM_DATA_ENTRY = range(4)


RATE_PER_HOUR = 15
AUTHORIZED_USERNAMES = ['terrykms', 'q000xd']

# in-memory usage before adding into a database
added_shift = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if user.username not in AUTHORIZED_USERNAMES:
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    keyboard = [
        [
            KeyboardButton(text=ADD_BUTTON_TEXT),
            KeyboardButton(text=REMOVE_BUTTON_TEXT),
        ],
        [
            KeyboardButton(text=EDIT_BUTTON_TEXT),
            KeyboardButton(text=SUMMARY_BUTTON_TEXT),
        ],
    ]

    await update.message.reply_text(
        "Welcome! What do you want to do?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True
        ))
    return INITIATION


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
        res = False
        await update.message.reply_text('Error in recognising date. Please ensure format is in DD/MM/YYYY.')
        return CHECK_DATE

    added_shift['date'] = user_text

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
    added_shift['shift'] = user_text

    logger.info("Message sent by %s: %s", user.username, user_text)

    date = added_shift['date']
    shift = added_shift['shift']
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

    if user.username == 'terrykms':
        data_path = 'test_data.json'
    else:
        data_path = 'data.json'

    if user_text == 'Yes':
        with open(data_path, 'r+') as file:
            file_data = json.load(file)
            if "records" in file_data:
                file_data["records"].append(
                    {
                        'date': added_shift['date'],
                        'shift': added_shift['shift']
                    }
                )
            else:
                file_data["records"] = [{
                    'date': added_shift['date'],
                    'shift': added_shift['shift']
                }]
            file.seek(0)
            # convert back to json.
            json.dump(file_data, file, indent=4)
        await update.message.reply_text("Successfully updated records!")
        return ConversationHandler.END
    if user_text == 'No':
        await update.message.reply_text("Re-enter date of shift in DD/MM/YYYY format.")
        return CHECK_DATE


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if user.username == 'terrykms':
        data_path = 'test_data.json'
    else:
        data_path = 'data.json'

    with open(data_path, 'r') as file:
        file_data = json.load(file)
        records = file_data["records"]

    def get_date(record):
        return datetime.strptime(record['date'], "%d/%m/%Y")

    sorted_records = sorted(records, key=get_date)

    message = ''
    month_total = 0
    payroll_cutoff_date = 15

    for i, record in enumerate(sorted_records):
        logger.info(record)

        date = record['date']
        shift = record['shift']
        total_earned = float(shift_dict[shift]) * RATE_PER_HOUR

        if i == 0:
            message += f"{date}: ${total_earned:.2f} ({shift})\n"
            month_total += total_earned
            continue

        previous_date = sorted_records[i-1]['date']
        if int(previous_date.split('/')[0]) <= payroll_cutoff_date and (int(date.split('/')[0]) > payroll_cutoff_date or int(date.split('/')[1]) > int(previous_date.split('/')[1])):
            # start of new payroll
            message += f"\n MONTH TOTAL: ${month_total:.2f} \n ---------- \n\n"
            month_total = 0

        message += f"{date}: ${total_earned:.2f} ({shift})\n"

        month_total += total_earned

        if i == len(sorted_records) - 1:
            message += f"\n MONTH TOTAL: ${month_total:.2f}"

    await update.message.reply_text(message)

    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that command.")


def main():
    application = ApplicationBuilder().token(os.environ.get('BOT_TOKEN')).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INITIATION: [CommandHandler('add', add), CommandHandler('summary', summary)],
            CHECK_DATE: [MessageHandler(filters.TEXT, check_date)],
            CHECK_SHIFT_TYPE: [MessageHandler(filters.TEXT, check_shift_type)],
            CONFIRM_DATA_ENTRY: [MessageHandler(
                filters.TEXT, confirm_data_entry)]
        },
        fallbacks=[MessageHandler(filters.COMMAND, unknown)]
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
