import discord
from discord import app_commands
from discord.ext import commands, tasks
from perplexity import Perplexity
import json
import logging
import traceback
import re

perplexity = Perplexity()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('discord_bot')

OWNER_ID = 1123534156626939945

def split_message(message, max_length=2000):
    parts = []
    current_part = ""
    
    for line in message.split('\n'):
        if len(current_part) + len(line) + 1 > max_length:
            if current_part:
                parts.append(current_part.strip())
                current_part = ""
        current_part += line + '\n'
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts

async def send_long_message(channel, message):
    parts = split_message(message)
    
    for i, part in enumerate(parts):
        if i == 0:
            await channel.send(part)
        else:
            await channel.send(f"Suite ({i+1}/{len(parts)}):\n{part}")

async def send_error_to_owner(error_message):
    owner = await bot.fetch_user(OWNER_ID)
    if owner:
        await owner.send(f"Erreur détectée :\n```\n{error_message}\n```")

@bot.event
async def on_ready():
    logger.info(f"Le bot {bot.user} est connecté et prêt !")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synchronisé {len(synced)} commande(s)")
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation des commandes : {e}")
        await send_error_to_owner(f"Erreur lors de la synchronisation des commandes : {e}")

def format_references(text):
    def replace_ref(match):
        ref_num = match.group(1)
        return f"[{ref_num}](https://perplexity.ai/search?q=ref{ref_num})"
    
    return re.sub(r'\[(\d+)\]', replace_ref, text)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if bot.user.mentioned_in(message):
        query = message.content.replace(f'<@{bot.user.id}>', '').strip()
        logger.info(f"Requête reçue de {message.author}: {query}")
        try:
            async with message.channel.typing():
                result = perplexity.search_sync(query+" ?", mode="concise")
            if result and 'text' in result:
                json_result = json.loads(result['text'])
                if 'answer' in json_result:
                    formatted_answer = format_references(json_result['answer'])
                    await send_long_message(message.channel, formatted_answer)
                    logger.info(f"Réponse envoyée à {message.author}")
                else:
                    await message.channel.send("Je n'ai pas trouvé de réponse à votre question.")
                    logger.warning(f"Pas de réponse trouvée pour la requête: {query}")
            else:
                await message.channel.send("Je n'ai pas pu obtenir de résultat.")
                logger.warning(f"Pas de résultat obtenu pour la requête: {query}")
        except Exception as e:
            error_message = f"Erreur lors de la recherche Perplexity : {e}\n{traceback.format_exc()}"
            logger.error(error_message)
            await message.channel.send("Désolé, une erreur s'est produite lors du traitement de votre demande.")
            await send_error_to_owner(error_message)

@bot.event
async def on_error(event, *args, **kwargs):
    error_message = f"Erreur non gérée dans l'événement {event}:\n{traceback.format_exc()}"
    logger.error(error_message)
    await send_error_to_owner(error_message)

try:
    bot.run("TOKEN")
except Exception as e:
    error_message = f"Erreur fatale lors du démarrage du bot : {e}\n{traceback.format_exc()}"
    logger.critical(error_message)
    print(error_message)
