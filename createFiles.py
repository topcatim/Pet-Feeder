#!/var/www/feeder/bin/python
import sys

sys.path.extend(['/var/www/feeder/feeder'])
import subprocess
import sqlite3
import os
#from werkzeug import generate_password_hash
from werkzeug.security import generate_password_hash

import datetime

try:
    dbPath = '/var/www/feeder/feeder/feeder.db'
    appCFGPath = '/var/www/feeder/feeder/app.cfg'

    if os.path.isfile(dbPath):
        print('DB already exists. To create again first delete current copy')
    else:
        print('Creating DB. Please wait.')
        con = sqlite3.connect(dbPath)
        cur = con.execute(
            """CREATE TABLE feedtimes (feedid integer primary key autoincrement,feeddate string,feedtype integer);""")
        cur = con.execute("""CREATE TABLE feedtypes (feedtype integer primary key,description string);""")
        cur = con.execute(
            """CREATE TABLE loginLog (loginLogID integer primary key autoincrement,loginName text null,loginPW text null,loginDate text null);""")
        cur = con.execute(
            """CREATE TABLE user (user_id integer primary key autoincrement,username text not null,email text not null,pw_hash text not null);""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("0","Scheduled To Run");""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("1","Button");""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("2","Web Feed");""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("3","Scheduled");""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("4","Smart Home");""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("5","Repeat Schedule To Run");""")
        cur = con.execute("""insert into feedtypes (feedtype,description) values ("6","Spreadsheet");""")
        cur = con.execute('''insert into user (username,email,pw_hash) values (?,?,?)''',
                          ['admin', '', generate_password_hash('ChangeMe!')])
        nowDate = datetime.datetime.now()
        currentTimeString = nowDate.strftime("%Y-%m-%d %H:%M:%S")
        cur = con.execute('''insert into feedtimes (feeddate,feedtype) values (?,1)''', [currentTimeString, ])
        con.commit()
        cur.close()
        con.close()
        print('DB created')

    if os.path.isfile(appCFGPath):
        print('app.cfg already exists. To create again first delete current copy')
    else:
        print('Creating app.cfg. Please wait.')
        f = open(appCFGPath, "w+")

        f.write("""[feederConfig]
Database_Location=/var/www/feeder/feeder/feeder.db
Feed_Button_GPIO_Pin=12
Hopper_GPIO_Pin=11
Hopper_Spin_Time=0.6
Log_ButtonService_Filename=/var/www/feeder/feeder/logs/feederButtonService.log
Log_TimeService_Filename=/var/www/feeder/feeder/logs/feederTimeService.log
Motion_Video_Dir_Path=/var/www/feeder/feeder/static/video
Motion_Camera_Site_Address=http://yourRemoteAddress.duckdns.org:8081
Number_Days_Of_Videos_To_Keep=1
Number_Feed_Times_To_Display=5
Number_Scheduled_Feed_Times_To_Display=5
Number_Videos_To_Display=100
Seconds_Delay_After_Button_Push=3
Seconds_Delay_Between_Schedule_Checks=300
Secretkey=SUPER_SECRET_KEY
Spreadsheet_File_Name=PetFeederTimes
""")

        f.close()
        # os.chmod(appCFGPath, 0o777)
        print('app.cfg created')


    process = subprocess.Popen(["sudo", "chmod", "777", "-R", "/var/www/feeder"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    os.chmod(dbPath, 0o777)
    print('permissions set')

except Exception as e:
    print('Error: ' + str(e))
