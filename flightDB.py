import sqlite3
from flight import * 

# Class encapuslating all the functionality needed to use the 
# "flight" table in the Wilbot Database. The class's methods and 
# members are all static so instantiation of the class is not 
# required. 
# This table is meant to contain information about each flight 
# that is currently listed with Wilbot. 

# The Flight Table is composed of the following columns: 
# 
# user_id: (INTEGER) The numeric Discord user ID for the user. This (in conjunction with server_id) is the tables primary key. It is a foreign key reference to user_id in the user table. 
# server_id: (INTEGER) The numeric Discord server ID for the server where this flight was listed. This (in conjunction with user_id) is the tables primary key. 
# channel_id: (INTEGER) The numeric Discord channel ID for the channel where the message for this flight was posted. 
# message_id: (INTEGER) The numeric Discord message ID for the message posted for this flight listing. 
# player_name: (TEXT) The user's character name in Animal Crossing
# island_name: (TEXT) The name of the user's island in Animal Crossing
# end_time: (TIMESTAMP) The date and time when the listing should be automatically removed
# dodo_code: (TEXT) The Animal Crossing Dodo Code for this flight listing. 
# extra_info: (TEXT) Any extra information the user provided about this listing

# Potential concurrent access by multiple threads in wilbot is handled (inelegantly) by the calls to sqlite3.connect(). Since the
# "check_same_thread" argument it takes defaults to "true" and we aren't changing it, it will not allow another thread to make that 
# call if an update is currently being performed on the database. There is a configurable timeout the second thread will wait
# (the default is 5 seconds but can be changed with the "timeout" argument) after which it will throw an exception. This means 
# we're probably introducing a lot of unnecessary overhead connecting and disconnecting from the database repeatedly and there 
# is the risk that a query takes >5 seconds; but, the queries we're performing are -very- simple and I doubt the overhead is 
# significant at the frequency we're performing queries: A few per user interaction and a few per minute by the delete task. 
# If this approach proves insufficient, i'll have to go down the route of making a lock in the wilbot class the different 
# threads need to acquire before performing their operations and disableing the "check_same_thread" argument. 

class FlightDB: 
    # Constants defining the column position for each value
    USER_ID_COL = 0
    SERVER_ID_COL = 1
    CHANNEL_ID_COL = 2
    MESSAGE_ID_COL = 3
    PLAYER_NAME_COL = 4
    ISLAND_NAME_COL = 5
    END_TIME_COL = 6
    DODO_CODE_COL = 7
    EXTRA_COL = 8
    
    create_sql = """CREATE TABLE IF NOT EXISTS flight(user_id INTEGER NOT NULL, server_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id  INTEGER NOT NULL, player_name TEXT NOT NULL, island_name TEXT NOT NULL, end_time TIMESTAMP NOT NULL, dodo_code TEXT NOT NULL, extra TEXT, PRIMARY KEY(user_id, server_id), FOREIGN KEY(user_id) REFERENCES user(user_id));"""
    insert_sql = """INSERT INTO flight(user_id, server_id, channel_id, message_id, player_name, island_name, end_time, dodo_code, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"""
    delete_sql = """DELETE FROM flight WHERE user_id=? AND server_id=?;"""
    update_sql = """UPDATE flight SET message_id=?, end_time=?, dodo_code=?, extra_info=? WHERE user_id=? AND server_id=?;"""
    select_user_server_sql = """SELECT * FROM flight WHERE user_id=? AND server_id=?;"""
    select_message_sql = """SELECT * FROM flight WHERE message_id=?;"""
    selectAll_sql = """SELECT * FROM flight;"""
    
    def initialize():
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.create_sql)
            
        finally: 
            db_conn.commit()
            db_conn.close()
    
    def insert(user_id, server_id, channel_id, message_id, player_name, island_name, end_time, dodo_code, extra): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.insert_sql, (user_id, server_id, channel_id, message_id, player_name, island_name, end_time, dodo_code, extra))
            
        finally: 
            db_conn.commit()
            db_conn.close()
        
    def delete(user_id, server_id): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.delete_sql, (user_id, server_id))
            
        finally: 
            db_conn.commit()
            db_conn.close()
        
    def update(user_id, server_id, message_id, end_time, dodo_code, extra): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.update_sql, (message_id, end_time, dodo_code, extra, user_id, server_id))
            
        finally: 
            db_conn.commit()
            db_conn.close()

    def select_user_server(user_id, server_id): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.select_user_server_sql, (user_id, server_id))
            
            return db_cursor.fetchone()
            
        finally: 
            db_conn.commit()
            db_conn.close()
            
    def select_message(message_id): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.select_message_sql, (message_id,))
            
            return db_cursor.fetchone()
            
        finally: 
            db_conn.commit()
            db_conn.close()
        
    def selectAll(): 
        try: 
            db_conn = sqlite3.connect('wilbot.db', detect_types=sqlite3.PARSE_DECLTYPES)
            db_cursor = db_conn.cursor()
            
            db_cursor.execute(FlightDB.selectAll_sql)
            
            return db_cursor.fetchall()
            
        finally: 
            db_conn.commit()
            db_conn.close()