import sqlite3
from move import * 

# Class encapuslating all the functionality needed to use the 
# "move" table in the Wilbot Database. The class's methods and 
# members are all static so instantiation of the class is not 
# required. 
# This table is meant to contain information about each move 
# that is currently listed with Wilbot. 

# The Move Table is composed of the following columns: 
# 
# user_id: (INTEGER) The numeric Discord user ID for the user. This (in conjunction with server_id) is the tables primary key. It is a foreign key reference to user_id in the user table. 
# server_id: (INTEGER) The numeric Discord server ID for the server where this move was listed. This (in conjunction with user_id) is the tables primary key. 
# channel_id: (INTEGER) The numeric Discord channel ID for the channel where the message for this move was posted. 
# message_id: (INTEGER) The numeric Discord message ID for the message posted for this move listing. 
# player_name: (TEXT) The user's character name in Animal Crossing
# end_time: (TIMESTAMP) The date and time when the listing should be automatically removed
# villager: (TEXT) The name of the villager who is moving in this listing
# extra: (TEXT) Any extra information the user provided about this listing

class MoveDB: 
    # Constants defining the column position for each value
    USER_ID_COL = 0
    SERVER_ID_COL = 1
    CHANNEL_ID_COL = 2
    MESSAGE_ID_COL = 3
    PLAYER_NAME_COL = 4
    END_TIME_COL = 5
    VILLAGER_COL = 6
    EXTRA_COL = 7
    
    create_sql = """CREATE TABLE IF NOT EXISTS move(user_id INTEGER NOT NULL, server_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id  INTEGER NOT NULL, player_name TEXT NOT NULL, end_time TIMESTAMP NOT NULL, villager TEXT NOT NULL, extra TEXT, PRIMARY KEY(user_id, server_id), FOREIGN KEY(user_id) REFERENCES user(user_id));"""
    insert_sql = """INSERT INTO move(user_id, server_id, channel_id, message_id, player_name, end_time, villager, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?);"""
    delete_sql = """DELETE FROM move WHERE user_id=? AND server_id=?;"""
    update_sql = """UPDATE move SET message_id=?, end_time=?, villager=?, extra_info=? WHERE user_id=? AND server_id=?;"""
    select_user_server_sql = """SELECT * FROM move WHERE user_id=? AND server_id=?;"""
    select_message_sql = """SELECT * FROM move WHERE message_id=?;"""
    selectAll_sql = """SELECT * FROM move;"""
    
    def initialize():
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.create_sql)
            
        finally: 
            db_conn.commit()
            db_conn.close()
    
    def insert(user_id, server_id, channel_id, message_id, player_name, end_time, villager, extra): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.insert_sql, (user_id, server_id, channel_id, message_id, player_name, end_time, villager, extra))
            
        finally: 
            db_conn.commit()
            db_conn.close()
        
    def delete(user_id, server_id): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.delete_sql, (user_id, server_id))
            
        finally: 
            db_conn.commit()
            db_conn.close()
        
    def update(user_id, server_id, message_id, end_time, dodo_code, extra): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.update_sql, (message_id, end_time, dodo_code, extra, user_id, server_id))
            
        finally: 
            db_conn.commit()
            db_conn.close()
        
    def select_user_server(user_id, server_id): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.select_user_server_sql, (user_id, server_id))
            
            return db_cursor.fetchone()
            
        finally: 
            db_conn.commit()
            db_conn.close()
            
    def select_message(message_id): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.select_message_sql, (message_id,))
            
            return db_cursor.fetchone()
            
        finally: 
            db_conn.commit()
            db_conn.close()
            
    def selectAll(): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(MoveDB.selectAll_sql)
            
            return db_cursor.fetchall()
            
        finally: 
            db_conn.commit()
            db_conn.close()