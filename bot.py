import discord
from discord.ext import commands
from commands import * 
from db_migrations import run_migrations
import os
import time

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

### START UP ###
@bot.event
async def on_ready():
    await bot.tree.sync()  # Sync the / commands with Discord
    create_character_table()

    run_migrations.main()

def create_character_table():
    connection = create_oracle_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT table_name 
        FROM user_tables 
        WHERE table_name = 'CHARACTERS'
    ''')
    table_exists = cursor.fetchone()
    
    if not table_exists:
        cursor.execute('''
            CREATE TABLE characters (
                guild_id VARCHAR2(50),
                character_name VARCHAR2(50),
                owner_id VARCHAR2(50),
                image_url VARCHAR2(255),
                background VARCHAR2(1000),
                allowed_users CLOB
            )
        ''')
        connection.commit()
    cursor.close()
    connection.close()
    print("Characters table created successfully.")

### CHARACTER COMMANDS ###
bot.tree.add_command(create_character)
bot.tree.add_command(delete_character)
bot.tree.add_command(delete_all_characters)
bot.tree.add_command(edit_character)
bot.tree.add_command(allow_character)
bot.tree.add_command(view_character)

### SENDING MESSAGES AS CHARACTERS ###
bot.tree.add_command(speak_as_character)

### CHARACTER DATA MANAGEMENT ###
bot.tree.add_command(init)
bot.tree.add_command(load_characters_from_message)
bot.tree.add_command(export_characters_manual)

### MERCHANT COMMANDS ###
bot.tree.add_command(add_inventory)
bot.tree.add_command(add_stock)
bot.tree.add_command(remove_inventory)
bot.tree.add_command(see_inventory)
bot.tree.add_command(buy_item)
bot.tree.add_command(edit_inventory)

bot.run(os.getenv('DISCORD_TOKEN'))
