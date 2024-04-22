## Video Summarization with AI on Google Colab

<a href="https://colab.research.google.com/github/martinopiaggi/summarize/blob/main/Summarize.ipynb" target="_parent">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>


Effortlessly summarize videos from multiple sources (YouTube, Dropbox, and Google Drive) in Google Colab using state-of-the-art AI models (free Groq cloud api).

![example](https://github.com/martinopiaggi/summarize/assets/72280379/14daff90-e472-4a72-8059-50a4c6f7eeb9)


## Features

- Provides a summary with timestamps for a precise overview of the content + original transcript
- Summarize videos from YouTube, Dropbox, and Google Drive.
- **Llama3-8b** AI models via the **free** Groq cloud API, or opt for OpenAI's GPT-3.5 without hitting Groq usage caps.
- Summaries based on auto generated captions for YouTube videos, and supports **Faster Whisper** for other sources or when captions are not available.
    
## Use Cases

- Get a quick summary of a lengthy video with timestamps
- Efficiently take notes on a video with a summary that captures key points
- Have a grammarly correct transcript of the video

[Example of summary](Video%20summaries%20examples/ngvOyccUzzY_captions_FINAL.md)

## Usage

1. Sign up or log into Groq Console or use OpenAI's ChatGPT for API access.
2. Obtain your unique API key from either service and input it into the Colab.
4. *Remember the Colab notebook settings to utilize a T4 GPU if using Faster Whisper (basically when the source is Dropbox or GDrive video link)*
5. Input the video URL selecting correct video source type
6. Run the needed cells
7. Summaries and transcripts can be downloaded or read directly in the browser using the colab file-explorer pane on the left.


