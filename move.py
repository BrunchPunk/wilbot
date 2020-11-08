import csv
from datetime import datetime

# Class representing a moving villager listing that a user requested. It's created
# when the listing is successfully created and persists until its timer expires 
# or it's manually closed. 
class Move: 
    
    # Static Variables 
    villagerImageMap = {}
    
    # Static Functions
    # 
    @staticmethod
    def initVillagerImageMap(): 
        print("Running initVillagerImageMap()", flush=True)
        reader = csv.reader(open('villager_image_map.csv'))
        
        Move.villagerImageMap = {}
        for row in reader: 
            Move.villagerImageMap[row[0].lower()] = row[1]
    
    # Check if the provided villager name is in the dictionary of 
    # valid villagers. Return true if so, false otherwise
    @staticmethod
    def checkVillager(villagerName): 
        print("Running checkVillager", flush=True)
        if not Move.villagerImageMap: 
            Move.initVillagerImageMap()
        
        if villagerName.lower() in Move.villagerImageMap.keys(): 
            return True
        else: 
            return False
    
    # Constructor for the Move class
    # Arguments: 
    #   userID: The discord.py User mention string for the user who requested the flight
    #   playerName: The AC player name the user provided
    #   villager: The name of the AC villager moving out that the user provided 
    #   end_time: The time the move should be removed
    #   extra: Any additional information the user wants to provide about their island
    def __init__(self, userID, playerName, villager, end_time, extra): 
        self.userID = userID
        self.playerName = playerName
        self.villager = villager.title()
        self.end_time = end_time
        self.extra = extra
        self.messageID = None
        
        if not Move.villagerImageMap: 
            Move.initVillagerImageMap()
    
    # Set the message associated with this move listing
    def setMessageID(self, messageID): 
        self.messageID = messageID
    
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
        if not Move.villagerImageMap: 
            Move.initVillagerImageMap()
        
        returnMessage = self.villager + " is moving out of " + self.playerName + "'s island. \n" 
        returnMessage = returnMessage + "Send <@" + str(self.userID) + "> a PM if you're interested in having " + self.villager + " move into your town. \n"
        
        if self.extra.lower() != "none": 
            returnMessage  = returnMessage + self.extra + "\n"
            
        returnMessage = returnMessage + Move.villagerImageMap[self.villager.lower()]
        
        return returnMessage
