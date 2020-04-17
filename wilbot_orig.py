import discord
from datetime import *
import asyncio
import threading
import time

# Old version used to get used to the discord.py module
# Can be ignored

client = discord.Client()
botspam_channel_ID = 573707326976950272
cactus_enamel_ID = 417518570206003206
cactus_enamel_officer_role_ID = 567949934587019266
active_sessions = []
user_message_map = {}

# Simple print wrapper to make log lines a little cleaner
def log(logMessage): 
    print(logMessage, flush=True)
    
    
# Cleanup thread. Runs in the background and cleans up expired listings
def cleanupThreadFunction(): 
    while True: 
        #log("cleanupThreadFunction() - running")
        time.sleep(30)

# Sends a "Hello!" to the channel supplied
async def sendHelloWorld(channel): 
    log("sendHellowWorld() - Sending hello message")
    
    await channel.send("World!") 
    
    log("sendHellowWorld() - hello message sent")
        

# wait for user to send ok message and reply with roger when they do
async def handleTest(message): 
    def testCheck1(checkMessage): 
        log("testCheck1() - " + str(checkMessage))
        return checkMessage.content == "ok" and checkMessage.channel == message.channel and checkMessage.author == message.author
    
    def testCheck2(checkMessage): 
        log("testCheck2() - " + str(checkMessage))
        return checkMessage.channel == message.channel and checkMessage.author == message.author
    
    def testCheck3(checkMessage): 
        log("testCheck3() - " + str(checkMessage))
        return checkMessage.channel == message.channel and checkMessage.author == message.author
    
    try: 
        await message.channel.send('Tell me "ok"')
            
        try: 
            log("handleTest() - waiting for user to say ok")
            await client.wait_for('message', check=testCheck1, timeout=15.0)
        except asyncio.TimeoutError: 
            await message.channel.send("Sorry, I didn't catch that")
        else: 
            
            await message.channel.send("Roger! Now tell me your island's name")
            
            try: 
                log("handleTest() - waiting for user to give an island name")
                userIslandNameMessage = await client.wait_for('message', check=testCheck2, timeout=15.0)
                islandName = str(userIslandNameMessage.content)
            except asyncio.TimeoutError: 
                await message.channel.send("Sorry, I didn't catch your name there.")
            else: 
            
                await message.channel.send( islandName + " was it? Great! And lastly, can you tell me the code for your town?")
                
                try: 
                    log("handleTest() - waiting for user to give a code")
                    userCodeMessage = await client.wait_for('message', check=testCheck3, timeout=15.0)
                    userCode = str(userCodeMessage.content)
                except asyncio.TimeoutError: 
                    await message.channel.send("Sorry, I didn't hear a code in time.")
                else: 
                    await message.channel.send("Got it! " + userCode + " it is. Alright, I'll post your listing in #bot-spam then.")
                    botspam_channel = client.get_channel(botspam_channel_ID)
                    newMessage = await botspam_channel.send("Now booking flights to " + islandName + "\n" + \
                                               "Use the code " + userCode + " at Dodo Airlines to get your ticket", delete_after=30.0)
                    user_message_map[message.author] = newMessage
    finally: 
        if message.author in active_sessions: 
            active_sessions.remove(message.author)

async def handleDelete(message): 
    log("handleDelete() - Entering function")
    botspam_channel = client.get_channel(botspam_channel_ID)
    
    def deleteCheck(checkMessage): 
        log("deleteCheck() - " + str(checkMessage))
        return checkMessage.channel == message.channel and checkMessage.author == message.author
        
    await message.channel.send('Tell me the message ID of the post of mine you want deleted')
        
    try: 
        log("handleDelete() - waiting for user to provide the message ID")
        messageToDeleteIDMessage = await client.wait_for('message', check=deleteCheck, timeout=15.0)
    except asyncio.TimeoutError: 
        await message.channel.send("Sorry, I didn't catch that")
    else: 
        # delete the message
        msgID = messageToDeleteIDMessage.content
        #botspam_channel = client.get_channel(botspam_channel_ID)
        try: 
            messageToDelete = await botspam_channel.fetch_message(msgID)
        except Exception as ex: 
            log("handleDelete() - failed to retrieve a message: " + str(ex))
            await message.channel.send("Sorry, I couldn't find a message with that ID")
        else: 
            log("handleDelete() - found a matching message: " + str(messageToDelete))
            if messageToDelete.author == client.user: 
                try: 
                    log("handleDelete() - Deleting message with ID " + msgID)
                    if messageToDelete in user_message_map.values(): 
                        for u, m in user_message_map: 
                            if messageToDelete == m: 
                                del user_message_map[u]
                    await messageToDelete.delete()
                    await message.channel.send("Message deleted")
                except Exception as ex: 
                    log("handleDelete() - failed to delete a message: " + str(ex))
                    await message.channel.send("Failed to delete the message")
            else: 
                log("handleDelete() - Wilbot did not create the message you're trying to delete.")
                await message.channel.send("Sorry, I didn't write the message you're trying to delete")

# when we get this command, make a post in the cactus enamel botspam channel
async def handlePost(message): 
    botspam_channel = client.get_channel(botspam_channel_ID)
    
    await botspam_channel.send(str(message.author) + " told me to post here")

async def handleClose(message): 
    log("handleClose() - enter function")
    messageToDelete = user_message_map[message.author]
    log("handleClose() - messagetoDelete is: " + str(messageToDelete))
    await messageToDelete.delete()
    del user_message_map[message.author]
    await message.channel.send("OK, we'll remove your listing for flights to your island")

# Sends a message with instructions for using Wilbot to the channel supplied
async def sendHelp(channel): 
    log("sendHelp() - Sending help message")
    
    helpMessage = """I can perform the following functions: 
**Hello, World:** Send me a message including "Hello" and I'll reply with "World!"
**Test:** Run a demo version of the island posting feature
**Post:** Create a post in the bot-spam channel
**Delete:** Delete a post that Wilbot has made
**Help:** Prints this helpful help message

Make sure to send Wilbot instructions in a Direct Message"""
    await channel.send(helpMessage) 
    
    log("sendHelp() - help message sent")

################ Event Handlers ################

# Process the event raised when the bot has started up fully
@client.event
async def on_ready():
    log("Starting cleanupThreadFunction")
    cleanupThread = threading.Thread(target=cleanupThreadFunction, daemon=True)
    cleanupThread.start()
    log("Wilbot is online!")

# Process any new message that gets sent in the server
@client.event
async def on_message(message):
    
    
    # Ignore all messages sent by Wilbot so it doesn't 
    # ever get stuck in a loop
    if message.author == client.user:
        return
    
    # Check if this was a private message
    # Wilbot only deals in Direct Messages so most others will be ignored
    if message.channel.type is discord.ChannelType.private: 
        log("on_message() - Received a Direct Message: " + message.content)
        
        # Put the message in lower case to simplify parsing
        messageContent = message.content.lower()
        
        if "hello" in messageContent:
            log("on_message() - Running the Hello, World routine")
            await sendHelloWorld(message.channel)
        
        elif "test" in messageContent: 
            # Check if the message author is a member of the cactus enamel server and that they're not already using Wilbot
            cactus_enamel_guild = client.get_guild(cactus_enamel_ID)
            if message.author in cactus_enamel_guild.members and message.author not in active_sessions: 
                log("on_message() - running the test routine")
                log("DEBUG the user has the following id: " + str(message.author.id))
                log("DEBUG the user has tehe following roles: " + str(cactus_enamel_guild.get_member(message.author.id).roles))
                officer_role = cactus_enamel_guild.get_role(cactus_enamel_officer_role_ID)
                if officer_role in cactus_enamel_guild.get_member(message.author.id).roles: 
                    active_sessions.append(message.author)
                    await handleTest(message)
                else: 
                    log("DEBUG non officer tried to use the bot")
            
        elif "post" in messageContent: 
            log("on_message() - running the post routine")
            await handlePost(message)
            
        elif "close" in messageContent: 
            if message.author in user_message_map.keys(): 
                log("on_message() - running the close routine")
                await handleClose(message)
            else: 
                log("on_message() - tried to close without active island")
                await message.channel.send("It doesn't look like you have any available flights to your island")
        
        # delete a posting
        elif "delete" in messageContent: 
            log("on_message() - running the delete routine")
            await handleDelete(message)
            
        if ("help" == messageContent): 
            log("on_message() - Running the help routine")
            await sendHelp(message.channel)
        
    # Check if the message mentions Wilbot and work 
    # on those that do
    if client.user in message.mentions:
        log("on_message() - Wilbot's User ID was mentioned")
        
        messageContent = message.content.lower()
            
        if ("help" in messageContent): 
            log("on_message() - Running the help routine")
            await sendHelp(message.channel)
            

client.run("Njk2ODc2MzI3Mzg2NzQyODU1.XovHKw.RNpRqYdkZ_2sOA817oACaFEl--U")
