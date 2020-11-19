from datetime import datetime
from datetime import timedelta

# Class representing a flight listing that a user has requested. It's created
# when the listing is successfully created and persists until its timer expires 
# or it's manually closed. 
class Flight: 
    
    # Constructor for the Flight class
    # Arguments: 
    #   userID: The discord.py User ID for the user who requested the flight
    #   playerName: The AC player name the user provided 
    #   island: The AC island name the user provided 
    #   end_time: The time the flight should be removed
    #   code: The Dodo Code(tm) for the flight
    #   extra: Any additional information the user wants to provide about their island
    def __init__(self, userID, playerName, island, end_time, code, extra): 
        self.userID = userID
        self.playerName = playerName
        self.island = island
        self.end_time = end_time
        self.code = code
        self.extra = extra
        self.messageID = None
        self.duration = None
        
    # Checks if the requested duration for the flight listing has been reached
    # and returns True if it has, False if it hasn't. 
    def checkExpired(self): 
        if datetime.utcnow() > self.end_time: 
            return True
        else: 
            return False
            
    # Sets the message member variable in this flight object
    def setMessageID(self, messageID): 
        self.messageID = messageID
        
    # Returns the duration of the listing as timedelta object
    def getDuration(self): 
        if self.duration is not None: 
            return self.duration
        elif datetime.utcnow() < self.end_time:
            return self.end_time - datetime.utcnow()
        else: 
            return timedelta(0)
        
    # Set the duration for this listing
    def setDuration(self, duration): 
        self.duration = duration
    
    # Use the information in this object to create a string that will be 
    # used in the listing message for this flight
    def generateMessage(self): 
        durationString = ""
        
        currentDuration = self.getDuration()
        days = currentDuration.days
        seconds = currentDuration.seconds
        
        # calculate hours and minutes from seconds
        hours = seconds//60//60
        minutes = (seconds - (hours * 3600))//60
        
        dayString = ""
        hourString = ""
        minuteString = "" 
        
        dayFlag = False
        hourFlag = False
        minuteFlag = False
        
        # Determine which time fields we have and build their strings
        if days > 0: 
            dayFlag = True
            
            if days == 1: 
                dayString = str(days) +  " day" 
            else: 
                dayString = str(days) + " days"
        
        if hours > 0: 
            hourFlag = True
            
            if hours == 1: 
                hourString = str(hours) +  " hour" 
            else: 
                hourString = str(hours) + " hours"
        
        if minutes > 0: 
            minuteFlag = True
            
            if minutes == 1: 
                minuteString = str(minutes) +  " minute" 
            else: 
                minuteString = str(minutes) + " minutes"
        
        # Build the duration string based on what time fields we have
        if dayFlag and hourFlag and minuteFlag: 
            durationString = dayString + ", " + hourString + " and " + minuteString
        elif dayFlag and hourFlag: 
            durationString = dayString + " and " + hourString
        elif dayFlag and minuteFlag: 
            durationString = dayString + " and " + minuteString
        elif hourFlag and minuteFlag: 
            durationString = hourString + " and " + minuteString
        elif dayFlag: 
            durationString = dayString
        elif hourFlag: 
            durationString = hourString
        elif minuteFlag: 
            durationString = minuteString
        else: 
            durationString = "0 hours"
        
        # Build the message
        returnMessage =  "Flights are now available to " + self.island + "!\n"
        returnMessage += "Host: " + self.playerName + " (<@" + str(self.userID) + ">)\n"
        returnMessage += "Dodo Code™: " + self.code + "\n"
        returnMessage += "This flight will be available for " + durationString + " from time of posting. \n"

        
        if self.extra.lower() != "none": 
            returnMessage += self.extra
                
        return returnMessage