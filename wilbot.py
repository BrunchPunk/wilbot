import discord
import asyncio
import threading
import time
import re
import pickle
import sqlite3
import os
import xml.etree.ElementTree as ET

from discord.errors import NotFound
from flight import *
from move import *
from userDB import * 
from flightDB import *
from moveDB import * 
from datetime import time
from datetime import datetime
from datetime import timedelta
from discord.ext import tasks

#Give the bot the necessary permissions
intents = discord.Intents.all()

# Main client reference for this Bot
client = discord.Client(intents = intents)

# Important discord object IDs parsed from wilbot_config.xml
configXML = None

# A list of user's (discord User object IDs) actively using Wilbot
active_sessions = []
active_sessions_lock = threading.Lock()

# List of Channel IDs that have recently requested the help message
help_throttle = []
help_throttle_lock = threading.Lock()

# Simple print wrapper to force flushing
def log(logMessage): 
    print(str(datetime.now()) + ":\t" + logMessage, flush=True)
    
# Return False if there is a non-twitter url in the provided string or if there are more than 2 urls, True otherwise
def checkForValidUrl(checkString): 
    if "http" in checkString.lower(): 
        findCount = 0
        for match in re.finditer("http", checkString): 
            findCount = findCount + 1
            log("checkForUrl() - Checking URL begining with " + checkString[match.start() : match.start()+19])
            if checkString[match.start() : match.start()+19] != "https://twitter.com": 
                return False
                
        if findCount != 1: 
            return False
        else: 
            return True
    else: 
        return True

# Return False if there is any URL in the string, True otherwise
def checkForNoUrl(checkString): 
    if "http" in checkString.lower(): 
        return False
    else: 
        return True

# Delete a message with the specified Message ID. Note that this will also remove 
# any corresponding entry in flights and moves if there is one for this message. 
# The channel argument is the channel wilbot can use to provide feedback from the 
# delete attempt. No feedback will be attempted if channel is None which is the 
# default if no channel is provided
async def deleteMessage(messageID, channel = None): 
    log("deleteMessage() - Attempting to delete a message with ID: " + str(messageID))
    
    message_deleted = False
    
    # Check the Flight DB for this message 
    flight_result = FlightDB.select_message(int(messageID))
    if not flight_result is None: # there was a flight with this message ID
        # Delete the message
        try: 
            listing_channel = client.get_channel(flight_result[FlightDB.CHANNEL_ID_COL])
            messageToDelete = await listing_channel.fetch_message(messageID)
            await messageToDelete.delete()
            log("deleteMessage() - Deleted a flight listing message with ID: " + str(messageID))
        except NotFound: 
            # Ignore this, it's fine if there isn't one
            log("deleteMessage() - Did not find a flight message with ID: " + str(messageID))
        
        # Delete the flight's row in the database
        FlightDB.delete(flight_result[FlightDB.USER_ID_COL], flight_result[FlightDB.SERVER_ID_COL])
        log("deleteMessage() - Deleted a flight db entry with user/server: " + str(flight_result[FlightDB.USER_ID_COL]) + "/" + str(flight_result[FlightDB.SERVER_ID_COL]))
        
        message_deleted = True
    
    # Check the Move DB for this message
    move_result = MoveDB.select_message(messageID)
    if not move_result is None: # there was a move with this message ID
        # Delete the message
        try: 
            listing_channel = client.get_channel(move_result[FlightDB.CHANNEL_ID_COL])
            messageToDelete = await listing_channel.fetch_message(messageID)
            await messageToDelete.delete()
            log("deleteMessage() - Deleted a move listing message with ID: " + str(messageID))
        except NotFound: 
            # Ignore this, it's fine if there isn't one
            log("deleteMessage() - Did not find a move message with ID: " + str(messageID))
        
        # Delete the move's row in the database
        MoveDB.delete(move_result[MoveDB.USER_ID_COL], move_result[MoveDB.SERVER_ID_COL])
        log("deleteMessage() - Deleted a move db entry with user/server: " + str(move_result[MoveDB.USER_ID_COL]) + "/" + str(move_result[MoveDB.SERVER_ID_COL]))
        
        message_deleted = True
    
    if not message_deleted: 
        log("deleteMessage() - Failed to find the message the user asked to delete.")
        if channel is not None: 
            await channel.send("Wuh-oh! I couldn't find a message with your supplied ID in the channels where I manage listings.")
    
# Used to confirm with the user which guild they want to perform the action on in when 
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
                if checkForNoUrl(checkMessage.content) == True: 
                    return True
                else: 
                    return False
                    
        # Create a list of configured servers this user is a member of
        usersServers = []
        for serverConfig in configXML.getroot(): 
            log("Checking if they're a member of: " + str(serverConfig.attrib['name']))
            guild = client.get_guild(int(serverConfig.attrib['id']))
            if (guild is not None) and (user in guild.members): 
                log("User is a member. Adding to list.")
                usersServers.append(serverConfig)
        
        # User is not in any server, should be ignored
        if len(usersServers) == 0: 
            log("User is not in any server.")
            return None
            
        # User is only in one of the servers so default to that one
        elif len(usersServers) == 1: 
            log("User is in only one server. Using that one.")
            return usersServers[0]
            
        # User is in 2+ servers, prompt them to determine which they want to use
        else: 
            serverPromptString = "Hey, it looks like you're a member of multiple servers where I manage listings. Could you confirm for me which server you want this action applied to? \nEnter the number that corresponds to the server I should use: \n" 
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

    for flight_row in FlightDB.selectAll(): 
        if datetime.utcnow() > flight_row[FlightDB.END_TIME_COL]: 
            log("Attempting to delete a flight row: " + str(flight_row))
            await deleteMessage(flight_row[FlightDB.MESSAGE_ID_COL])
            
    for move_row in MoveDB.selectAll(): 
        if datetime.utcnow() > move_row[MoveDB.END_TIME_COL]: 
            log("Attempting to delete a move row: " + str(move_row))
            await deleteMessage(move_row[MoveDB.MESSAGE_ID_COL])
            
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
async def flightRoutine(channel, user, listingServerID, listingChannelID): 
    log("flightRoutine() - Enter")
    
    def inputCheckNoURL(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForNoUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
                
    def inputCheckValidURL(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message contains only a valid URL
            if checkForValidUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        # Check if the user has an active flight and offer to cancel the old one first
        existing_listing = FlightDB.select_user_server(user.id, listingServerID)
        if not existing_listing is None: 
            log("flightRoutine() - User requested a flight while they already had one")
            await channel.send("Wuh-oh! Looks like you already have a flight listed. Do you want me to go ahead and cancel that one? Reply with 'yes' or 'no'")
            try: 
                userProvidedCancelMessage = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
            except asyncio.TimeoutError: 
                await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
                return
            else: 
                # Check if the user replied with "yes"
                if (userProvidedCancelMessage.content.lower() != "yes") and (userProvidedCancelMessage.content.lower() != "y"): 
                    # Don't allow the user to create two listings
                    await channel.send("Wuh-oh! I can't let you have two flights listed at the same time. Cancel your existing one then try again.")
                    return
                else: 
                    # Delete the flights message
                    await deleteMessage(existing_listing[FlightDB.MESSAGE_ID_COL], channel)
                    await channel.send("OK! Your previous listing has been canceled.")
                    
        
        # Begin collecting the necessary information from the user
        await channel.send("So you'd like to list a flight to your island? Great! I just need you to answer a few questions first. Please note that responses including links to a website will be ignored unless prompted otherwise. ")
        
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
            userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
            playerName = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing playerName")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Get the user's island name
        await channel.send("Next, could you tell me the name of your island?")
            
        try: 
            log("flightRoutine() - Waiting for user to give an islandName")
            userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
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
                userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
                
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
                userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
                
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
            userAnswer = await client.wait_for('message', check=inputCheckValidURL, timeout=600.0)
            extra = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("flightRoutine() - User timed out providing extra information")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 10 minutes when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        
        # Create the flight object
        log("flightRoutine() - Creating the flight object")
        end_time = datetime.utcnow() + duration
        newFlight = Flight(user.id, playerName, islandName, end_time, dodoCode, extra)
        newFlight.setDuration(duration)
        
        # Confirm that the message looks good to the user before posting
        await channel.send("That's everything! With the information provided your listing will look like this.")
        await channel.send(newFlight.generateMessage())
        await channel.send("Should I go ahead and post it? Answer 'yes' or 'no' please.")
        try: 
            userProvidedConfirmationMessage = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
        except asyncio.TimeoutError: 
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Flight' if you want to try again.")
            return
        else: 
            # Check if the user replied with "yes"
            if (userProvidedConfirmationMessage.content.lower() != "yes") and (userProvidedConfirmationMessage.content.lower() != "y"): 
                # Don't allow the user to create two listings
                await channel.send("No worries, I won't post it. Message me 'flight' if you'd like to try again.")
                return
        
        # Success! We got all the necessary information and the user confirmed it looks good
        await channel.send("Alright! I'll go ahead and list this flight for you. You can always send me 'cancel' to have me take it down at any time.")

        # Send the message
        listing_channel = client.get_channel(listingChannelID)
        listingMessage = await listing_channel.send(newFlight.generateMessage())
        newFlight.setMessageID(listingMessage.id)
        
        # Add the flight to the database
        FlightDB.insert(user.id, listingServerID, listingChannelID, listingMessage.id, playerName,islandName, end_time, dodoCode, extra)
    
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
async def moveRoutine(channel, user, listingServerID, listingChannelID): 
    log("moveRoutine() - Enter")
    
    # Functions used to check for user answers
    def inputCheckNoURL(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForNoUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
                    
    def inputCheckValidURL(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForValidUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        
        # Check if the user has an active move and offer to cancel the old one first
        existing_listing = MoveDB.select_user_server(user.id, listingServerID)
        log("DEBUG - existing listing is: " + str(existing_listing))
        if not existing_listing is None: 
            log("moveRoutine() - User requested a Move while they already had one")
            await channel.send("Wuh-oh! Looks like you already have a move listed. Do you want me to go ahead and cancel that one? Reply with 'yes' or 'no'")
            try: 
                userProvidedCancelMessage = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
            except asyncio.TimeoutError: 
                await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
                return
            else: 
                # Check if the user replied with "yes"
                if (userProvidedCancelMessage.content.lower() != "yes") and (userProvidedCancelMessage.content.lower() != "y"): 
                    # Don't allow the user to create two listings
                    await channel.send("Wuh-oh! I can't let you have two moves listed at the same time. Cancel your existing one then try again.")
                    return
                else: 
                    # Delete the moves message and the entry in moves map for it
                    await deleteMessage(existing_listing[MoveDB.MESSAGE_ID_COL], channel)
                    await channel.send("OK! Your previous listing has been canceled.")
                    
        
        # Begin collecting the necessary information from the user
        await channel.send("So you'd like to post a listing for a villager moving off of your island? Great! I just need you to answer a few questions first. Please note that responses including links to a website will be ignored unless prompted otherwise. ")
            
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
            userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
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
                userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
                
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
                userAnswer = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
                
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
            userAnswer = await client.wait_for('message', check=inputCheckValidURL, timeout=600.0)
            extra = str(userAnswer.content)
        except asyncio.TimeoutError: 
            log("moveRoutine() - User timed out providing extra")
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 10 minutes when prompted. Send me a message saying 'Move' if you want to try again.")
            return
        
        # Create the move object
        newMove = Move(user.id, playerName, villagerName, end_time, extra)
        newMove.setDuration(duration)
        
        # Confirm that the message looks good to the user before posting
        await channel.send("That's everything! With the information provided your listing will look like this: " )
        await channel.send(newMove.generateMessage())
        await channel.send("Should I go ahead and post it? Answer 'yes' or 'no' please.")
        try: 
            log("moveRoutine() - Waiting for user to confirm listing")
            userProvidedConfirmationMessage = await client.wait_for('message', check=inputCheckNoURL, timeout=30.0)
        except asyncio.TimeoutError: 
            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Move' if you want to try again.")
            return
        else: 
            # Check if the user replied with "yes"
            if (userProvidedConfirmationMessage.content.lower() != "yes") and (userProvidedConfirmationMessage.content.lower() != "y"): 
                # Don't allow the user to create two listings
                await channel.send("No worries, I won't post it. Message me 'move' if you'd like to try again.")
                return
        
        # Success! We got all the necessary information and the user confirmed it looks good
        await channel.send("Alright! I'll go ahead and list this move for you. You can always send me 'cancel' to have me take it down at any time.")
        
        # Send the message
        listing_channel = client.get_channel(listingChannelID)
        listing_message = await listing_channel.send(newMove.generateMessage())
        newMove.setMessageID(listing_message.id)
        
        # Add the move listing to the database
        MoveDB.insert(user.id, listingServerID, listingChannelID, listing_message.id, playerName, end_time, villagerName, extra)
        
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Will, through a series of prompts, allow the user to update an 
# existing flight or move listing the user has created. 
async def updateRoutine(channel, user, serverID): 
    log("updateRoutine() - Enter")
    
    # Functions used for checking input for user answers
    def inputCheck(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForNoUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
                
    def inputCheckNoURL(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForNoUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
                
    def inputCheckValidURL(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message contains only a valid URL
            if checkForValidUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
                
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
            
        # Determine what flight and/or move this user has in this server
        existing_flight = FlightDB.select_user_server(user.id, serverID)
        existing_move = MoveDB.select_user_server(user.id, serverID)
        
        flight_update_flag = (not existing_flight is None)
        move_update_flag = (not existing_move is None)
        
        # If the user has neither a flight or delete, go no further
        if not flight_update_flag and not move_update_flag: 
            await channel.send("Wuh-oh! It doesn't look like you have any active listings.")
            return
        
        # Check whether the user has an active flight, move or both 
        if flight_update_flag and move_update_flag:
            # User has both a flight and a move listing
            log("updateRoutine() - User has both a flight and a move listing")
            
            # Determine whether the user wants to delete the flight, the move or both
            await channel.send("It looks like you have both a flight listing and a move listing right now. Do you want to update the flight or the move? Reply with 'flight' or 'move'")
            
            answer = False
            while answer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "flight") or (answerContent == "move"): 
                        answer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'flight' or 'move' only.")
            
            # Update the flags per the user's answer 
            if answerContent == "flight": 
                flight_update_flag = True
                move_update_flag = False
            elif answerContent == "move": 
                flight_update_flag = False
                move_update_flag = True
                
        # Handle an update to their flight listing
        if flight_update_flag: 
            log("updateRoutine() - Updating the user's flight listing")
            
            # Make a flight object from existing_flight
            user_flight = Flight(existing_flight[FlightDB.USER_ID_COL], existing_flight[FlightDB.PLAYER_NAME_COL], existing_flight[FlightDB.ISLAND_NAME_COL], existing_flight[FlightDB.END_TIME_COL], existing_flight[FlightDB.DODO_CODE_COL], existing_flight[FlightDB.EXTRA_COL])
            
            # Display the current flight and make sure the user wants to update it
            await channel.send("It looks like you have the following flight: " )
            await channel.send(user_flight.generateMessage())
            await channel.send("Would you like to modify it? Please reply with 'yes' or 'no'")
            
            flightAnswer = False
            answerContent = "" 
            while flightAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                        flightAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if (answerContent == "no") or (answerContent == "n"): 
                # Don't perform any updates
                await channel.send("OK, I'll leave your flight listing the way it is.")
                return
                
            # Loop, allowing the user to modify an aspect of the flight with each iteration until the done
            doneEditing = False
            answerContent = ""
            while doneEditing == False: 
                # Determine which part of the flight to update
                selectMessage = """What part of the flight listing would you like to change?
    1. Dodo Code™
    2. Duration
    3. Extra Information
    Please answer with the number of the option you want."""
                await channel.send(selectMessage)
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                    answerContent = userAnswer.content.lower()
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    if answerContent == "1": 
                        log("updateRoutine() - User wants to update their code")
                        # Get the user's Dodo Code Update
                        await channel.send("What would you like to update the Dodo Code to?")
                            
                        try: 
                            log("updateRoutine() - Waiting for user to give a dodoCode")
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
                                
                            user_flight.code = dodoCode
                            
                            # Check if the user wants to update something else
                            editingAnswered = False
                            answerContent = ""
                            
                            await channel.send("Do you want to change any other parts of the listing? Answer with 'yes' or 'no'")
                            while editingAnswered == False: 
                                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)

                                answerContent = userAnswer.content.lower()
                                
                                if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                                    editingAnswered = True
                                else: 
                                    await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
                            
                            if (answerContent == "no") or (answerContent == "n"):
                                doneEditing = True
                                
                        except asyncio.TimeoutError: 
                            log("updateRoutine() - User timed out providing dodoCode")
                            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                            return
                            
                    elif answerContent == "2":
                        log("updateRoutine() - User wants to update their duration")
                        # Update the Duration
                        await channel.send("How long, in hours, would you like this flight to be listed now?")
                        try: 
                            log("updateRoutine() - Waiting for user to give a duration")
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
                                
                            end_time = datetime.utcnow() + duration
                            user_flight.end_time = end_time
                            user_flight.setDuration(duration)
                            
                            # Check if the user wants to update something else
                            editingAnswered = False
                            answerContent = ""
                            
                            await channel.send("Do you want to change any other parts of the listing? Answer with 'yes' or 'no'")
                            while editingAnswered == False: 
                                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)

                                answerContent = userAnswer.content.lower()
                                
                                if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                                    editingAnswered = True
                                else: 
                                    await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
                            
                            if (answerContent == "no") or (answerContent == "n"):
                                doneEditing = True
                                
                        except asyncio.TimeoutError: 
                            log("updateRoutine() - User timed out providing dodoCode")
                            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                            return
                        
                    elif answerContent == "3": 
                        log("updateRoutine() - User wants to update their extra info")
                        # Update the Extra Information
                        await channel.send("What would you like to change the extra information in the listing to? If you don't have anything to add, just reply with 'None'")
                        try: 
                            log("updateRoutine() - Waiting for user to give extra information")
                            userAnswer = await client.wait_for('message', check=inputCheckValidURL, timeout=600.0)
                            extra = str(userAnswer.content)
                                
                            user_flight.extra = extra
                            
                            # Check if the user wants to update something else
                            editingAnswered = False
                            answerContent = ""
                            
                            await channel.send("Do you want to change any other parts of the listing? Answer with 'yes' or 'no'")
                            while editingAnswered == False: 
                                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)

                                answerContent = userAnswer.content.lower()
                                
                                if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                                    editingAnswered = True
                                else: 
                                    await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
                            
                            if (answerContent == "no") or (answerContent == "n"):
                                doneEditing = True
                                
                        except asyncio.TimeoutError: 
                            log("updateRoutine() - User timed out providing dodoCode")
                            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 10 minutes when prompted. Send me a message saying 'Update' if you want to try again.")
                            return
                        
                    else: 
                        # Invalid Input
                        await channel.send("Wuh-oh! Please reply with just the single number of the option you wish to select e.g. '1'")
                        
            # Check that the user likes the new post
            log("updateRoutine() - Confirming the user's update")
            await channel.send("With your updates, the flight listing will look like this: " )
            await channel.send(user_flight.generateMessage())
            await channel.send("Would you like to post this modifed version? Please reply with 'yes' or 'no'")
            
            flightAnswer = False
            answerContent = "" 
            while flightAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                        flightAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if (answerContent == "no") or (answerContent == "n"): 
                # Leave the flight listing as is
                await channel.send("OK, I'll leave your flight listing the way it is.")
                return
                
            # Delete the existing message
            log("updateRoutine() - deleting existing flight listing")
            await deleteMessage(existing_flight[FlightDB.MESSAGE_ID_COL], channel) 
            
            # Send the message
            log("updateRoutine() - sending updated message")
            listing_channel = client.get_channel(existing_flight[FlightDB.CHANNEL_ID_COL])
            listingMessage = await listing_channel.send(user_flight.generateMessage())
            user_flight.setMessageID(listingMessage.id)
            
            # Add the flight to the database
            log("updateRoutine() - adding updated flight to database")
            FlightDB.insert(existing_flight[FlightDB.USER_ID_COL], existing_flight[FlightDB.SERVER_ID_COL], existing_flight[FlightDB.CHANNEL_ID_COL], listingMessage.id, user_flight.playerName, user_flight.island, user_flight.end_time, user_flight.code, user_flight.extra)
            
            await channel.send("All set! Your listing has been updated.")
            
        # Handle an update to their move listing    
        if move_update_flag: 
            log("updateRoutine() - Updating the user's move listing")
            
            # Make a move object from existing_move
            user_move = Move(existing_move[MoveDB.USER_ID_COL], existing_move[MoveDB.PLAYER_NAME_COL], existing_move[MoveDB.VILLAGER_COL], existing_move[MoveDB.END_TIME_COL], existing_move[MoveDB.EXTRA_COL])
            
            # Display the current move and make sure the user wants to update it
            await channel.send("It looks like you have the following move: " )
            await channel.send(user_move.generateMessage())
            await channel.send("Would you like to modify it? Please reply with 'yes' or 'no'")
            
            moveAnswer = False
            answerContent = "" 
            while moveAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                        moveAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if (answerContent == "no") or (answerContent == "n"): 
                # Don't perform any updates
                await channel.send("OK, I'll leave your move listing the way it is.")
                return
                
            # Loop, allowing the user to modify an aspect of the move with each iteration until the done
            doneEditing = False
            answerContent = ""
            while doneEditing == False: 
                # Determine which part of the move to update
                selectMessage = """What part of the move listing would you like to change?
    1. Duration
    2. Extra Information
    Please answer with the number of the option you want."""
                await channel.send(selectMessage)
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                    answerContent = userAnswer.content.lower()
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    
                    if answerContent == "1":
                        log("updateRoutine() - User wants to update their duration")
                        # Update the Duration
                        await channel.send("How long, in hours, would you like this move to be listed now?")
                        try: 
                            log("updateRoutine() - Waiting for user to give a duration")
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
                                
                            end_time = datetime.utcnow() + duration
                            user_move.end_time = end_time
                            user_move.duration = duration
                            
                            # Check if the user wants to update something else
                            editingAnswered = False
                            answerContent = ""
                            
                            await channel.send("Do you want to change any other parts of the listing? Answer with 'yes' or 'no'")
                            while editingAnswered == False: 
                                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)

                                answerContent = userAnswer.content.lower()
                                
                                if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                                    editingAnswered = True
                                else: 
                                    await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
                            
                            if (answerContent == "no") or (answerContent == "n"):
                                doneEditing = True
                                
                        except asyncio.TimeoutError: 
                            log("updateRoutine() - User timed out providing dodoCode")
                            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                            return
                        
                    elif answerContent == "2": 
                        log("updateRoutine() - User wants to update their extra info")
                        # Update the Extra Information
                        await channel.send("What would you like to change the extra information in the listing to? If you don't have anything to add, just reply with 'None'")
                        try: 
                            log("updateRoutine() - Waiting for user to give extra information")
                            userAnswer = await client.wait_for('message', check=inputCheckValidURL, timeout=600.0)
                            extra = str(userAnswer.content)
                                
                            user_move.extra = extra
                            
                            # Check if the user wants to update something else
                            editingAnswered = False
                            answerContent = ""
                            
                            await channel.send("Do you want to change any other parts of the listing? Answer with 'yes' or 'no'")
                            while editingAnswered == False: 
                                userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)

                                answerContent = userAnswer.content.lower()
                                
                                if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                                    editingAnswered = True
                                else: 
                                    await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
                            
                            if (answerContent == "no") or (answerContent == "n"):
                                doneEditing = True
                                
                        except asyncio.TimeoutError: 
                            log("updateRoutine() - User timed out providing dodoCode")
                            await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 10 minutes when prompted. Send me a message saying 'Update' if you want to try again.")
                            return
                        
                    else: 
                        # Invalid Input
                        await channel.send("Wuh-oh! Please reply with just the single number of the option you wish to select e.g. '1'")
                        
            # Check that the user likes the new post
            log("updateRoutine() - Confirming the user's update")
            await channel.send("With your updates, the move listing will look like this: " )
            await channel.send(user_move.generateMessage())
            await channel.send("Would you like to post this modifed version? Please reply with 'yes' or 'no'")
            
            moveAnswer = False
            answerContent = "" 
            while moveAnswer == False: 
                try: 
                    userAnswer = await client.wait_for('message', check=inputCheck, timeout=30.0)
                except asyncio.TimeoutError: 
                    await channel.send("Wuh-oh! I didn't catch that. Make sure to answer within 30 seconds when prompted. Send me a message saying 'Update' if you want to try again.")
                    return
                else: 
                    answerContent = userAnswer.content.lower()
                    
                    if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                        moveAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if (answerContent == "no") or (answerContent == "n"): 
                # Leave the move listing as is
                await channel.send("OK, I'll leave your move listing the way it is.")
                return
                
            # Delete the existing message
            log("updateRoutine() - deleting existing move listing")
            await deleteMessage(existing_move[MoveDB.MESSAGE_ID_COL], channel) 
            
            # Send the message
            log("updateRoutine() - sending updated message")
            listing_channel = client.get_channel(existing_move[MoveDB.CHANNEL_ID_COL])
            listingMessage = await listing_channel.send(user_move.generateMessage())
            user_move.setMessageID(listingMessage.id)
            
            # Add the flight to the database
            log("updateRoutine() - adding updated flight to database")
            MoveDB.insert(existing_move[MoveDB.USER_ID_COL], existing_move[MoveDB.SERVER_ID_COL], existing_move[MoveDB.CHANNEL_ID_COL], listingMessage.id, user_move.playerName, user_move.end_time, user_move.villager, user_move.extra)
            
            await channel.send("All set! Your listing has been updated.")
                
    finally: 
        try: 
            active_sessions_lock.acquire()
            if user.id in active_sessions: 
                active_sessions.remove(user.id)
        finally: 
            active_sessions_lock.release()

# Will confirm that the user wishes to cancel their listing and, if 
# so, delete the associated message and listing database row. 
async def cancelRoutine(channel, user, serverID): 
    log("cancelRoutine() - Enter")
    
    # Functions used for checking input for user answers
    def inputCheck(checkMessage): 
        # Make sure this was a message sent as a DM by the same user
        if ((checkMessage.channel == channel) and (checkMessage.author == user)): 
            # Make sure the message does not contain a URLs
            if checkForNoUrl(checkMessage.content) == True: 
                return True
            else: 
                return False
                    
    try: 
        try: 
            active_sessions_lock.acquire()
            active_sessions.append(user.id)
        finally: 
            active_sessions_lock.release()
        
        existing_flight = FlightDB.select_user_server(user.id, serverID)
        existing_move = MoveDB.select_user_server(user.id, serverID)
        
        flight_delete_flag = (not existing_flight is None)
        move_delete_flag = (not existing_move is None)
        
        # If the user has neither a flight or delete, go no further
        if not flight_delete_flag and not move_delete_flag: 
            await channel.send("Wuh-oh! It doesn't look like you have any active listings.")
            return
        
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
            user_flight = Flight(existing_flight[FlightDB.USER_ID_COL], existing_flight[FlightDB.PLAYER_NAME_COL], existing_flight[FlightDB.ISLAND_NAME_COL], existing_flight[FlightDB.END_TIME_COL], existing_flight[FlightDB.DODO_CODE_COL], existing_flight[FlightDB.EXTRA_COL])
            await channel.send("It looks like you have the following flight: " )
            await channel.send(user_flight.generateMessage())
            await channel.send("Would you like to delete it? Please reply with 'yes' or 'no'")
            
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
                    
                    if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                        flightAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if (answerContent == "yes") or (answerContent == "y"): 
                # Delete the flights message
                await deleteMessage(existing_flight[FlightDB.MESSAGE_ID_COL], channel) 
                await channel.send("OK! Your previous flight listing has been canceled.")
                    
            else: 
                await channel.send("OK, I'll leave your flight listing in place, then.")
                return
            
        if move_delete_flag: 
            # User only has an active move they want deleted
            log("cancelRoutine() - User has only an active move")
            user_move = Move(existing_move[MoveDB.USER_ID_COL], existing_move[MoveDB.PLAYER_NAME_COL], existing_move[MoveDB.VILLAGER_COL], existing_move[MoveDB.END_TIME_COL], existing_move[MoveDB.EXTRA_COL])
            await channel.send("It looks like you have the following move listing: ")
            await channel.send(user_move.generateMessage())
            await channel.send("Would you like to delete it? Please reply with 'yes' or 'no'")
            
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
                    
                    if (answerContent == "yes") or (answerContent == "y") or (answerContent == "no") or (answerContent == "n"): 
                        moveAnswer = True
                    else: 
                        await channel.send("Wuh-oh! Please reply with either 'yes' or 'no' only.")
            
            if (answerContent == "yes") or (answerContent == "y"): 
                # Delete the move's message
                await deleteMessage(existing_move[MoveDB.MESSAGE_ID_COL], channel) 
                await channel.send("OK! Your previous move listing has been canceled.")
                    
            else: 
                await channel.send("OK, I'll leave your move listing in place, then.")
                return
    
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
**Update:** Answer some questions and I'll update one of your existing flight or move listings. 
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
    # Start the cleanup thread 
    cleanupThreadFunction.start()
    
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
                await flightRoutine(message.channel, message.author, int(serverConfig.attrib['id']), int(flightConfig.attrib['channelID']))
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
                await moveRoutine(message.channel, message.author, int(serverConfig.attrib['id']), int(moveConfig.attrib['channelID']))
            else: 
                log("on_message() - move called by user with incorrect roles")
                await message.channel.send("Wuh-oh! Looks like you don't have the right role to use this command.")
            
        elif "update" == messageContent: 
            # Get the "server" config information for where this listing would go
            serverConfig = await confirmServer(message.channel, message.author)
            await updateRoutine(message.channel, message.author, int(serverConfig.attrib['id']))
            
        elif "cancel" == messageContent: 
            # Get the "server" config information for where this listing would go
            serverConfig = await confirmServer(message.channel, message.author)
            await cancelRoutine(message.channel, message.author, int(serverConfig.attrib['id']))
                
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
            

# Get the directory the script is in as the botToken.txt and wilbot_config.xml files
# are expected to be in the same directory with it. 
execDir = os.path.dirname(os.path.realpath(__file__))

# Retrieve wilbot's Bot Token from the botToken.txt file
tokenFile = open(execDir + '/botToken.txt')
token = tokenFile.readline()
tokenFile.close()

# Load the configuration xml file
configXML = ET.parse(execDir + '/wilbot_config.xml')

# Open or initialize the database file
try: 
    if os.path.isfile(execDir + '/wilbot.db'): 
        log("Database already exists")
        
    else: 
        log("initializing database")
        UserDB.initialize()
        FlightDB.initialize()
        MoveDB.initialize()
        
        log("initialization complete!")
    
except Exception as ex: 
    log("Unable to initialize the database")
    log(str(ex))

# Start Wilbot!
client.run(token)
        
log("post client.run")
