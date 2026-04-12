from app import coerce_int, normalize_config_section
from summarizer.api import chunk_text


def test_normalize_config_section_accepts_kebab_and_snake_case():
    normalized = normalize_config_section(
        {
            "chunk-size": 1200,
            "parallel-calls": 12,
            "max-tokens": 2048,
        }
    )

    assert normalized == {
        "chunk_size": 1200,
        "parallel_api_calls": 12,
        "max_output_tokens": 2048,
    }


def test_coerce_int_applies_fallback_and_bounds():
    assert coerce_int("bad", 1000, minimum=500, maximum=5000) == 1000
    assert coerce_int(20, 1000, minimum=500, maximum=5000) == 500
    assert coerce_int(9000, 1000, minimum=500, maximum=5000) == 5000


def test_chunk_text_changes_chunk_count_when_chunk_size_changes():
    transcript = "\n".join(
        f"00:00:{idx:02d} " + ("lorem ipsum dolor sit amet " * 12)
        for idx in range(12)
    )

    small_chunks = chunk_text(transcript, 500)
    large_chunks = chunk_text(transcript, 2000)

    assert len(small_chunks) > len(large_chunks)


def test_chunk_text_uses_same_minimum_as_streamlit():
    transcript = "\n".join(
        f"00:00:{idx:02d} " + ("alpha beta gamma delta " * 10)
        for idx in range(8)
    )

    assert chunk_text(transcript, 100) == chunk_text(transcript, 500)
