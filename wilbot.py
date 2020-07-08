import discord
import asyncio
import threading
import time
import re
import pickle
import xml.etree.ElementTree as ET
from flight import *
from move import *
from datetime import time
from datetime import datetime
from datetime import timedelta
from discord.ext import tasks

# Main client reference for this Bot
client = discord.Client()

# Important discord object IDs parsed from wilbot_config.xml
configXML = None

# A list of user's (discord User object IDs) actively using Wilbot
active_sessions = []
active_sessions_lock = threading.Lock()

# A dictionary mapping user object ID's to their active flights
flights = {}
flights_lock = threading.Lock()

# A dictionary mapping user object ID's to their active moves
moves = {}
moves_lock = threading.Lock()

# List of Channel IDs that have recently requested the help message
help_throttle = []
help_throttle_lock = threading.Lock()

# Simple print wrapper to force flushing
def log(logMessage): 
    print(str(datetime.now()) + ":\t" + logMessage, flush=True)
    
# Return True if there is a non-twitter url in the provided string or if there are more than 2 urls, False otherwise
def checkForUrl(checkString): 
    if "http" in checkString.lower(): 
        findCount = 0
        for match in re.finditer("http", checkString): 
            findCount = findCount + 1
            log("checkForUrl() - Checking URL begining with " + checkString[match.start() : match.start()+19])
            if checkString[match.start() : match.start()+19] != "https://twitter.com": 
                return True
                
        if findCount != 1: 
            return True
        else: 
            return False
    else: 
        return False

# Delete a message with the specified Message ID. Note that this will also remove 
# and any corresponding entry in flights and moves if there is one for this message. 
# The channel argument is the channel wilbot can use to provide feedback from the 
# delete attempt. No feedback will be attempted if channel is None which is the 
# default if no channel is provided
async def deleteMessage(messageID, channel = None): 
    log("deleteMessage() - Attempting to delete a message with ID: " + str(messageID))
    messageToDelete = None
    for serverConfig in configXML.getroot(): 
        for child in serverConfig: 
            if (child.tag == 'flight') or (child.tag == 'move'): 
                try: 
                    # Try to retrieve the requested message from the channel
                    listing_channel = client.get_channel(int(child.attrib['channelID']))
                    messageToDelete = await listing_channel.fetch_message(messageID)
                except Exception as ex: 
                    #log("deleteRoutine() - failed to retrieve a message: " + str(ex))
                    # Exception occurred while trying to retrieve the message but that 
                    # may be ok, we'll check the other channels/servers
                    messageToDelete = None
                
            if messageToDelete is not None: 
                break
            
        if messageToDelete is not None: 
                break
                    
    if messageToDelete is not None: 
        # Found the message
        log("deleteRoutine() - Found a matching message")
        
        # Make sure Wilbot was the author of this message
        if messageToDelete.author == client.user: 
                # Perform the deletions
                log("deleteRoutine() - Deleting message with ID " + str(messageID))
                
                try: 
                    flights_lock.acquire()
                    
                    # See if this message has an associated flight and delete it if so
                    originalListersID = 0
                    for userID, flight in flights.items(): 
                        if flight.messageID == messageToDelete.id: 
                            originalListersID = userID
                            break
                            
                    if originalListersID != 0: 
                        del flights[originalListersID]
                
                finally: 
                    flights_lock.release()
                    
                try: 
                    moves_lock.acquire()
                    
                    # See if this message has an associated move and delete it if so
                    originalListersID = 0
                    for userID, move in moves.items(): 
                        if move.messageID == messageToDelete.id: 
                            originalListersID = userID
                            break
                            
                    if originalListersID != 0: 
                        del moves[originalListersID]
                
                finally: 
                    moves_lock.release()
                    
                try: 
                    # Delete the message
                    await messageToDelete.delete()
                    if channel is not None: 
                        await channel.send("Message deleted")
                except Exception as ex: 
                    log("deleteRoutine() - failed to delete a message: " + str(ex))
                    if channel is not None: 
                        await channel.send("Wuh-oh! Something went wrong and I was unable to delete the message.")
                    
                
        else: 
            log("deleteRoutine() - Failed to find the message the user asked to delete.")
            if channel is not None: 
                await channel.send("Wuh-oh! I couldn't find a message with your supplied ID in the channels where I manage listings.")

# Used to confirm with the user which guild they want to post the listing in when 
# they are a member of multiple guilds Wilbot is a member of. This will return 
# an XML Element object representing the selected server's node. 
async def confirmServer(channel, user): 
    log("confirmServer() - Enter")
    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
    
        def inputCheck(checkMessage): 
            # Make sure this was a message sent as a DM by the same user
            if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
                # Make sure the message does not contain a URLs
                if checkForUrl(checkMessage.content) == True: 
                    return False
                else: 
                    return True
                    
        # Create a list of configured servers this user is a member of
        usersServers = []
        for serverConfig in configXML.getroot(): 
            log("Checking if they're a member of: " + str(serverConfig.attrib['name']))
            guild = client.get_guild(int(serverConfig.attrib['id']))
            if user in guild.members: 
                log("User is a member. Adding to list.")
                usersServers.append(serverConfig)
        
        # User is not in any server, should be ignored
        if len(usersServers) == 0: 
            return None
            
        # User is only in one of the servers so default to that one
        elif len(usersServers) == 1: 
            return usersServers[0]
            
        # User is in 2+ servers, prompt them to determine which they want to use
        else: 
            serverPromptString = "Hey, it looks like you're a member of multiple servers where I manage listings. Could you confirm for me which one you want this listing to be made on? \nEnter the number that corresponds to the server I should use: \n" 
            for i in range(1, len(usersServers)+1): 
                serverPromptString = serverPromptString + str(i) + ": " + usersServers[i-1].attrib['name'] + "\n"
            
            await channel.send(serverPromptString)
                
            try: 
                log("confirmServer() - Waiting for user to pick a server")
                serverConfirmed = False
                while not serverConfirmed: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                    
                    # Make sure the input is a valid number
                    try: 
                        input = int(userAnswer.content)
                    
                        # Make sure the supplied value is greater than 0 and less than len(usersServers) + 1
                        if input > 0 and input < (len(usersServers) + 1): 
                            serverSelection = input
                            serverConfirmed = True
                        else: 
                            await channel.send("Wuh-oh! Your selection needs to be one of the options supplied. Please try again")
                            
                    except ValueError: 
                        await channel.send("Wuh-oh! Your selection needs to be a positive whole number value. Please try again")
                        
                return usersServers[input-1]
                
            except asyncio.TimeoutError: 
                log("confirmServer() - User timed out selecting a server")
                await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Message me if you want to try again.")
                return
            
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Cleanup thread. Runs in the background and cleans up expired flights
@tasks.loop(seconds=60.0)
async def cleanupThreadFunction(): 
    await client.wait_until_ready()
    
    try: 
        flights_lock.acquire()

        # Check each flight to see if it's expired and delete its message and 
        # remove it from the list if so. 
        keys_to_delete = []
        for userID in flights.keys(): 
            if flights[userID].checkExpired() == True: 
                log("cleanupThreadFunction() - Cleaning up an expired flight")
                
                # Delete the message. 
                await deleteMessage(flights[userID].messageID)
                
                # Append key to list of those to delete after iterating
                keys_to_delete.append(userID)
        
        # Delete the flight objects from the dictionary
        for key in keys_to_delete: 
            del flights[key]
            
    finally: 
        flights_lock.release()
    
    # Check each move to see if it's expired and delete its message and 
    # remove it from the list if so. 
    try: 
        moves_lock.acquire()

        # Check each move to see if it's expired and delete its message and 
        # remove it from the list if so. 
        keys_to_delete = []
        for userID in moves.keys(): 
            if moves[userID].checkExpired() == True: 
                log("cleanupThreadFunction() - Cleaning up an expired move")
                
                # Delete the message. 
                await deleteMessage(moves[userID].messageID) 
                
                # Append key to list of those to delete after iterating
                keys_to_delete.append(userID)
        
        # Delete the move objects from the dictionary
        for key in keys_to_delete: 
            del moves[key]
            
    finally: 
        moves_lock.release()
    
    # Clean out the contents of the help_throttle list
    try: 
        help_throttle_lock.acquire()
        help_throttle.clear()
    finally: 
        help_throttle_lock.release()

# Prompts the user with a number of questions in order to collect 
# details for a flight to their island. If questions are answered 
# sufficiently, a message with the flight details will be posted 
# and a flight object added to the flights list. 
async def flightRoutine(channel, user, listingChannelID): 
    log("flightRoutine() - Enter")
    
    def inputCheck(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForUrl(checkMessage.content) == True: 
                return False
            else: 
                return True
    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        # Check if the user has an active flight and offer to cancel the old one first
        if user.id in flights.keys(): 
            log("flightRoutine() - User requested a flight while they already had one")
            await channel.send("Wuh-oh! Looks like you already have a flight listed. Do you want me to go ahead and cancel that one? Reply with 'yes' or 'no'")
            try: 
                userProvidedCancelMessage = await client.wait_for('message', check=inputCheck, timeout=30.0)
            except asyncio.TimeoutError: 
                await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
                return
            else: 
                # Check if the user replied with "yes"
                if userProvidedCancelMessage.content.lower() != "yes": 
                    # Don't allow the user to create two listings
                    await channel.send("Wuh-oh! I can't let you have two flights listed at the same time. Cancel your existing one then try again.")
                    return
                else: 
                    # Delete the flights message
                    await deleteMessage(flights[user.id].messageID, channel)
                    await channel.send("OK! Your previous listing has been canceled.")
                    
        
        # Begin collecting the necessary information from the user
        await channel.send("So you'd like to list a flight to your island? Great! I just need you to answer a few questions first. Please include at most 1 Twitter link in your answers. Answers that include more than 1 or links to other websites will be ignored. ")
        
        # Variables holding the user supplied information
        playerName = ""
        islandName = "" 
        dodoCode = ""
        duration = 0
        extra = ""
        
        # Get the user's in game name
        await channel.send("Alright, could you start by telling me your in game name in Animal Crossing?")
            
        try: 
            log("flightRoutine() - Waiting for user to give a playerName")
            userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
            playerName = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing playerName")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Get the user's island name
        await channel.send("Next, could you tell me the name of your island?")
            
        try: 
            log("flightRoutine() - Waiting for user to give an islandName")
            userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
            islandName = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing islandName")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Get the user's Dodo Code (tm)
        await channel.send("Great! Now, could you tell me the Dodo Code™ others can use to find your island?")
            
        try: 
            log("flightRoutine() - Waiting for user to give a dodoCode")
            dodoCodeReceived = False
            while not dodoCodeReceived: 
                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                
                # Check that the code is the right length
                if len(userAnswer.content) != 5: 
                    await channel.send("Wuh-oh! Your Dodo Code™ needs to be exactly 5 characters long. Please double check it and resubmit it.")
                    
                # Check that the code is only alpha numeric characters
                elif re.fullmatch("[A-Z0-9]{5}", userAnswer.content.upper()) == None: 
                    await channel.send("Wuh-oh! Your Dodo Code™ needs to be letters and numbers only. Please double check it and resubmit it.")
                    
                # Check that the code does not contain invalid letters
                elif re.search("[IOZ]", userAnswer.content.upper()) != None: 
                    await channel.send("Wuh-oh! Your Dodo Code™ cannot contain the characters 'I', 'O' or 'Z'. Please double check it and resubmit it.")
                    
                # This is a valid code
                else: 
                    dodoCode = userAnswer.content.upper()
                    dodoCodeReceived = True
            
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing dodoCode")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Get the length of time (in hours) they'd like to have the flight listed for
        await channel.send("Almost finished. For how long, in hours, would you like this flight to be listed?")
            
        try: 
            log("flightRoutine() - Waiting for user to give a duration")
            durationReceived = False
            while not durationReceived: 
                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                
                # Make sure the input is a valid number
                try: 
                    input = float(userAnswer.content)
                
                    # Make sure the supplied value is greater than 0
                    if input > 0: 
                        duration = timedelta(hours=float(userAnswer.content))
                        durationReceived = True
                    else: 
                        await channel.send("Wuh-oh! Your duration needs to be a positive number. Please try again")
                        
                except ValueError: 
                    await channel.send("Wuh-oh! Your duration needs to be a positive numeric value (decimal values are ok). Please try again")
                
                
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing duration")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Get any extra information the user wants to supply
        await channel.send("And lastly, is there anything extra you'd like people to know about your island? This could be things like who's visiting or what hot items are for sale in your town. If you don't have anything to add, just reply with 'None'")
            
        try: 
            log("flightRoutine() - Waiting for user to give extra information")
            userAnswer = await client.wait_for('message', check=inputCheck, timeout=60.0)
            extra = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing extra information")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 60 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Create the flight object
        log("flightRoutine() - Creating the flight object")
        end_time = datetime.utcnow() + duration
        newFlight = Flight(user.mention, playerName, islandName, duration, end_time, dodoCode, extra)
        
        # Confirm that the message looks good to the user before posting
        await channel.send("That's everything! With the information provided your listing will look like this. \n" + newFlight.generateMessage() + "\nShould I go ahead and post it? Answer 'yes' or 'no' please.")
        try: 
            userProvidedConfirmationMessage = await client.wait_for('message', check=inputCheck, timeout=30.0)
        except asyncio.TimeoutError: 
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        else: 
            # Check if the user replied with "yes"
            if userProvidedConfirmationMessage.content.lower() != "yes": 
                # Don't allow the user to create two listings
                await channel.send("No worries, I won't post it. Message me 'flight' if you'd like to try again.")
                return
        
        # Success! We got all the necessary information and the user confirmed it looks good
        await channel.send("Alright! I'll go ahead and list this flight for you. You can always send me 'cancel' to have me take it down at any time.")

        # Send the message
        listing_channel = client.get_channel(int(listingChannelID))
        listingMessage = await listing_channel.send(newFlight.generateMessage())
        newFlight.setMessageID(listingMessage.id)
        
        # Add the flight object to the map
        try: 
            flights_lock.acquire()
            flights[user.id] = newFlight
        finally: 
            flights_lock.release()
    
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Prompts the user with a number of questions in order to collect 
# details for a post notifying that a villager wants to move 
# off their island. 
async def moveRoutine(channel, user, listingChannelID): 
    log("moveRoutine() - Enter")
    
    # Function used to check for user answers
    def inputCheck(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForUrl(checkMessage.content) == True: 
                return False
            else: 
                return True
    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        
        # Check if the user has an active move and offer to cancel the old one first
        if user.id in moves.keys(): 
            log("moveRoutine() - User requested a Move while they already had one")
            await channel.send("Wuh-oh! Looks like you already have a move listed. Do you want me to go ahead and cancel that one? Reply with 'yes' or 'no'")
            try: 
                userProvidedCancelMessage = await client.wait_for('message', check=inputCheck, timeout=30.0)
            except asyncio.TimeoutError: 
                await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
                return
            else: 
                # Check if the user replied with "yes"
                if userProvidedCancelMessage.content.lower() != "yes": 
                    # Don't allow the user to create two listings
                    await channel.send("Wuh-oh! I can't let you have two moves listed at the same time. Cancel your existing one then try again.")
                    return
                else: 
                    # Delete the moves message and the entry in moves map for it
                    await deleteMessage(moves[user.id].messageID, channel)
                    await channel.send("OK! Your previous listing has been canceled.")
                    
        
        # Begin collecting the necessary information from the user
        await channel.send("So you'd like to post a listing for a villager moving off of your island? Great! I just need you to answer a few questions first. Please include at most 1 Twitter link in your answers. Answers that include more than 1 or links to other websites will be ignored. ")
            
        # Variables storing the user's answers
        playerName = "" 
        villagerName = "" 
        duration = 0
        end_time = ""
        extra = ""
        
        # Get the user's in game name
        await channel.send("Alright, could you start by telling me your in game name in Animal Crossing?")
            
        try: 
            log("moveRoutine() - Waiting for user to give a playerName")
            userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
            playerName = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("moveRoutine() - User timed out providing playerName")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
            return
        
        # Get the user's villager name
        await channel.send("Next, could you tell me the name of the villager moving out?")
            
        try: 
            log("moveRoutine() - Waiting for user to give a villagerName")
            villagerReceived = False
            while not villagerReceived: 
                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                
                if Move.checkVillager(userAnswer.content) == False: 
                    await channel.send("Wuh-oh! I couldn't find a villager with a name like that. Please try again")
                else: 
                    villagerName = str(userAnswer.content)
                    villagerReceived = True
                    
        except asyncio.TimeoutError: 
            log("moveRoutine() - User timed out providing villagerName")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
            return
                
        # Get the length of time (in hours) they'd like to have the move listed for
        await channel.send("Almost finished. For how long, in hours, would you like this move to be listed?")
            
        try: 
            log("moveRoutine() - Waiting for user to give a duration")
            durationReceived = False
            while not durationReceived: 
                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                
                # Make sure the input is a valid number
                try: 
                    input = float(userAnswer.content)
                
                    # Make sure the supplied value is greater than 0 and less than 48
                    if (input > 0) and (input <= 48): 
                        duration = timedelta(hours=float(userAnswer.content))
                        durationReceived = True
                    else: 
                        await channel.send("Wuh-oh! Your duration needs to be a number betwee 0 and 48. Please try again")
                        
                except ValueError: 
                    await channel.send("Wuh-oh! Your duration needs to be a numeric value (decimal values are ok). Please try again")
                
                
        except asyncio.TimeoutError: 
            log("moveRoutine() - User timed out providing duration")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
            return
           
        end_time = datetime.utcnow() + duration
        
        # Get any additional information they want to provide
        await channel.send("Great! Is there anything else you want to add to the listing? I'll go ahead and add a picture of the villager myself. If you want to you can include a Twitter link too but I'm afraid I can't post images you may attach to this message directly. If you don't want to add anything, just reply with 'None'")
            
        try: 
            log("moveRoutine() - Waiting for user to give an extra")
            userAnswer = await client.wait_for('message', check=inputCheck, timeout=60.0)
            extra = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("moveRoutine() - User timed out providing extra")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 60 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
            return
        
        # Create the move object
        newMove = Move(user.mention, playerName, villagerName, end_time, extra)
        
        # Confirm that the message looks good to the user before posting
        await channel.send("That's everything! With the information provided your listing will look like the following. Should I go ahead and post it? Answer 'yes' or 'no' please. \n\n" + newMove.generateMessage())
        try: 
            log("moveRoutine() - Waiting for user to confirm listing")
            userProvidedConfirmationMessage = await client.wait_for('message', check=inputCheck, timeout=30.0)
        except asyncio.TimeoutError: 
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
            return
        else: 
            # Check if the user replied with "yes"
            if userProvidedConfirmationMessage.content.lower() != "yes": 
                # Don't allow the user to create two listings
                await channel.send("No worries, I won't post it. Message me 'move' if you'd like to try again.")
                return
        
        # Success! We got all the necessary information and the user confirmed it looks good
        await channel.send("Alright! I'll go ahead and list this move for you. You can always send me 'cancel' to have me take it down at any time.")
        
        # Send the message
        listing_channel = client.get_channel(int(listingChannelID))
        listing_message = await listing_channel.send(newMove.generateMessage())
        newMove.setMessageID(listing_message.id)
        
        # Add the move object to the map
        try: 
            moves_lock.acquire()
            moves[user.id] = newMove
        finally: 
            moves_lock.release()
        
        
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Will confirm that the user wishes to cancel their flight and, if 
# so, delete the associated message and flight object. 
async def cancelRoutine(channel, user): 
    log("cancelRoutine() - Enter")
    
    # Functions used for checking input for user answers
    def inputCheck(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForUrl(checkMessage.content) == True: 
                return False
            else: 
                return True
    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        flight_delete_flag = (user.id in flights.keys())
        move_delete_flag = (user.id in moves.keys())
        
        # Check whether the user has an active flight, move or both 
        if flight_delete_flag and move_delete_flag:
            # User has both a flight and a move listing
            log("cancelRoutine() - User has both a flight and a move listing")
            
            # Determine whether the user wants to delete the flight, the move or both
            await channel.send("It looks like you have both a flight listing and a move listing right now. Do you want to cancel the flight, the move or both? Reply with 'flight', 'move', or 'both'")
            
            bothAnswer = False
            while bothAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Cancel' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "flight") or (answerContent == "move") or (answerContent == "both"): 
                        bothAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'flight' or 'move' or 'both' only.")
            
            # Update the flags per the user's answer 
            if answerContent == "both": 
                flight_delete_flag = True
                move_delete_flag = True
            elif answerContent == "flight": 
                flight_delete_flag = True
                move_delete_flag = False
            elif answerContent == "move": 
                flight_delete_flag = False
                move_delete_flag = True
        
        if flight_delete_flag: 
            # User only has an active flight they want deleted
            log("cancelRoutine() - User has only an active flight")
            await channel.send("It looks like you have the following flight: \n" + flights[user.id].generateMessage() + "\nWould you like to delete it? Please reply with 'yes' or 'no'")
            
            flightAnswer = False
            answerContent = "" 
            while flightAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Cancel' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "yes") or (answerContent == "no"): 
                        flightAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if answerContent == "yes": 
                # Delete the flights message
                await deleteMessage(flights[user.id].messageID, channel) 
                await channel.send("OK! Your previous flight listing has been canceled.")
                
                # Delete the flight object from the list if deleteMessage failed to
                if user.id in flights.keys(): 
                    try: 
                        flights_lock.acquire()
                        del flights[user.id]
                    finally: 
                        flights_lock.release()
                    
            else: 
                await channel.send("OK, I'll leave your flight listing in place, then.")
                return
            
        if move_delete_flag: 
            # User only has an active move they want deleted
            log("cancelRoutine() - User has only an active move")
            await channel.send("It looks like you have the following move listing: \n" + moves[user.id].generateMessage() + "\nWould you like to delete it? Please reply with 'yes' or 'no'")
            
            moveAnswer = False
            answerContent = "" 
            while moveAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Cancel' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "yes") or (answerContent == "no"): 
                        moveAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if answerContent == "yes": 
                # Delete the move's message
                await deleteMessage(moves[user.id].messageID, channel) 
                await channel.send("OK! Your previous move listing has been canceled.")
                
                # Delete the move object from the list if deleteMessage failed to
                if user.id in moves.keys(): 
                    try: 
                        moves_lock.acquire()
                        del moves[user.id]
                    finally: 
                        moves_lock.release()
                    
            else: 
                await channel.send("OK, I'll leave your move listing in place, then.")
                return
        
        else: 
            # User has neither. Note this should have been checked 
            # previously so we'll just log here and exit
            log("cancelRoutine() - User requested cancel but had nothing to cancel")
    
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Will prompt an officer user for a message ID and will delete it if it's 
# a Wilbot message
async def deleteRoutine(channel, user): 
    log("deleteRoutine() - Enter")
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        # Define a function used to check for the user's reply to the request for the 
        # message to be deleted's ID
        # The message must come from the same DM Channel and must be from the original user
        def deleteCheck(checkMessage): 
            return ((checkMessage.channel == channel) and (checkMessage.author == user))
        
        # Send a message asking the user for the ID of the message to be deleted
        await channel.send("Certainly. What is the ID of the message you'd like deleted? ")
            
        try: 
            log("deleteRoutine() - waiting for user to provide the message ID")
            # Wait for the user to provide the requested ID
            userProvidedIDMessage = await client.wait_for('message', check=deleteCheck, timeout=30.0)
        except asyncio.TimeoutError: 
            await channel.channel.send("Wuh-oh! I didn't catch that. Make sure to tell me the ID within 30 seconds when prompted. Send me a message saying 'Delete' if you want to try again.")
        else: 
            # Got the requested input
            log("deleteRoutine() - User provided a message ID: " + str(userProvidedIDMessage.content))
            
            # Extract the ID of the message to be deleted from the user's reply
            msgID = userProvidedIDMessage.content
            
            await deleteMessage(msgID, channel)
            
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Sends a message with instructions for using Wilbot to the channel supplied
async def helpRoutine(channel): 
    log("helpRoutine() - Sending help message")
    
    helpMessage = """I can perform the following functions: 
**Flight:** Answer some questions and I'll post a flight listing for your island
**Move:**   Answer some questions and I'll post a move listing for a villager moving off your island
**Cancel:** I'll cancel a flight listing or a move listing you have
**Delete:** Officers only - Delete a post that Wilbot has made
**Help:** Prints this helpful help message

Make sure to send Wilbot instructions in a Direct Message"""
    await channel.send(helpMessage) 
    
    log("helpRoutine() - help message sent")

# Sends a message indicating the request made by the user was invlid then calls the help routine
async def invalidInputRoutine(channel): 
    log("invalidInputRoutine() - Sending message")
    
    await channel.send("Wuh-oh! That's not a command I recognize. Make sure you're using a command specified in the help prompt with no extraneous words or characters.") 
    await helpRoutine(channel)
    
    log("invalidInputRoutine() - message sent")

################ Event Handlers ################

# Process the event raised when the bot has started up fully
@client.event
async def on_ready():
    #await client.change_presence(activity=discord.Activity(name='the skies', type=discord.ActivityType.watching))
    
    log("Wilbot is online!")

# Process any new message that gets sent in the server
@client.event
async def on_message(message):
    # Ignore all messages sent by Wilbot so it doesn't 
    # ever get stuck in a loop
    if message.author == client.user:
        return
    
    # Check if this was a private message and that the user isn't already talking to Wilbot
    if (message.channel.type is discord.ChannelType.private) and (not message.author.id in active_sessions): 
        log("on_message() - Received a Direct Message: " + message.content)
        
        # Put the message in lower case to simplify parsing
        messageContent = message.content.lower()
        
        # Check the direct message content for words or phrases Wilbot should act on
        if "flight" == messageContent: 
            # Get the "server" config information for where this listing would go
            serverConfig = await confirmServer(message.channel, message.author)
            
            if serverConfig is None: 
                return
            
            # Make sure the user has the right role to use this command
            guild = client.get_guild(int(serverConfig.attrib['id']))
            flightConfig = None
            for child in serverConfig: 
                if child.tag == "flight": 
                    flightConfig = child
                    break
                    
            post_role = guild.get_role(int(flightConfig.attrib['rollID']))
            if post_role in guild.get_member(message.author.id).roles: 
                log("on_message() - Running the flight routine")
                await flightRoutine(message.channel, message.author, flightConfig.attrib['channelID'])
            else: 
                log("on_message() - Flight called by user with incorrect roles")
                await message.channel.send("Wuh-oh! Looks like you don't have the right role to use this command.")
                
        elif "move" == messageContent: 
            # Get the "server" config information for where this listing would go
            serverConfig = await confirmServer(message.channel, message.author)
            
            # Make sure the user has the right role to use this command
            guild = client.get_guild(int(serverConfig.attrib['id']))
            moveConfig = None
            for child in serverConfig: 
                if child.tag == "move": 
                    moveConfig = child
                    break
                    
            post_role = guild.get_role(int(moveConfig.attrib['rollID']))
            if post_role in guild.get_member(message.author.id).roles: 
                log("on_message() - Running the move routine")
                await moveRoutine(message.channel, message.author, moveConfig.attrib['channelID'])
            else: 
                log("on_message() - move called by user with incorrect roles")
                await message.channel.send("Wuh-oh! Looks like you don't have the right role to use this command.")
                
        elif "cancel" == messageContent: 
            # Check if the user has an active flight
            if (message.author.id in flights.keys()) or (message.author.id in moves.keys()): 
                log("on_message() - Running the cancel routine")
                await cancelRoutine(message.channel, message.author)
            else: 
                log("on_message() - Cancel called when the user did not have an active flight or move")
                await message.channel.send("Wuh-oh! It doesn't look like you have any active listings.")
                
        elif "delete" == messageContent: 
            # Get the "server" config information for where this listing would go
            serverConfig = await confirmServer(message.channel, message.author)
            
            # Make sure the user has the right role to use this command
            guild = client.get_guild(int(serverConfig.attrib['id']))
            deleteConfig = None
            for child in serverConfig: 
                if child.tag == "delete": 
                    deleteConfig = child
                    break
            
            delete_role = guild.get_role(int(deleteConfig.attrib['rollID']))
            if delete_role in guild.get_member(message.author.id).roles: 
                log("on_message() - Running the delete routine")
                await deleteRoutine(message.channel, message.author)
            else: 
                log("on_message() - Delete called by user with incorrect roles")
                await message.channel.send("Wuh-oh! You don't have the right role to use this command.")
                
        elif ("help" == messageContent): 
            log("on_message() - Running the help routine")
            await helpRoutine(message.channel)
            
        else: 
            log("on_message() - Running the invalid input routine")
            await invalidInputRoutine(message.channel)
        
    # Check if the message mentions Wilbot and work 
    # on those that do
    if client.user in message.mentions:
        log("on_message() - Wilbot's User ID was mentioned")
        
        # Put the message in lower case to simplify parsing
        messageContent = message.content.lower()
        
        # Check the message content for words or phrases Wilbot should act on
        if "help" in messageContent: 
            log("on_message() - Received a help request in a message mentioning Wilbot")
            try: 
                # Check if help has been requested too recently in this channel
                help_throttle_lock.acquire()
                if not message.channel.id in help_throttle: 
                    # Send the help message
                    help_throttle.append(message.channel.id)
                    
                    log("on_message() - Running the help routine")
                    await helpRoutine(message.channel)
                else: 
                    # Do not send the help message
                    log("on_message() - help was requested too recently to print it again")
                    
            finally: 
                help_throttle_lock.release()
            

# Start the Cleanup Thread
cleanupThreadFunction.start()

# Retrieve wilbot's Bot Token from the botToken.txt file
tokenFile = open('botToken.txt')
token = tokenFile.readline()
tokenFile.close()

# Load the configuration xml file
configXML = ET.parse('wilbot_config.xml')

# Unpickle any existing flight or move listings
try: 
    flightsPickle = open('flights.pkl', 'rb')
    flights = pickle.load(flightsPickle)
    flightsPickle.close();
except Exception as ex: 
    log("Unable to unpickle previous flights dictionary")
    log(str(ex))
    
try: 
    movesPickle = open('moves.pkl', 'rb')
    moves = pickle.load(movesPickle)
    movesPickle.close();
except Exception as ex: 
    log("Unable to unpickle previous moves dictionary")
    log(str(ex))

try: 
    client.run(token)

finally: 
    # Pickle any existing flight or move listings
    try: 
        flightsPickle = open('flights.pkl', 'wb')
        pickle.dump(flights, flightsPickle)
        flightsPickle.close();
    except Exception as ex: 
        log("Unable to pickle flights dictionary")
        log(str(ex))
    
    try: 
        movesPickle = open('moves.pkl', 'wb')
        pickle.dump(moves, movesPickle)
        movesPickle.close();
    except Exception as ex: 
        log("Unable to pickle moves dictionary")
        log(str(ex))
        
log("post client.run")
