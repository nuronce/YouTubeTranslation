import os
import sys
import json
import torch
import random
import time
import re
import structlog
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from deep_translator import GoogleTranslator
from tenacity import retry, stop_after_attempt, wait_fixed
from TTS.api import TTS
from pydub import AudioSegment
from datetime import datetime

# Set up the logging module
log_filename = datetime.now().strftime("YouTube_Translation_log_%Y-%m-%d %H-%M.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(),  # Logs to the console
        logging.FileHandler(log_filename, mode="w")  # Logs to a file
    ]
)

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,  # Filters log level
        structlog.processors.TimeStamper(fmt="iso"),  # Adds timestamps
        structlog.processors.JSONRenderer()  # Logs as JSON
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),  # Uses Python's logging module
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Create a structlog logger
log = structlog.get_logger()

def get_video_ids_from_channel(api_key, channel_id):
    from googleapiclient.discovery import build
    youtube = build('youtube', 'v3', developerKey=api_key)

    # Get the uploads playlist ID
    channel_response = youtube.channels().list(
        part='contentDetails',
        id=channel_id
    ).execute()
    uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # Get video IDs from the uploads playlist
    video_ids = []
    next_page_token = None
    while True:
        playlist_response = youtube.playlistItems().list(
            part='contentDetails',
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        ).execute()
        video_ids.extend([item['contentDetails']['videoId'] for item in playlist_response['items']])
        next_page_token = playlist_response.get('nextPageToken')
        if not next_page_token:
            break

    return video_ids

def process_transcripts(video_ids):
    
    for video_id in video_ids:
        if config['YOUTUBE']['videoid_filter_Starts_With']!="" and re.match(config['YOUTUBE']['videoid_filter_Starts_With'], video_id) is None:
            log.warning("Invalid video ID", video_id = video_id)
            continue
        root_dir = f"{config['rootTranslations']}/{video_id}/"
        try:
            # Fetch transcript in French or English
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            
            transcript_obj = transcripts.find_transcript(['fr','en'])
            original_language = transcript_obj.language_code
            transcript = transcript_obj.fetch(original_language)          

            if os.path.exists(f"{root_dir}{video_id}.{original_language}.json"):
                with open(f"{root_dir}{video_id}.{original_language}.json", "r", encoding="utf-8") as json_file:
                    json_data = json.load(json_file)
            else:
                original_text = []
                txt = ""
                duration = 0
                for key, snip in enumerate(transcript.snippets):
                    txt += snip.text + " "
                    if duration == 0:
                        start = snip.start
                    duration += snip.duration
                    if (key == len(transcript.snippets)-1) or (snip.duration > 15) or (len( transcript.snippets[key+1].text + txt) > 210 ):
                        original_text.append({"text":txt,'duration':duration, 'start':start})
                        txt = ""
                        duration = 0
                    

                os.makedirs(f"{root_dir}", exist_ok=True)  # Create directory if it doesn't exist
                json_data = {'video_id':video_id,'language':original_language,'snips':original_text}

                with open(f"{root_dir}{video_id}.{original_language}.json", "w", encoding="utf-8") as json_file:
                    json.dump(json_data, json_file, indent=4)

            log.info("Found transcript", original_language=original_language, video_id=video_id)

            for lang in config['languages']:
                
                if original_language == lang:           
                    continue
                date = datetime.now()
                log.info("Processing transcript", original_language=original_language, video_id=video_id)
                process_language(json_data, lang)
                date2 = datetime.now()
                log.info("Processed transcript", original_language=original_language, video_id=video_id, duration=(date2 - date).total_seconds())

        except TranscriptsDisabled as e:
            log.error("Transcripts are disabled", video_id=video_id, error=str(e))
        #except YouTubeTranscriptApi.NoTranscriptFound as e:             log.error("Transcripts are missing", video_id=video_id, error=str(e))
        except Exception as e:
            log.error("Error processing video ID", video_id=video_id, error=str(e))

def process_language(source_json, target_language):

    translated_text = []
    original_text = ""
    video_id = source_json['video_id']
    root_dir = f"{config['rootTranslations']}/{video_id}/"

    log.info("Processing Language", target_language=target_language, video_id=video_id)
            
    try:
        json_data = ""
        if os.path.exists(f"{root_dir}{target_language}/{video_id}.{target_language}.wav"):
            log.warning("Audio already exists", target_language = target_language, video_id=video_id)
            return
        if os.path.exists(f"{root_dir}{target_language}/{video_id}.{target_language}.json"):
            with open(f"{root_dir}{target_language}/{video_id}.{target_language}.json", "r", encoding="utf-8") as json_file:
                json_data = json.load(json_file)
            log.warning(f"Found Translation", target_language = target_language, video_id=video_id)
        else:
            os.makedirs(f"{root_dir}{target_language}/", exist_ok=True)  # Create directory if it doesn't exist
            # Translate to target_language
            for key, snip in enumerate(source_json['snips']):
                retries = 0
                max_retries = 3
                translated = ""
                while retries < max_retries:
                    try:
                        translated = GoogleTranslator(source=source_json['language'], target=target_language).translate(snip['text'])     
                        log.info("Translated", key=key, of=len(source_json['snips'])-1, target_language=target_language, video_id=video_id)
                        time.sleep(random.uniform(0, 1) ) 
                    except Exception as e:
                        log.error("Error translating text", video_id=video_id, error=str(e))
                        retries += 1
                        time.sleep(random.uniform(5, 15) ) 
                    else:
                        break  # Exit the loop if translation is successful
                if translated == "":
                    log.error(f"Translation failed, Skipping Language", text=trans_text, target_language=target_language, video_id=video_id, error=str(e))
                    return

                #translated = translate_with_tenacity(source=source_json['language'], target=target_language, text=trans_text)                   
                                
                translated_text.append({"text":translated,'original_duration':snip['duration'], 'start':snip['start']})
                trans_text = ""
            
            log.info("Translated",  target_language=target_language, video_id=video_id)

            json_data = {'video_id':video_id,'original_language':source_json['language'],'language':target_language,'snips':translated_text}

            with open(f"{root_dir}{target_language}/{video_id}.{target_language}.json", "w", encoding="utf-8") as json_file:
                json.dump(json_data, json_file, indent=4)
    
        audio_parts = []
        file_parts = []
        start = 0

        # Create voice
        for key, value in enumerate(json_data['snips']):
            if os.path.exists(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav"):
                file_parts.append(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
                tts_audio =AudioSegment.from_wav(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
                start += tts_audio.duration_seconds
                continue
            log.info(f"Generating voice file",  key=key, of=len(json_data['snips'])-1, target_language=target_language,video_id=video_id)
                     
            # Generate voice files
            tts.tts_to_file(text=value['text'], file_path=f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav"
                            ,language=target_language.lower()  # Specify the language
                            ,speaker_wav=f"Samples/sample.{source_json['language']}.wav", speed=1.05, temperature=0.81
                
                )
            
            file_parts.append(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")

            tts_audio =AudioSegment.from_wav(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
            
            log.info("Timing", key=key, Time=start, Start=value['start'])
            
            if start < value['start']:
                silence_duration = (value['start'] - start) * 1000 
                
                if start == 0:
                    silence_duration /= 2 #not all of it for the first one
                 
                 # we'll append silence to the start and end of the audio and it's a bit off possibly because of the TTS speed and different langages
                silence_duration = silence_duration * .90 / 2
                log.info(f"Appending voice file Silence to start & end", key=key,of=len(json_data['snips'])-1 , target_language=target_language,video_id=video_id, silence_duration=silence_duration)
                shh = AudioSegment.silent(duration=silence_duration)
                tts_audio = shh + tts_audio + shh
                tts_audio.export(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav", format="wav")
            
            start += tts_audio.duration_seconds
            
            log.info(f"Generated voice file", key=key,of=len(json_data['snips'])-1 , target_language=target_language,video_id=video_id)
            audio_parts.append(tts_audio)                  
        
        log.info("Generated all voice files", target_language=target_language,video_id=video_id)

        # Combine the voice files into one
        combined = sum(audio_parts)
        combined.export(f"{root_dir}{target_language}/{video_id}.{target_language}.wav", format="wav")
                          
        log.info("Generated voice file for video ID", target_language=target_language,video_id=video_id)
        
        for f in file_parts:
            os.remove(f)

        log.info("Removed voice part files", target_language=target_language,video_id=video_id)

    except Exception as e:
        log.error("Error processing",  target_language=target_language,video_id=video_id, error=str(e))

# Define the translation function with retry logic  not working for some reason
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))  
def translate_with_tenacity(source_language, target_language, text):
    s = GoogleTranslator(source=source_language, target=target_language).translate(text)                   
    return s 
 
if (sys.flags.utf8_mode != 1):
    log.error("Setting default encoding to utf-8")
    exit()

def load_config(config_path="config.json"):
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}
config = load_config()

if (config['ffmpeg_Path'] != ""):
    AudioSegment.converter = config['ffmpeg_Path']

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"
log.info(f"Using device: {device}")

tts = TTS(model_name=config['Coqui-TTS']['model']).to(device)

log.info(f"Using TTS model: {config['Coqui-TTS']['model']}")

for channel_id in config['YOUTUBE']['CHANNELIDs']:
    log.info(f"Processing channel" ,channel_id=channel_id)
    video_ids = get_video_ids_from_channel(config['YOUTUBE']['APIKEY'], channel_id)
    log.info(f"Found {len(video_ids)} videos in channel",channel_id=channel_id)

    process_transcripts(video_ids)
