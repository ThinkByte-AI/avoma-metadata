import uuid

import pytest

from app.ingestion.classify import FileKind, classify_key

MID = "8b4873e1-42b7-4fbc-8414-02205d45fdbf"
P = ["avoma/"]


@pytest.mark.parametrize(
    "key,kind",
    [
        (f"avoma/2025/02/{MID}/transcript.json", FileKind.TRANSCRIPT),
        (f"avoma/2025/02/{MID}/notes.md", FileKind.NOTES_MD),
        (f"avoma/2025/02/{MID}/notes.json", FileKind.NOTES_JSON),
        (f"avoma/2025/02/{MID}/recording.mp3", FileKind.AUDIO),
        (f"avoma/2025/02/{MID}/recording.mp4", FileKind.VIDEO),
    ],
)
def test_known_files(key, kind):
    c = classify_key(key, P)
    assert c.kind == kind
    assert c.meeting_id == uuid.UUID(MID)
    assert c.folder == f"avoma/2025/02/{MID}/"


@pytest.mark.parametrize(
    "key",
    [
        "_bootstrap/ec2_run.log",
        f"avoma/2025/13/{MID}/transcript.json",
        f"avoma/2025/00/{MID}/transcript.json",
        "avoma/2025/02/not-a-uuid/transcript.json",
        f"avoma/2025/02/{MID}/random.txt",
        f"avoma/2025/02/{MID}/sub/transcript.json",
        f"other/2025/02/{MID}/transcript.json",
        "avoma/",
        f"avoma/2025/02/{MID}/",
    ],
)
def test_unknown_files(key):
    c = classify_key(key, P)
    assert c.kind == FileKind.UNKNOWN and c.meeting_id is None and c.folder is None


def test_uppercase_uuid_normalised():
    c = classify_key(f"avoma/2025/02/{MID.upper()}/transcript.json", P)
    assert c.kind == FileKind.TRANSCRIPT and c.meeting_id == uuid.UUID(MID)


def test_prefix_without_trailing_slash_and_multiple_prefixes():
    c = classify_key(f"archive2/2024/11/{MID}/notes.md", ["avoma", "archive2"])
    assert c.kind == FileKind.NOTES_MD and c.folder == f"archive2/2024/11/{MID}/"
