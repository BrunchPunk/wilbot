import discord
from datetime import datetime

# Class representing a flight listing that a user has requested. It's created
# when the listing is successfully created and persists until its timer expires 
# or it's manually closed. 
class Flight: 
    
    # Constructor for the Flight class
    # Arguments: 
    #   owner: The discord.py User object for the user who requested the flight
    #   name: The AC player name the user provided 
    #   island: The AC island name the user provided 
    #   end_time: The time the flight should be removed
    #   code: The Dodo Code(tm) for the flight
    #   extra: Any additional information the user wants to provide about their island
    #   message: The discord.py Message object for the listing that was made
    def __init__(self, owner, name, island, duration, end_time, code, extra): 
        self.owner = owner
        self.name = name
        self.island = island
        self.duration = duration
        self.end_time = end_time
        self.code = code
        self.extra = extra
        self.message = None
        
    # Checks if the requested duration for the flight listing has been reached
    # and returns True if it has, False if it hasn't. 
    def checkExpired(self): 
        if datetime.utcnow() > self.end_time: 
            return True
        else: 
            return False
            
    # Sets the message member variable in this flight object
    def setMessage(self, newMessage): 
        self.message = newMessage
    
    # Use the information in this object to create a string that will be 
    # used in the listing message for this flight
    def generateMessage(self): 
        returnMessage =  "Flights are now available to " + self.island + "!\n"
        returnMessage += "Host: " + self.name + " (" + self.owner.mention + ")\n"
        returnMessage += "Dodo Code™: " + self.code + "\n"
        returnMessage += "This flight will be available for " + str(self.duration) + " from time of posting\n"

        
        if self.extra.lower() != "none": 
            returnMessage += self.extra
        
        # TODO - do we want this message to mention the requester by discord ID?
        
        return returnMessage