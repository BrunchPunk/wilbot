import sqlite3

# Class encapuslating all the functionality needed to use the 
# "user" table in the Wilbot Database. The class's methods and 
# members are all static so instantiation of the class is not 
# required. 
# This table is meant to contain information about each user 
# who has made a listing with Wilbot. This information will be 
# retained between listings to speed up listings after the first

# The User Table is composed of the following columns: 
# 
# user_id: (INTEGER) The numeric Discord user ID for the user. This is the tables primary key. 
# game_name: (TEXT) The Animal Crossing in game name for the user
# island_name: (TEXT) The Animal Crossing island name for the user
# dream_code: (TEXT) The Animal Crossing dream code for the user

class UserDB: 
    
    create_sql = """CREATE TABLE IF NOT EXISTS user(user_id INTEGER PRIMARY KEY, game_name TEXT, island_name TEXT, dream_code TEXT);"""
    insert_sql = """INSERT INTO user(user_id, game_name, island_name, dream_code) VALUES (?, ?, ?, ?);"""
    delete_sql = """DELETE FROM user WHERE user_id=?;"""
    update_sql = """UPDATE user SET game_name=?, island_name=?, dream_code=? WHERE user_id=?;"""
    
    def initialize():
        db_conn = sqlite3.connect('wilbot.db')
        db_cursor = db_conn.cursor()
        
        db_cursor.execute(UserDB.create_sql)
        
        db_conn.commit()
        db_conn.close()
    
    def insert(user_id, game_name, island_name): 
        db_conn = sqlite3.connect('wilbot.db')
        db_cursor = db_conn.cursor()
        
        db_cursor.execute(UserDB.insert_sql, (user_id, game_name, island_name))
        
        db_conn.commit()
        db_conn.close()
        
    def delete(user_id): 
        db_conn = sqlite3.connect('wilbot.db')
        db_cursor = db_conn.cursor()
        
        db_cursor.execute(UserDB.delete_sql, (user_id))
        
        db_conn.commit()
        db_conn.close()
        
    def update(user_id, game_name, island_name, dream_code): 
        db_conn = sqlite3.connect('wilbot.db')
        db_cursor = db_conn.cursor()
        
        db_cursor.execute(UserDB.update_sql, (game_name, island_name, dream_code, user_id))
        
        db_conn.commit()
        db_conn.close()