import discord
from discord import app_commands
import json
from . import db

async def owner_check(interaction, character):
    user_id = str(interaction.user.id)
    if user_id != character['owner_id']:
        await interaction.followup.send("You are not the owner of this character.", ephemeral=True)
        return False
    return True

async def allowed_users_check(interaction, character, send_followup=True):
    user_id = str(interaction.user.id)
    if user_id not in character['allowed_users']:
        if send_followup:
            await interaction.followup.send("You do not have permission to use this character.", ephemeral=True)
        return False
    return True

def get_character(guild_id, name):
    connection = db.create_oracle_connection()
    cursor = connection.cursor()

    cursor.execute('''
        SELECT id, character_name, owner_id, image_url, background, allowed_users
        FROM characters
        WHERE guild_id = :guild_id AND character_name = :name
    ''', {"guild_id": guild_id, "name": name})

    character = cursor.fetchone()
    if character:
        character = {
            "id": character[0],
            "name": character[1],
            "owner_id": character[2],
            "image_url": character[3],
            "background": character[4],
            "allowed_users": json.loads(character[5].read())
        }

    cursor.close()
    connection.close()
    return character

@app_commands.command(name='create_character', description="Create a character specific to this guild.")
@app_commands.describe(
    name="The name of the character to edit (50 character limit)",
    image_url="Image URL for the character",
    background="New description for the character (1000 character limit)"
)
async def create_character(interaction: discord.Interaction, name: str, image_url: str, *, background: str):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)

    if get_character(guild_id, name):
        await interaction.followup.send(f"A character with the name '{name}' already exists in this guild!", ephemeral=True)
        return

    user = interaction.user
    user_id = str(user.id) 

    try:
        connection = db.create_oracle_connection()
        cursor = connection.cursor()
        cursor.execute('''
            INSERT INTO characters (guild_id, character_name, owner_id, image_url, background, allowed_users)
            VALUES (:guild_id, :name, :owner_id, :image_url, :background, :allowed_users)
        ''', {
            "guild_id": guild_id, 
            "name": name, 
            "owner_id": user_id, 
            "image_url": image_url, 
            "background": background, 
            "allowed_users": json.dumps([user_id])
        })
        connection.commit()
        await interaction.followup.send(f"Character '{name}' created and saved for this guild.", ephemeral=True)
        await db.export_characters(interaction, send_messages=False)
    except Exception as e:
        await interaction.followup.send(f"Failed to create character due to an error: {str(e)}", ephemeral=True)
    finally:
        cursor.close()
        connection.close()

@app_commands.command(name='delete_character', description="Delete a character from this guild.")
async def delete_character(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    character = get_character(guild_id, name)
    if not character:
        await interaction.followup.send(f"Character '{name}' does not exist in this guild.", ephemeral=True)
        return

    if not await owner_check(interaction, character):
        return

    try: 
        connection = db.create_oracle_connection()
        cursor = connection.cursor()
        cursor.execute('''
            DELETE FROM characters
            WHERE guild_id = :guild_id AND character_name = :name
        ''', {"guild_id": guild_id, "name": name})
        connection.commit()
        await interaction.followup.send(f"Character '{name}' has been deleted.", ephemeral=True)
        await db.export_characters(interaction, send_messages=False)
    except Exception as e:
        await interaction.followup.send(f"Failed to delete character due to an error: {str(e)}", ephemeral=True)
    finally:
        cursor.close()
        connection.close()

class ConfirmDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, custom_id="confirm_delete_all_characters")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild_id)
        connection = db.create_oracle_connection()
        cursor = connection.cursor()
        cursor.execute('''
            DELETE FROM characters
            WHERE guild_id = :guild_id
        ''', {"guild_id": guild_id})
        connection.commit()
        cursor.close()
        connection.close()
        # send empty json to backup channel, but leave older messages for recovery
        private_channel = discord.utils.get(interaction.guild.text_channels, name=BACKUP_CHANNEL)
        if private_channel:
            await db.export_json_to_channel(private_channel, {})
        await interaction.response.send_message("All characters have been deleted from this guild.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_delete_all_characters")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Deletion of all characters has been cancelled.", ephemeral=True)
        self.stop()

@app_commands.command(name='delete_all_characters', description="Delete all characters from this guild.")
async def delete_all_characters(interaction: discord.Interaction):
    view = ConfirmDeleteView()
    await interaction.response.send_message("Are you sure you want to delete all characters in this guild?", ephemeral=True, view=view)

@app_commands.command(name='edit_character', description="Edit a character's information.")
@app_commands.describe(
    name="The name of the character to edit",
    new_name="New name for the character (optional)",
    image_url="Image URL for the character (optional)",
    background="New description for the character (optional)"
)
async def edit_character(interaction: discord.Interaction, name: str, new_name: str = None, image_url: str = None, background: str = None):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    character = get_character(guild_id, name)
    if not character:
        await interaction.followup.send(f"Character '{name}' does not exist in this guild.", ephemeral=True)
        return

    if not await allowed_users_check(interaction, character):
        return

    if image_url:
        character['image_url'] = image_url
    if background:
        character['background'] = background
    if new_name:
        character['name'] = new_name
        name = new_name

    try:
        connection = db.create_oracle_connection()
        cursor = connection.cursor()
        cursor.execute('''
            UPDATE characters
            SET character_name = :new_name, image_url = :image_url, background = :background
            WHERE guild_id = :guild_id AND character_name = :name
        ''', {
            "new_name": character['name'], 
            "image_url": character['image_url'], 
            "background": character['background'], 
            "guild_id": guild_id, 
            "name": name
        })
        connection.commit()
        await interaction.followup.send(f"Character '{name}' has been updated.", ephemeral=True)
        await db.export_characters(interaction, send_messages=False)
    except Exception as e:
        await interaction.followup.send(f"Failed to update character due to an error: {str(e)}", ephemeral=True)
    finally:
        cursor.close()
        connection.close()

@app_commands.command(name='allow_character', description="Allow another user to use a character in this guild.")
async def allow_character(interaction: discord.Interaction, character_name: str, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    character = get_character(guild_id, character_name)
    
    if not character:
        await interaction.followup.send(f"Character '{character_name}' does not exist in this guild.", ephemeral=True)
        return
        
    if not await owner_check(interaction, character):
        return
    
    character['allowed_users'].append(str(user.id))
    try:
        connection = db.create_oracle_connection()
        cursor = connection.cursor()
        cursor.execute('''
            UPDATE characters
            SET allowed_users = :allowed_users
            WHERE guild_id = :guild_id AND character_name = :name
        ''', {
            "allowed_users": json.dumps(character['allowed_users']), 
            "guild_id": guild_id, 
            "name": character_name
        })
        connection.commit()
        await interaction.followup.send(f"User {user.name} can now use the character '{character_name}' in this guild.", ephemeral=True)
        await db.export_characters(interaction, send_messages=False)
    except Exception as e:
        await interaction.followup.send(f"Failed to allow user due to an error: {str(e)}", ephemeral=True)
        return
    finally:
        cursor.close()
        connection.close()

@app_commands.command(name='view_character', description="View a character's information.")
async def view_character(interaction: discord.Interaction, character_name: str):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    character = get_character(guild_id, character_name)
    
    if not character:
        await interaction.followup.send(f"Character '{character_name}' does not exist in this guild.", ephemeral=True)
        return

    if not await allowed_users_check(interaction, character):
        return
    
    channel = interaction.channel
    await db.export_json_to_channel(channel, {character_name: character})
    msg = await interaction.followup.send('Success!', ephemeral=True)
    await msg.delete(delay=2)
    