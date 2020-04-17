import discord
from datetime import datetime

# Class representing a moving villager listing that a user requested. It's created
# when the listing is successfully created and persists until its timer expires 
# or it's manually closed. 
class Move: 
    # Constructor for the Move class
    # Arguments: 
    #   owner: The discord.py User object ID for the user who requested the move
    #   villager: The name of the AC villager moving out that the user provided 
    #   island: The AC island name the user provided 
    #   end_time: The time the move should be removed
    #   extra: Any additional information the user wants to provide about their island
    #   message: The discord.py Message object for the listing that was made
    def __init__(self, owner, villager, island, end_time, extra): 
        self.villager = villager
        self.message = None
    
    # 
    def setMessage(self, message): 
        self.message = message
    
    # Checks if the requested duration for the move listing has been reached
    # and returns True if it has, False if it hasn't. 
    def checkExpired(self): 
        if datetime.utcnow() > self.end_time: 
            return True
        else: 
            return False
    
    # Use the information in this object to create a string that will be 
    # used in the listing message for this move
    def generateMessage(self): 
        # TODO - Update this return value
        returnMessage = "TODO"
        
        return returnMessage
    
    # Return a discord.File reference to an image for the specified villager
    #def generateImage(self): 
        # TODO 