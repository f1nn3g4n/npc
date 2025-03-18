import discord
from discord import app_commands
import json
import os
import oracledb
import yaml

BACKUP_CHANNEL = 'npc-character-backup'

def load_config():
    with open("./db-info/config.yml", "r") as file:
        return yaml.safe_load(file)

config = load_config()

def create_oracle_connection():
    connection = oracledb.connect(
        user=config['oracle_db']['user'],
        password=config['oracle_db']['password'],
        dsn=config['oracle_db']['dsn'],
    )
    return connection

async def create_backup_channel(guild: discord.Guild):
    if discord.utils.get(guild.text_channels, name=BACKUP_CHANNEL):
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True, 
            attach_files=True
        )
    }
    channel = await guild.create_text_channel(BACKUP_CHANNEL, overwrites=overwrites)
    await channel.edit(topic="NPC-generated channel for storing character data backups.")


@app_commands.command(name="init", description="Init or refresh the character data from the backup channel")
async def init(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    private_channel = discord.utils.get(interaction.guild.text_channels, name=BACKUP_CHANNEL)
    if private_channel:
        # Fetch the last message from the private channel
        messages = [message async for message in private_channel.history(limit=1)]
        if messages:
            last_message = messages[0]
            try:
                await load_character_data(interaction, last_message)
            except json.JSONDecodeError:
                await interaction.followup.send("Failed to load character data. The data might be corrupted.", ephemeral=True)
        else:
            await interaction.followup.send("No backup message found in the private channel.", ephemeral=True)
    else:
        await interaction.followup.send("Backup channel not found, creating one.", ephemeral=True)
        await create_backup_channel(interaction.guild)
        await interaction.followup.send("Backup channel created. Add a character JSON to that channel and rerun command to upload.", ephemeral=True)

@app_commands.command(name="load_characters_from_message", description="Load characters from a JSON message")
@app_commands.describe(message_id="The ID of the message containing the JSON data")
async def load_characters_from_message(interaction: discord.Interaction, message_id: str):
    channel = interaction.channel
    await interaction.response.defer()
    try:
        message = await channel.fetch_message(int(message_id))
        load_character_data(interaction, message)  
    except Exception as e:
        await interaction.followup.send(f"Failed to load characters: {str(e)}", ephemeral=True)

async def load_character_data(interaction: discord.Interaction, message: discord.Message):
    if not message.attachments:
        await interaction.followup.send("No file attachments found in the message.", ephemeral=True)
        return

    # Assuming there's only one attachment
    attachment = message.attachments[0]

    file = await attachment.read()
    try:
        characters_data = json.loads(file.decode('utf-8'))
    except json.JSONDecodeError:
        await interaction.followup.send("The file content is not valid JSON.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    try:
        connection = create_oracle_connection()
        cursor = connection.cursor()
        for character_name, character_info in characters_data.items():        
            cursor.execute('''
                INSERT INTO characters (guild_id, character_name, owner_id, image_url, background, allowed_users)
                VALUES (:guild_id, :name, :owner_id, :image_url, :background, :allowed_users)
            ''', {
                'guild_id': guild_id,
                'name': character_name,
                'owner_id': character_info['owner_id'],
                'image_url': character_info.get('image_url', ''),
                'background': character_info.get('background', ''),
                'allowed_users': json.dumps(character_info.get('allowed_users', []))
            })
        connection.commit()
        await interaction.followup.send(f"Characters loaded successfully from message.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Failed to load characters: {str(e)}", ephemeral=True)
    finally:
        cursor.close()
        connection.close()
 
@app_commands.command(name="export_characters_manual", description="Export the list of characters as JSON to the back up channel")
async def export_characters_manual(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await export_characters(interaction)

async def export_characters(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    
    connection = create_oracle_connection()
    cursor = connection.cursor()
    
    cursor.execute('''
        SELECT character_name, owner_id, image_url, background, allowed_users
        FROM characters
        WHERE guild_id = :guild_id
    ''', {"guild_id": guild_id})
    
    characters = cursor.fetchall()
    
    if not characters or len(characters) == 0:
        await interaction.response.send_message("No characters to export.", ephemeral=True)
        cursor.close()
        connection.close()
        return

    characters_data = {}
    for character in characters:
        character_name, owner_id, image_url, background, allowed_users = character
        characters_data[character_name] = {
            "owner_id": owner_id,
            "image_url": image_url,
            "background": background,
            "allowed_users": json.loads(allowed_users.read())
        }
    cursor.close()
    connection.close()

    private_channel = discord.utils.get(interaction.guild.text_channels, name=BACKUP_CHANNEL)
    if private_channel:
        await export_json_to_channel(private_channel, characters_data)
        await interaction.followup.send("Characters exported successfully.", ephemeral=True)
    else:
        await interaction.followup.send("Backup channel not found. Please run /init", ephemeral=True)

async def export_json_to_channel(channel, data):
    with open("characters.json", "w") as f:
        json.dump(data, f, indent=4)

    await channel.send(file=discord.File("characters.json"))
    os.remove("characters.json")
