## Video Summarization with AI

<a href="https://colab.research.google.com/github/martinopiaggi/summarize/blob/main/Summarize.ipynb" target="_parent">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>


Effortlessly summarize videos from multiple sources (YouTube, Dropbox, Google Drive, local files) in Google Colab or locally, using state-of-the-art AI models (free Groq cloud api, OpenAI or any local model).

[](https://github.com/martinopiaggi/summarize/assets/72280379/f65eca0b-f61e-4aed-864f-8f86cc1722cf)

## Features

- Provides a summary with timestamps for a precise overview of the content + original transcript
- Summarize videos from YouTube, Dropbox, Google Drive or local files.
- **Llama3-8b** model via the **free** Groq cloud API, OpenAI's GPT-3.5 or local model (tested with LM Studio)
- Summaries based on auto generated captions for YouTube videos, and supports **Whisper** for other sources or when captions are not available.
    
## Use Cases

- Get a quick summary of a lengthy video with timestamps
- Efficiently take notes on a video with a summary that captures key points
- Have a grammarly correct transcript of the video

[Example of summary](Video%20summaries%20examples/ngvOyccUzzY_captions_FINAL.md)

## Colab usage

1. Sign up or log into Groq Console or use OpenAI's ChatGPT for API access.
2. Obtain your unique API key from either service and input it into the Colab.
4. *Remember the Colab notebook settings to utilize a T4 GPU if using Faster Whisper (basically when the source is Dropbox or GDrive video link)*
5. Input the video URL selecting correct video source type
6. Run the needed cells
7. Summaries and transcripts can be downloaded or read directly in the browser using the colab file-explorer pane on the left.


