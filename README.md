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

for CPU version
pip install -r requirements_CPU.txt

currently for GPU version install the CPU version and then instally pytorch based on your needs.