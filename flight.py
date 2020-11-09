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
        else:
            return self.end_time - datetime.utcnow()
        
    # Set the duration for this listing
    def setDuration(self, duration): 
        self.duration = duration
    
    # Use the information in this object to create a string that will be 
    # used in the listing message for this flight
    def generateMessage(self): 
        durationList = str(self.getDuration()).split(':')
        hourFlag = False
        
        durationString = ""
        
        if int(durationList[0]) == 1: 
            hourFlag = True
            durationString = durationString + durationList[0] + " hour "
        elif int(durationList[0]) > 1: 
            durationString = durationString + durationList[0] + " hours "
        
        if int(durationList[1]) == 1: 
            if hourFlag: 
                durationString = durationString + "and " + durationList[1] + " minute "
            else: 
                durationString = durationString + durationList[1] + " minute "
        elif int(durationList[1]) > 1: 
            if hourFlag: 
                durationString = durationString + "and " + durationList[1] + " minutes "
            else: 
                durationString = durationString + durationList[1] + " minutes "
        
        
        returnMessage =  "Flights are now available to " + self.island + "!\n"
        returnMessage += "Host: " + self.playerName + " (<@" + str(self.userID) + ">)\n"
        returnMessage += "Dodo Code™: " + self.code + "\n"
        returnMessage += "This flight will be available for " + durationString + "from time of posting\n"

        
        if self.extra.lower() != "none": 
            returnMessage += self.extra
                
        return returnMessage