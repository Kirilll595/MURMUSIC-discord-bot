import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import googleapiclient.discovery

# YouTube API Key
YOUTUBE_API_KEY = "your_api_key_youtube_music"

# Очередь песен
queue = []
# Чат для команд
allowed_channel_id = None

intents = discord.Intents.default()
intents.messages = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

paused = False  # Флаг для состояния паузы

def ensure_download_folder():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

async def check_channel(interaction: discord.Interaction):
    if allowed_channel_id and interaction.channel.id != allowed_channel_id:
        await interaction.response.send_message("Команды можно использовать только в разрешенном чате!", ephemeral=True)
        return False
    return True

async def search_youtube(query, max_results=5):
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    request = youtube.search().list(
        part="snippet",
        q=query,
        maxResults=max_results,
        type="video"
    )
    response = request.execute()
    videos = [(item["snippet"]["title"], f"https://www.youtube.com/watch?v={item['id']['videoId']}") for item in response["items"]]
    return videos

async def autocomplete_play(interaction: discord.Interaction, current: str):
    videos = await search_youtube(current, max_results=5)
    return [discord.app_commands.Choice(name=title, value=url) for title, url in videos]

@tree.command(name="set_channel", description="Установить канал для команд (только для админов)")
@commands.has_permissions(administrator=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    global allowed_channel_id
    allowed_channel_id = channel.id
    await interaction.response.send_message(f'Теперь команды можно использовать только в {channel.mention}')

@tree.command(name="join", description="Подключить бота к голосовому каналу и замутить себя")
async def join(interaction: discord.Interaction):
    if not await check_channel(interaction):
        return
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        vc = await channel.connect()
        await interaction.response.send_message(f'Подключился к {channel}')
        
        # Мутим бота после подключения
        await interaction.guild.me.edit(mute=True)
    else:
        await interaction.response.send_message("Вы должны быть в голосовом канале!", ephemeral=True)

@tree.command(name="leave", description="Отключить бота от голосового канала")
async def leave(interaction: discord.Interaction):
    if not await check_channel(interaction):
        return
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Отключился от канала!")
    else:
        await interaction.response.send_message("Я не в голосовом канале!", ephemeral=True)

@tree.command(name="play", description="Воспроизвести музыку по названию или ссылке")
@discord.app_commands.autocomplete(query=autocomplete_play)
async def play(interaction: discord.Interaction, query: str):
    if not await check_channel(interaction):
        return
    await interaction.response.defer()
    ensure_download_folder()
    
    videos = await search_youtube(query, max_results=1)
    if not videos:
        await interaction.followup.send("Не удалось найти песню на YouTube.")
        return
    
    video_url = videos[0][1]
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/song.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = ydl.prepare_filename(info)
        filename = filename.replace(".webm", ".mp3").replace(".m4a", ".mp3")
    
    if interaction.guild.voice_client is None:
        await join(interaction)
    
    vc = interaction.guild.voice_client
    if vc.is_playing():
        queue.append(filename)
        await interaction.followup.send(f'Добавлено в очередь: {query}')
    else:
        vc.play(discord.FFmpegPCMAudio(filename), after=lambda e: play_next(vc))
        await interaction.followup.send(f'Сейчас играет: {query}')

async def play_next(vc):
    if queue:
        next_song = queue.pop(0)
        vc.play(discord.FFmpegPCMAudio(next_song), after=lambda e: play_next(vc))

@tree.command(name="pause", description="Поставить музыку на паузу")
async def pause(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("Музыка поставлена на паузу!")
    else:
        await interaction.response.send_message("Сейчас ничего не играет!", ephemeral=True)

@tree.command(name="resume", description="Возобновить музыку после паузы")
async def resume(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("Музыка продолжена!")
    else:
        await interaction.response.send_message("Музыка не на паузе!", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Бот {bot.user.name} запущен!')

bot.run('your_token')
