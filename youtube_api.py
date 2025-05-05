import os
import glob
import sys
import json
import torch
import random
import time
import re
import structlog
import logging
import pysrt
import inflect
import ctypes
import time
import platform
import copy
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from deep_translator import GoogleTranslator
from tenacity import retry, stop_after_attempt, wait_fixed
from TTS.api import TTS
from pydub import AudioSegment
from datetime import datetime

# Constants for execution state
if platform.system() == "Windows":
    # Windows-specific logic
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    print("Sleep mode prevented on Windows.")
elif platform.system() == "Linux":
    # Linux-specific logic: Execute a command to prevent sleep
    os.system("caffeinate")  # Example: Use `caffeinate` on macOS/Linux

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

def srt_transcript(transcript, output_file):
    srt_content = []
    
    for idx, line in enumerate(transcript, start=1):
        start_time = format_time(line.start)
        end_time = format_time(line.start + line.duration)
        srt_content.append(f"{idx}\n{start_time} --> {end_time}\n{line.text}\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_content))


def format_time(seconds):
    millis = int((seconds - int(seconds)) * 1000)
    hours, minutes = divmod(int(seconds), 3600)
    minutes, secs = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
 

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
        os.makedirs(f"{root_dir}", exist_ok=True)
        srt_file = f"{root_dir}{video_id}.*.srt"

        try:
            z = glob.glob(srt_file)
            if len(z) == 1:
                original_language=z[0].split(".")[-2]
                log.warning("Transcript already exists", video_id=video_id, original_language=original_language)
                srt_file = z[0]
            else:
                # Fetch transcript in French or English
                transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                
                transcript_obj = transcripts.find_transcript(['fr','en'])
                original_language = transcript_obj.language_code
                transcript = transcript_obj.fetch(original_language)          
                srt_file = f"{root_dir}{video_id}.{original_language}.srt"
                srt_transcript(transcript, srt_file)

            srt = pysrt.open(srt_file)
            for lang in config['languages']:
                if original_language == lang:           
                    continue
                date = datetime.now()
                log.info("Processing transcript", original_language=original_language, video_id=video_id)
                process_language(srt, original_language, lang, root_dir, video_id)
                date2 = datetime.now()
                log.info("Processed transcript", original_language=original_language, video_id=video_id, duration=(date2 - date).total_seconds())

        except TranscriptsDisabled as e:
            log.error("Transcripts are disabled", video_id=video_id, error=str(e))
        #except YouTubeTranscriptApi.NoTranscriptFound as e:             log.error("Transcripts are missing", video_id=video_id, error=str(e))
        except Exception as e:
            log.error("Error processing video ID", video_id=video_id, error=str(e))
 
def translate_srt(srt_source, output_file, source_language, target_language, video_id):
    subs = copy.deepcopy(srt_source)

    translated_text = ""
    max_retries = 3
    
    for key,sub in enumerate(subs):
        retries = 0
    
        while retries < max_retries:
            try:
                if (source_language in (['cs','hi'])) and text.isnumeric():
                   p = inflect.engine()
                   text = p.number_to_words(sub.text, andword=" ")
                
                translated = ""
                translated = GoogleTranslator(source=source_language, target=target_language).translate(sub.text)
                
                if translated != "":
                    sub.text = translated 
                    log.info("Translated", key=key,of=len(subs)-1, target_language=target_language, video_id=video_id)
                    time.sleep(random.uniform(0, 1) ) 
                    break  # Exit the loop if translation is successful
                else:
                    log.error(f"Translation failed, Skipping Language", text=text, target_language=target_language, video_id=video_id, error=str(e))
                    raise Exception(f"Translation failed for {video_id}")

            except Exception as e:
                log.error("Error translating text", video_id=video_id, error=str(e))
                retries += 1
                time.sleep(random.uniform(5, 15) ) 

    subs.save(output_file, encoding="utf-8")


def process_language(srt_source, source_language, target_language, root_dir, video_id):

    translated_text = []
    original_text = ""

    log.info("Processing Language", target_language=target_language, video_id=video_id)
    translated_path= f"{root_dir}{target_language}/{video_id}.{target_language}.srt"
    try:
        if os.path.exists(f"{root_dir}{target_language}/{video_id}.{target_language}.wav"):
            log.warning("Audio already exists", target_language = target_language, video_id=video_id)
            return
        if os.path.exists(translated_path):
            subs = pysrt.open(translated_path)
            log.warning(f"Found Translation", target_language = target_language, video_id=video_id)
        else:
            os.makedirs(f"{root_dir}{target_language}/", exist_ok=True)  # Create directory if it doesn't exist
            translate_srt(srt_source, translated_path, source_language, target_language, video_id)

            subs = pysrt.open(translated_path)
             
        if config['generate_audio'] == False:
            return;
    
        audio_parts = []
        file_parts = []
        overage_duration = 0
        # Create voice
        for key, sub in enumerate(subs):
            if os.path.exists(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav"):
                file_parts.append(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
                tts_audio =AudioSegment.from_wav(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
                audio_parts.append(tts_audio)        
                continue

            log.info(f"Generating voice file",  key=key, of=len(subs)-1, target_language=target_language,video_id=video_id)
                     
            #split the processing for limitations of the TTS
            #make sure no other parts exist
            pattern = f"{root_dir}{target_language}/{video_id}.{key}-*.{target_language}.wav"
            files = glob.glob(pattern)

            for file in files:
                os.remove(file)

            process_text = ""
            words = sub.text.split(" ")
            sub_audio_parts = []
            sub_files = []
            parts_counter = 1


            for sub_key, sub_value in enumerate(words):  
                process_text += sub_value + " "
                if ((sub_key == len(words)-1)) or (len(process_text)+ len(words[sub_key+1]) > int(config['languages'][target_language])):
                    # Generate voice files
                    log.info(f"Generating voice file",  key=f"{key}.{parts_counter}", of=len(subs)-1, target_language=target_language,video_id=video_id)
                    filename = f"{root_dir}{target_language}/{video_id}.{key}-{parts_counter}.{target_language}.wav"
                    sub_files.append(filename)
                    tts.tts_to_file(text=process_text, file_path=filename
                                    ,language=target_language.lower()  # Specify the language
                                    ,speaker_wav=f"Samples/sample.{source_language}.wav", speed=1.05, temperature=0.81
                        
                        )
                    tts_audio =AudioSegment.from_wav(filename)
                    sub_audio_parts.append(tts_audio)
                    parts_counter += 1  
                    process_text = ""
                    continue

            #combine the sub-parts into one file    
            combined = sum(sub_audio_parts)
            combined.export(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav", format="wav")
            for f in sub_files:
                os.remove(f)

            file_parts.append(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
            log.info(f"Generated voice file",  key=key, of=len(subs)-1, target_language=target_language,video_id=video_id)
            
            tts_audio =AudioSegment.from_wav(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
            duration_original = (sub.end - sub.start).seconds
            duration_new = tts_audio.duration_seconds

            log.info("Timing", key=key, WAV_Duration=duration_new, SRT_Duration=duration_original)
            

            if duration_new > duration_original:
                overage_duration +=  (duration_new-duration_original) * 1000 
                continue
            elif duration_new < duration_original:
                silence_duration =  (duration_original-duration_new) * 1000 
                if (silence_duration < overage_duration):
                    overage_duration - silence_duration
                    continue
                else:
                    silence_duration = silence_duration - overage_duration
                    overage_duration = 0

                 # we'll append silence to the start and end of the audio 
                silence_duration = silence_duration / 2
                log.info(f"Appending voice file Silence to start & end", key=key,of=len(subs)-1 , target_language=target_language,video_id=video_id, silence_duration=silence_duration)
                shh = AudioSegment.silent(duration=silence_duration)
                tts_audio = shh + tts_audio + shh
                tts_audio.export(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav", format="wav")
                        
            log.info(f"Generated voice file", key=key,of=len(subs)-1 , target_language=target_language,video_id=video_id)
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

if ('ffmpeg_Path' in config) and (config['ffmpeg_Path'] != ""):
    AudioSegment.converter = config['ffmpeg_Path']

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"
log.info(f"Using device: {device}")

if config['generate_audio'] == True:
    tts = TTS(model_name=config['Coqui-TTS']['model']).to(device)

    log.info(f"Using TTS model: {config['Coqui-TTS']['model']}")

for channel_id in config['YOUTUBE']['CHANNELIDs']:
    log.info(f"Processing channel" ,channel_id=channel_id)
    video_ids = get_video_ids_from_channel(config['YOUTUBE']['APIKEY'], channel_id)
    log.info(f"Found {len(video_ids)} videos in channel",channel_id=channel_id)

    process_transcripts(video_ids)
    log.info(f"Processed channel",channel_id=channel_id)

