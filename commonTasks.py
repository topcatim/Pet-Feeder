import sqlite3
import configparser
import time
from Adafruit_CharLCD import Adafruit_CharLCD
import datetime
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_formatting import *
import RPi.GPIO as GPIO

# Find config file
dir = os.path.dirname(__file__)  # os.getcwd()
configFilePath = os.path.abspath(os.path.join(dir, "app.cfg"))
configParser = configparser.RawConfigParser()
configParser.read(configFilePath)

# Read in config variables
DB = str(configParser.get('feederConfig', 'Database_Location'))
hopperGPIO = str(configParser.get('feederConfig', 'Hopper_GPIO_Pin'))
hopperTime = str(configParser.get('feederConfig', 'Hopper_Spin_Time'))
latestXNumberFeedTimesValue = str(configParser.get('feederConfig', 'Number_Feed_Times_To_Display'))
upcomingXNumberFeedTimesValue = str(configParser.get('feederConfig', 'Number_Scheduled_Feed_Times_To_Display'))
spreadsheetFileName = str(configParser.get('feederConfig', 'Spreadsheet_File_Name'))


def connect_db():
    try:
        """Connects to the specific database."""
        rv = sqlite3.connect(DB)
        return rv
    except Exception as e:
        return e


def db_insert_feedtime(dateObject, complete):
    try:
        """Connects to the specific database."""
        datetime = dateObject.strftime('%Y-%m-%d %H:%M:%S')
        con = connect_db()
        cur = con.execute('''insert into feedtimes (feeddate,feedtype) values (?,?)''', [str(datetime), int(complete)])
        con.commit()
        cur.close()
        con.close()

        return 'ok'
    except Exception as e:
        return e


def db_get_last_feedtimes(numberToGet):
    try:
        con = connect_db()
        cur = con.execute(''' select feeddate,description
                                from feedtimes ft
                                join feedtypes fty on ft.feedtype=fty.feedtype
                                where ft.feedtype in (1,2,3,4,6)
                                order by feeddate desc
                                limit ?''', [str(numberToGet), ])
        LastFeedingTimes = cur.fetchall()
        cur.close()
        con.close()
        return LastFeedingTimes
    except Exception as e:
        return e


def db_get_scheduled_feedtimes(numberToGet):
    try:
        con = connect_db()
        cur = con.execute(''' select feeddate,description,ft.feedtype
                                from feedtimes ft
                                join feedtypes fty on ft.feedtype=fty.feedtype
                                where ft.feedtype in (0,5)
                                order by ft.feedtype desc,ft.feeddate desc
                            limit ?''', [str(numberToGet), ])
        LastFeedingTimes = cur.fetchall()
        cur.close()
        con.close()
        return LastFeedingTimes
    except Exception as e:
        return e


def db_get_specific_scheduled_feedtime_by_date(date):
    try:
        con = connect_db()
        cur = con.execute(''' select feedid, feeddate, feedtype
                                from feedtimes ft
                                where feedtype in (3)
                                and feeddate=?
                            ''', [str(date), ])
        LastFeedingTimes = cur.fetchone()
        cur.close()
        con.close()
        return LastFeedingTimes
    except Exception as e:
        return e


def get_last_feedtime_string():
    try:
        # Get last date from database
        lastFeedDateCursor = db_get_last_feedtimes(1)
        lastFeedDateString = lastFeedDateCursor[0][0]
        lastFeedDateObject = datetime.datetime.strptime(lastFeedDateString, "%Y-%m-%d %H:%M:%S")

        yesterdayDateObject = datetime.datetime.now() - datetime.timedelta(days=1)
        nowDateObject = datetime.datetime.now()
        verbiageString = ''
        finalMessage = ''
        if lastFeedDateObject.year == nowDateObject.year and lastFeedDateObject.month == nowDateObject.month and lastFeedDateObject.day == nowDateObject.day:
            verbiageString = 'Today' + ' ' + lastFeedDateObject.strftime(
                "%I:%M %p")  # +str('%02d' % lastFeedDateObject.hour)+':'+str('%02d' % lastFeedDateObject.minute)
        elif lastFeedDateObject.year == yesterdayDateObject.year and lastFeedDateObject.month == yesterdayDateObject.month and lastFeedDateObject.day == yesterdayDateObject.day:
            verbiageString = 'Yesterday' + ' ' + lastFeedDateObject.strftime("%I:%M %p").replace(' ',
                                                                                                 '')  # str('%02d' % lastFeedDateObject.hour)+':'+str('%02d' % lastFeedDateObject.minute)
        else:
            verbiageString = str(abs((
                                             nowDateObject - lastFeedDateObject).days)) + ' days ago!'  # str('%02d' % lastFeedDateObject.month)+'-'+str('%02d' % lastFeedDateObject.day)+'-'+str(lastFeedDateObject.year)[2:]+' '+str('%02d' % lastFeedDateObject.hour)+':'+str('%02d' % lastFeedDateObject.minute)

        finalMessage = 'Last feed time:\n' + verbiageString
        return finalMessage
    except Exception as e:
        return e


def spin_hopper(pin, duration):
    try:
        pin = int(pin)
        duration = float(duration)
        GPIO.setwarnings(False)
        GPIO.cleanup(pin)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup(pin)

        return 'ok'
    except Exception as e:
        return 'ok'  # e

def spin_treathopper(pin, duration):
    try:
        pin = int(pin)
        duration = float(duration)
        GPIO.setwarnings(False)
        GPIO.cleanup(pin)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup(pin)

        return 'ok'
    except Exception as e:
        return 'ok'  # e

def print_to_LCDScreen(message):
    try:
        lcd = Adafruit_CharLCD()
        lcd.begin(16, 2)
        for x in range(0, 16):
            for y in range(0, 2):
                lcd.setCursor(x, y)
                lcd.message('>')
                time.sleep(.025)
        lcd.noDisplay()
        lcd.clear()
        lcd.message(str(message))
        for x in range(0, 16):
            lcd.DisplayLeft()
        lcd.display()
        for x in range(0, 16):
            lcd.scrollDisplayRight()
            time.sleep(.05)

        return 'ok'
    except Exception as e:
        return 'ok'  # e


def spreadsheetFeed():
    dateNowObject = datetime.datetime.now()
    spin = spin_hopper(hopperGPIO, hopperTime)

    if spin != 'ok':
        return 'Error! No feed activated! Error Message: ' + str(spin)

    dbInsert = db_insert_feedtime(dateNowObject, 6)  # FeedType 6=Spreadsheet
    if dbInsert != 'ok':
        return 'Warning. Database did not update. Message returned: ' + str(dbInsert)

    return 'Feed success!'


def update_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('/var/www/feeder/feeder/googleapisecret.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open(spreadsheetFileName).sheet1

    # example calls
    # times = sheet.get_all_records()
    # feedingNeeded = sheet.row_values(1)
    # sheet.update_cell(2,4,"false")
    triggerFeeding = sheet.cell(1, 2).value  # Check if box is checked to do a feeding
    if triggerFeeding == 'TRUE':
        output = spreadsheetFeed()  # do feed
        sheet.update_cell(1, 2, "FALSE")  # Set box back to false to allow another feeding to occur
        if str(output) != 'Feed success!':
            return "Error updating sheet. Error message: " + str(output)

    # clear out old data
    cell_list = sheet.range('A4:A25')
    for cell in cell_list:
        cell.value = ''
    sheet.update_cells(cell_list)

    cell_list = sheet.range('B4:B25')
    for cell in cell_list:
        cell.value = ''
    sheet.update_cells(cell_list)

    # Update latest feed times to spreadsheet
    latestXNumberFeedTimes = db_get_last_feedtimes(latestXNumberFeedTimesValue)
    rowCounter = 4  # Row 1-3 has column titles, dont want to overwrite
    finalFeedTimeList = []
    for time in latestXNumberFeedTimes:
        time = list(time)
        dateobject = datetime.datetime.strptime(time[0], '%Y-%m-%d %H:%M:%S')
        time[0] = dateobject.strftime("%m-%d-%y %I:%M %p")
        time = tuple(time)
        # print (time[0])
        # print(time[1])
        sheet.update_cell(rowCounter, 1, time[0])
        sheet.update_cell(rowCounter, 2, time[1])
        rowCounter += 1

    # Update latest scheduled feedtimes to spreadsheet
    # Get position of title for schedeuled feeds
    scheduledFeedingTitleRowValue = 3 + int(
        latestXNumberFeedTimesValue) + 2  # Start Below 3 frozen columns+latest number of feedings+padding
    sheet.update_cell(scheduledFeedingTitleRowValue, 1, "Scheduled Feed Times")

    # Bold it
    fmt = cellFormat(
        backgroundColor=color(1, .7, 1),  # RGD value / 255
        textFormat=textFormat(bold=True),  # , foregroundColor=color(1, 0, 1)),
        horizontalAlignment='LEFT'
    )
    rangeValue = "A" + str(scheduledFeedingTitleRowValue) + ":" + "A" + str(scheduledFeedingTitleRowValue)
    format_cell_range(sheet, str(rangeValue), fmt)  # Scheduled feed title
    format_cell_range(sheet, "A3:B3", fmt)  # Latest time title
    fmt1 = cellFormat(
        backgroundColor=color(.85, .96, 1),  # RGD value / 255
        textFormat=textFormat(bold=True),  # , foregroundColor=color(1, 0, 1)),
        horizontalAlignment='LEFT'
    )
    format_cell_range(sheet, "A1:B1", fmt1)  # Checkbox

    scheduledFeedingTitleRowValue = scheduledFeedingTitleRowValue + 1  # Start below title bar
    scheduledFeedtimes = db_get_scheduled_feedtimes(upcomingXNumberFeedTimesValue)
    finalUpcomingFeedTimeList = []
    for scheduledFeedTime in scheduledFeedtimes:
        scheduledFeedTime = list(scheduledFeedTime)
        dateobject = datetime.datetime.strptime(scheduledFeedTime[0], '%Y-%m-%d %H:%M:%S')
        finalString = dateobject.strftime("%m-%d-%y %I:%M %p")

        # 1900-01-01 default placeholder date for daily reoccuring feeds
        if str(scheduledFeedTime[2]) == '5':  # Repeated schedule. Strip off Date
            finalString = finalString.replace("01-01-00", "Daily at")
        # print (finalString)
        sheet.update_cell(scheduledFeedingTitleRowValue, 1, finalString)
        scheduledFeedingTitleRowValue += 1
    sheet.update_cell(1, 3, "")  # Clear out any errors
    fmt2 = cellFormat(
        backgroundColor=color(1, 1, 1),  # RGD value / 255
        textFormat=textFormat(bold=True),  # , foregroundColor=color(1, 0, 1)),
        horizontalAlignment='LEFT'
    )
    format_cell_range(sheet, "C1:C1", fmt2)  # Checkbox

    return ('spreadsheet updated')
