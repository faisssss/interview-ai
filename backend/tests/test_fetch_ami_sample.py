import pytest

from scripts.fetch_ami_sample import sample_url


def test_sample_url_points_at_the_headset_mix():
    assert sample_url("ES2002b") == (
        "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2002b/audio/"
        "ES2002b.Mix-Headset.wav"
    )


@pytest.mark.parametrize("meeting_id", ["", "es2002b", "../ES2002b", "ES2002b/../x", "ES2002b?x=1"])
def test_sample_url_rejects_ids_that_are_not_ami_meetings(meeting_id):
    with pytest.raises(ValueError, match="AMI meeting ID"):
        sample_url(meeting_id)
