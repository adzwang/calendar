from enum import Enum
import json

from datetime import datetime, timedelta, time

from gcsa.event import Event
from gcsa.google_calendar import GoogleCalendar

google_account = "" # simply a working email which is organised by oauth
with open("config.json", "r") as f:
    google_account = json.loads(f.read())["email"]

tag = "#auto"

class Priority(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2

class Task:
    def __init__(self, time, priority, due, name, desc):
        self.time = time # this is time required
        self.priority = priority # enum of low, medium, high
        self.due = due # iso timestamp of the due time
        self.name = name
        self.desc = desc

class Event:
    def __init__(self, time, starts, name, desc):
        self.time = time
        self.starts = starts
        self.name = name
        self.desc = desc

class DailyTask:
    def __init__(self, time, name, desc):
        self.time = time
        self.name = name
        self.desc = desc

class Calendar:
    def __init__(self, active_time, inactive_time):
        self.tasks_by_due = []

        self.link = GoogleCalendar(google_account) # link to google

        self.log_on = active_time # this should be a datetime object of the time when you start being active
        self.log_off = inactive_time

        self.events = self.get_events()
        print(self.events)
    
    def get_events(self):
        events = []

        for event in self.link:
            if not (event.description is not None and event.description.endswith(tag)):
                events.append(event)
        
        return events
    
    def get_tasks(self):
        events = []

        for event in self.link:
            if event.description and event.description.endswith(tag): # all the descriptions must end with this
                events.append(event)
        
        return events

    def insert_task(self, task):
        for i,v in enumerate(self.by_dtasks_by_dueue):
            if v.due > task.due:
                self.tasks_by_due.insert(i,task)
                break

    def organise_calendar(self):
        """
        Creates a valid new calendar, organising tasks by due date and around events.
        
        To be implemented in order of priority:
        1) (Assuming all tasks are assignable easily in the order by due date) lay out all tasks by due date.
        2) Lay out all tasks by due date if tasks can be switched around and still give a valid layout. (ex: short task taking up space on day 2 when day 1 has a gap free for it)
        3) If the layout isn't possible and you're swamped, extend log_off time by increments of 30 minutes (includes log_off time being technically before log_on time, if log_off is 2am and log_on is 7am)
        """
        # let's find the first active moment that's a multiple of 15 minutes after when this is being run

        now = datetime.now() 
        fifteen_minutes = timedelta(minutes=15)

        current_minute = now.minute
        if current_minute % 15 != 0:
            # i couldn't think of a better way to do this
            for i in range(15):
                current_minute -= 1
                if current_minute % 15 == 0:
                    break
        
        now = now.replace(minute=current_minute,second=0,microsecond=0)
        now += fifteen_minutes # this is now the first 15 minute starter

        now_time = now.time()

        if now_time < self.log_on:
            # this is not a valid time to set a task to, find the first valid time

            while now_time < self.log_on:
                # continue adding 15 minutes until it is a valid time
                now += fifteen_minutes
                now_time = now.time()
        
        # now_time is now a valid time to try the place to calendar logic
        
        starting_time = now.replace(hour=now_time.hour, minute=now_time.minute) # we know the seconds have to be 0
        print(starting_time)

# cheeky little test case

c = Calendar(time(hour=7), time(hour=23))

c.organise_calendar()