from setuptools import setup, find_packages

setup(
    name="summarizer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-dotenv>=1.0.0",
        "youtube-transcript-api>=0.6.1",
        "pytubefix>=1.6.3", 
        "openai-whisper>=20231117",
        "groq>=0.4.2",
        "openai>=1.3.7",
        "aiohttp>=3.9.0",
        "requests>=2.31.0",
        "wget>=3.2",
        "google-api-python-client>=2.0.0",
        "google-auth-httplib2>=0.1.0",
        "google-auth-oauthlib>=0.4.1",
        "dropbox>=11.36.2"
    ],
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