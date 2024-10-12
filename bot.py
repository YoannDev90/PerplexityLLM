import discord
from discord.ext import commands
from perplexity import Perplexity
import json

perplexity = Perplexity()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

async def send_long_message(channel, message):
    parts = [message[i:i+1900] for i in range(0, len(message), 1900)]
    
    for i, part in enumerate(parts):
        if i == 0:
            await channel.send(part)
        else:
            await channel.send(f"Suite ({i+1}/{len(parts)}):\n{part}")

@client.event
async def on_ready():
    print(f"Le bot {client.user} est connecté et prêt !")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if client.user.mentioned_in(message):
        query = message.content.replace(f'<@{client.user.id}>', '').strip()
        try:
            result = perplexity.search_sync(query+" ?", mode="concise")
            if result and 'text' in result:
                json_result = json.loads(result['text'])
                if 'answer' in json_result:
                    await send_long_message(message.channel, json_result['answer'])
                else:
                    await message.channel.send("Je n'ai pas trouvé de réponse à votre question.")
            else:
                await message.channel.send("Je n'ai pas pu obtenir de résultat.")
        except Exception as e:
            print(f"Erreur lors de la recherche Perplexity : {e}")
            await message.channel.send("Désolé, une erreur s'est produite lors du traitement de votre demande.")

client.run("TOKEN")