# YouTube Translation

Welcome to the YouTube Translation project! This Python application is designed to provide translations that are specific to predefined channels or contexts.

It is pulling EN or FR transcripts only, it will pick the first one and run with it.

## Features
- Translate content based on the specified YOUTUBE channel_ID.
- Add custom translation rules for each channel.
- Support for multiple languages via deep-translate https://pypi.org/project/deep-translator.
- Simple configuration and usage.
- adds silence to the audio to keep things in sync

## Getting Started

### Prerequisites
To run this project, ensure you have the following installed:
- Python 3.10 ~ 3.12 based on limitation from coqui-tts (https://pypi.org/project/coqui-tts/)
- setup the config.json file, see in samples the config.json.sample
- add voice samples in Samples folder sample.en.wav & sample.fr.wav

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/nuronce/YouTubeTranslation.git
   cd YouTubeTranslation
2. if you have a GPU go to https://pytorch.org/get-started/locally/ and pic the command that matches your setup.
   get the requirements
   ex: Cuda 12.8 & Windows
   ```bash
   pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
   ```
   ex: CPU & WIndows or MAC
   ```bash
   pip3 install torch torchvision torchaudio
   ```
   ex: Cuda 12.8 & Linux
   ```bash
   pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
   ```
3. To get all requirements installed
   ```bash
   pip install -r requirements_CPU.txt
4. Limits to what can be sent to convert at one time
   https://github.com/coqui-ai/TTS/discussions/3548
   If this changes need to change the config file
