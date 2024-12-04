import aiohttp
from discord import File
from io import BytesIO
import logging

logger = logging.getLogger('image_generator')

async def generate_image(prompt):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://image.pollinations.ai/prompt/{prompt}") as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.error(f"Erreur lors de la génération de l'image. Statut : {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'image : {e}")
        return None

