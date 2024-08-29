from classes import Task, Calendar

import json

from datetime import time, datetime, timedelta
from threading import Thread
from time import sleep

def parse_time(string):
    index = string.find(":")

    hour = int(string[:index])
    minute = int(string[index+1:])

    return time(hour=hour,minute=minute)

with open("config.json", "r") as f:
    data = json.loads(f.read())
    log_on = parse_time(data["log_on"])
    log_off = parse_time(data["log_off"])

calendar = Calendar(log_on, log_off)
calendar.start()

refresh_rate = 5

# we have our calendar, deal with a refresh loop

def refresh():
    while True:
        sleep(refresh_rate)
        calendar.reload_tasks() # refresh the calendar every minute, checking for new events which would interrupt the current tasks

def int_input(string):
    valid = False
    while valid is False:
        value = input(string)

        try:
            value = int(value)
            valid = True
        except:
            pass
    
    return value

def quit_main():
    quit()

def add_task_by_CLI():
    while True:
        try:
            print("=== TASK INPUT ===")
            task_name = input("Task name: ")
            task_desc = input("Task description: ")
            task_time = int_input("Task minutes: ")
            task_due = input("Task due date dd/mm/yy: ") # implement this next

            calendar.insert_task(Task(task_name, desc=task_desc, minutes=task_time))
        except:
            print("exception raised")
            quit_main()


calendar_loop = Thread(target=refresh)
calendar_loop.start()

input_loop = Thread(target=add_task_by_CLI)
input_loop.start()

calendar_loop.join()
input_loop.join()