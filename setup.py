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
        "openai>=1.3.7"
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