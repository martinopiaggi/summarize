from setuptools import setup, find_packages

# Define core requirements that are always needed
core_requirements = [
    "python-dotenv>=1.0.0",
    "youtube-transcript-api>=0.6.1",
    "pytubefix>=1.6.3", 
    "groq>=0.4.2",
    "openai>=1.3.7",
    "aiohttp>=3.9.0",
    "requests>=2.31.0",
    "wget>=3.2",
    "google-api-python-client>=2.0.0",
    "google-auth-httplib2>=0.1.0",
    "google-auth-oauthlib>=0.4.1",
    "dropbox>=11.36.2",
    "ffmpeg-python>=0.2.0"
]

extras_require = {
    'whisper': ['openai-whisper'],
    'all': ['openai-whisper']
}

setup(
    name="summarizer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=core_requirements,
    extras_require=extras_require,
    entry_points={
        "console_scripts": [
            "summarizer=summarizer.__main__:cli",
        ],
    },
    package_data={
        'summarizer': ['prompts.json'],
    },
    python_requires='>=3.7',
)