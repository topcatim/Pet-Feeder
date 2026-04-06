#!/var/www/feeder/bin/python
import sys

sys.path.extend(['/var/www/feeder/feeder'])
import logging.handlers
import argparse
import time
import signal
import commonTasks
import configparser
import os
import datetime
from pathlib import Path

# Find config file
dir = os.path.dirname(__file__)  # os.getcwd()
configFilePath = os.path.abspath(os.path.join(dir, "app.cfg"))
configParser = configparser.RawConfigParser()
configParser.read(configFilePath)

# Read in config variables
secondDelay = configParser.get('feederConfig', 'Seconds_Delay_Between_Schedule_Checks')
LOG_TimeService_FILENAME = configParser.get('feederConfig', 'Log_TimeService_Filename')
hopperGPIO = str(configParser.get('feederConfig', 'Hopper_GPIO_Pin'))
hopperTime = str(configParser.get('feederConfig', 'Hopper_Spin_Time'))
motionVideoDirPath = str(configParser.get('feederConfig', 'Motion_Video_Dir_Path'))
nowMinusXDays = str(configParser.get('feederConfig', 'Number_Days_Of_Videos_To_Keep'))

# Define and parse command line arguments
parser = argparse.ArgumentParser(description="My simple Python service")
parser.add_argument("-l", "--log", help="file to write log to (default '" + LOG_TimeService_FILENAME + "')")

# If the log file is specified on the command line then override the default
args = parser.parse_args()
if args.log:
    LOG_FILENAME = args.log

# Configure logging to log to a file, making a new file at midnight and keeping the last 3 day's data
# Give the logger a unique name (good practice)
logger = logging.getLogger(__name__)
# Set the log level to LOG_LEVEL
logger.setLevel(logging.INFO)  # Could be e.g. "DEBUG" or "WARNING")
# Make a handler that writes to a file, making a new file at midnight and keeping 3 backups
handler = logging.handlers.TimedRotatingFileHandler(LOG_TimeService_FILENAME, when="midnight", backupCount=3)
# Format each log message like this
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
# Attach the formatter to the handler
handler.setFormatter(formatter)
# Attach the handler to the logger
logger.addHandler(handler)


# Make a class we can use to capture stdout and sterr in the log
class MyLogger(object):
    def __init__(self, logger, level):
        """Needs a logger and a logger level."""
        self.logger = logger
        self.level = level

    def write(self, message):
        # Only log if there is a message (not just a new line)
        if message.rstrip() != "":
            self.logger.log(self.level, message.rstrip())


# Replace stdout with logging to file at INFO level
sys.stdout = MyLogger(logger, logging.INFO)
# Replace stderr with logging to file at ERROR level
sys.stderr = MyLogger(logger, logging.ERROR)


class GracefulKiller:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True


print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
print("Starting up")
print("Time delay default is: " + str(secondDelay) + " seconds")
print("Create Gracekiller class")
killer = GracefulKiller()
print("End Start up. Starting while loop")
print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
while True:
    print("--------------------------------------------------------------")

    screenMessage = commonTasks.get_last_feedtime_string()
    # print "Screen message to print: " + str(screenMessage)
    updatescreen = commonTasks.print_to_LCDScreen(str(screenMessage))
    # print "Message display return status: " + str(updatescreen)

    # print "Begin checking if scheduled events."
    upcomingXNumberFeedTimes = commonTasks.db_get_scheduled_feedtimes(50)
    for x in upcomingXNumberFeedTimes:
        if str(x[2]) == '5':
            print('Repeating scheduled time ' + str(x[0]))
            present = datetime.datetime.now()  # + datetime.timedelta(hours=24)
            preValue = datetime.datetime.strptime(x[0], '%Y-%m-%d %H:%M:%S')
            # Build current date value with scheduled time
            value = datetime.datetime(present.year, present.month, present.day, preValue.hour, preValue.minute)
            c = present - value
            d = divmod(c.days * 86400 + c.seconds, 60)

            # print 'After scheduled time run once for today will keep running unless have a check in place'
            scheduledForToday = commonTasks.db_get_specific_scheduled_feedtime_by_date(value)
            if scheduledForToday:
                print('Already ran for today, skip')
                d = (0, 0)
        else:
            print('One off scheduled time ' + str(x[0]))
            present = datetime.datetime.now()
            value = datetime.datetime.strptime(x[0], '%Y-%m-%d %H:%M:%S')
            c = present - value
            d = divmod(c.days * 86400 + c.seconds, 60)
            if d[0] < 1:
                print('Not past due yet')

        # print present, value, d[0],x

        if d[0] > 1:
            print('Scheduled record found past due')
            print("Current time: " + str(present))
            print("Scheduled time: " + str(value))
            print("Minutes difference: " + str(d[0]))

            spin = commonTasks.spin_hopper(hopperGPIO, hopperTime)
            if spin != 'ok':
                print('Error! Feeder not activated! Error Message: ' + str(spin))

            dbInsert = commonTasks.db_insert_feedtime(value, 3)
            if dbInsert != 'ok':
                print('Warning. Database did not update: ' + str(dbInsert))

            updatescreen = commonTasks.print_to_LCDScreen(commonTasks.get_last_feedtime_string())
            if updatescreen != 'ok':
                print('Warning. Screen feedtime did not update: ' + str(updatescreen))

            print('Auto feed success')

            # Delete one off scheduled feeds now. Keep reoccuring feed schedules in DB.
            # Reoccuring daily feed times have date 1900-01-01 as placeholder in DB
            if str(x[2]) == '5':
                # Do not delete as scheduled will therefore be deleted. Deleted scheduled times through UI.
                print('Scheduled date. Do not delete')

            else:
                # Not a scheduled time. Can delete
                # Delete old scheduled records from DB
                con = commonTasks.connect_db()
                cur = con.execute("""delete from feedtimes where feeddate=? and feedtype in (0)""", [str(x[0]), ])
                con.commit()
                cur.close()
                con.close()
                print('Deleted old record from DB')

            break

    # Remove video files older then specified days
    now = time.time()
    nowMinusSpecifiedDays = now - int(nowMinusXDays) * 86400
    # Loop and remove
    for f in os.listdir(motionVideoDirPath):
        if f != '.gitkeep':
            f = os.path.join(motionVideoDirPath, f)
            if os.stat(f).st_mtime < nowMinusSpecifiedDays:
                if os.path.isfile(f):
                    os.remove(os.path.join(motionVideoDirPath, f))
                    print('Removed old video file: ' + str(f))

    # Update spreadsheet file if exists
    my_file = Path("/var/www/feeder/feeder/googleapisecret.json")
    if my_file.is_file():
        output = commonTasks.update_spreadsheet()
        print(output)

    # Wait specified time before starting again
    time.sleep(float(secondDelay))
    if killer.kill_now: break

print("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
print("End of the program. Killed gracefully")
print("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
