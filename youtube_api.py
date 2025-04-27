import os
import json
import torch
import random
import time
import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from deep_translator import GoogleTranslator
from tenacity import retry, stop_after_attempt, wait_fixed
from TTS.api import TTS
from pydub import AudioSegment
from datetime import datetime

def print_log(message, error=False):
    if  error:
        print(f"\033[31m{datetime.now()} - ERROR: {message}\033[31m")
    else:
        print(f"{datetime.now()} - {message}")

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
            print_log(f"Invalid video ID: {video_id}", True)
            continue
        root_dir = f"{config['rootTranslations']}/{video_id}/"
        try:
            # Fetch transcript in French
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            
            transcript_obj = transcripts.find_transcript(['fr','en'])
            original_language = transcript_obj.language_code
            transcript = transcript_obj.fetch(original_language)          

            if os.path.exists(f"{root_dir}{video_id}.{original_language}.json"):
                with open(f"{root_dir}{video_id}.{original_language}.json", "r") as json_file:
                    json_data = json.load(json_file)
            else:
                original_text = []
                txt = ""
                duration = 0
                for snip in transcript.snippets:
                    txt += snip.text + " "
                    duration += snip.duration
                    if snip.duration <= 6:                  
                        original_text.append({"text":txt,'duration':duration})
                        txt = ""
                        duration = 0

                os.makedirs(f"{root_dir}", exist_ok=True)  # Create directory if it doesn't exist
                json_data = {'video_id':video_id,'language':original_language,'snips':original_text}

                with open(f"{root_dir}{video_id}.{original_language}.json", "w") as json_file:
                    json.dump(json_data, json_file, indent=4)

            print_log(f"Found transcript in {original_language} for video ID: {video_id}")

            for lang in config['languages']:
                
                if original_language == lang:           
                    continue
                date = datetime.now()
                print_log(f"Processing transcript in {original_language} for video ID: {video_id}")
                process_language(json_data, lang)
                date2 = datetime.now()
                print_log(f"Processed transcript in {original_language} for video ID: {video_id} in {(date2-date)}")

        except TranscriptsDisabled:
            print_log(f"Transcripts are disabled for video ID: {video_id}", True)
        #except NoTranscriptAvailable:            print(f"No French or English transcript available for video ID: {video_id}")
        except Exception as e:
            print_log(f"Error processing video ID {video_id}: {e}", True)

def process_language(source_json, target_language):

    translated_text = []
    original_text = ""
    video_id = source_json['video_id']
    root_dir = f"{config['rootTranslations']}/{video_id}/"

    print_log(f"Processing Language {target_language} for video ID: {video_id}")
            
    try:
        json_data = ""
        if os.path.exists(f"{root_dir}{target_language}/{video_id}.{target_language}.wav"):
            print_log(f"Already exists {target_language} audio for video ID: {video_id}")
            return
        if os.path.exists(f"{root_dir}{target_language}/{video_id}.{target_language}.json"):
            with open(f"{root_dir}{target_language}/{video_id}.{target_language}.json", "r") as json_file:
                json_data = json.load(json_file)
            print_log(f"Found Translation for {target_language} for video ID: {video_id}")
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
                        print_log(f"Translated {key}:{len(source_json['snips'])}")
                        time.sleep(random.uniform(0, 2) ) 
                    except Exception as e:
                        print_log(f"Error translating text: {e}", True)
                        retries += 1
                        time.sleep(random.uniform(5, 15) ) 
                    else:
                        break  # Exit the loop if translation is successful
                if translated == "":
                    print_log(f"Translation {target_language} for {trans_text} failed after {max_retries} attempts. Skipping this language.")
                    return

                #translated = translate_with_tenacity(source=source_json['language'], target=target_language, text=trans_text)                   
                                
                translated_text.append({"text":translated,'original_duration':snip['duration']})
                trans_text = ""
            print_log(f"Translated for {target_language} for video ID: {video_id}")

            json_data = {'video_id':video_id,'original_language':source_json['language'],'language':target_language,'snips':translated_text}

            with open(f"{root_dir}{target_language}/{video_id}.{target_language}.json", "w") as json_file:
                json.dump(json_data, json_file, indent=4)
    
        audio_parts = []
        file_parts = []

        # Create voice
        for key, value in enumerate(json_data['snips']):
            if os.path.exists(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav"):
                file_parts.append(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
                continue
            print_log(f"Generating voice file {key} for {target_language} for video ID: {video_id}")
            # Generate voice files
            tts.tts_to_file(text=value['text'], file_path=f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav"
                            ,language=target_language.lower()  # Specify the language
                            ,speaker_wav="Samples/sample.en.wav", speed=1.1, temperature=0.81
                
                )
            
            file_parts.append(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")

            tts_audio =AudioSegment.from_wav(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav")
            if tts_audio.duration_seconds < value['original_duration']:
                silence_duration = (value['original_duration'] - tts_audio.duration_seconds) * 1000 
                shh = AudioSegment.silent(duration=silence_duration)
                tts_audio = tts_audio.append(shh, crossfade=min(len(shh), len(tts_audio)))
                #tts_audio.export(f"{root_dir}{target_language}/{video_id}.{key}.{target_language}.wav", format="wav")  
            
            print_log(f"Generated voice file {key}:{len(json_data['snips'])} for {target_language} for video ID: {video_id}")
            audio_parts.append(tts_audio)                  
        
        print_log(f"Generated all voice files for {target_language} for video ID: {video_id}")

        # Combine the voice files into one
        combined = sum(audio_parts)
        combined.export(f"{root_dir}{target_language}/{video_id}.{target_language}.wav", format="wav")
                          
        print_log(f"Generated voice file for video ID: {video_id} in {target_language}")
        
        for f in file_parts:
            os.remove(f)

        print_log(f"Removed voice part files for video ID: {video_id} in {target_language}")

    except Exception as e:
        print_log(f"Error processing video ID {video_id}: {e}", True)

# Define the translation function with retry logic  not working for some reason
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))  
def translate_with_tenacity(source_language, target_language, text):
    s = GoogleTranslator(source=source_language, target=target_language).translate(text)                   
    return s 


def load_config(config_path="config.json"):
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        return {}
config = load_config()



# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"
print_log(f"Using device: {device}")

tts = TTS(model_name=config['Coqui-TTS']['model']).to(device)

print_log(f"Using TTS model: {config['Coqui-TTS']['model']}")

for channel_id in config['YOUTUBE']['CHANNELIDs']:
    print_log(f"Processing channel ID: {channel_id}")
    video_ids = get_video_ids_from_channel(config['YOUTUBE']['APIKEY'], channel_id)
    print_log(f"Found {len(video_ids)} videos in channel ID: {channel_id}")

    process_transcripts(video_ids)


