"""Sources with exactly the same content as another one (mirrors, copies) aren't downloaded every run."""

from proxyscraper import sources as srcs

DAY = 86400.0
NOW = 1_000_000.0
LIST = b"1.2.3.4:80\n5.6.7.8:8080\n"


def stats(tmp_path):
    st = srcs.SourceStats(tmp_path / "s.json")
    st.record_fetch("https://a.example/http.txt", b"old", 2, now=NOW - 5 * DAY)  # known for longer
    st.record_fetch("https://a.example/http.txt", LIST, 2, now=NOW)
    st.record_fetch("https://mirror.example/http.txt", LIST, 2, now=NOW + 5)      # same run, same content
    return st


def test_the_copy_is_skipped_while_the_original_is_fetched(tmp_path):
    st = stats(tmp_path)
    plan = {"https://a.example/http.txt": "http", "https://mirror.example/http.txt": "http"}
    kept, dropped = st.drop_duplicates(plan, now=NOW + 3600)
    assert kept == {"https://a.example/http.txt": "http"} and dropped == 1


def test_survives_a_save(tmp_path):
    st = stats(tmp_path)
    st.save()
    again = srcs.SourceStats(tmp_path / "s.json")
    plan = {"https://a.example/http.txt": "http", "https://mirror.example/http.txt": "http"}
    assert again.drop_duplicates(plan, now=NOW + 3600)[1] == 1


def test_once_a_day_the_copy_is_fetched_anyway(tmp_path):
    st = stats(tmp_path)
    plan = {"https://a.example/http.txt": "http", "https://mirror.example/http.txt": "http"}
    assert st.drop_duplicates(plan, now=NOW + srcs.DUP_RECHECK + 60) == (plan, 0)


def test_not_when_the_original_is_not_fetched_or_reads_it_as_another_type(tmp_path):
    st = stats(tmp_path)
    assert st.drop_duplicates({"https://mirror.example/http.txt": "http"}, now=NOW + 60)[1] == 0
    plan = {"https://a.example/http.txt": "http", "https://mirror.example/http.txt": "socks5"}
    assert st.drop_duplicates(plan, now=NOW + 60)[1] == 0


def test_content_that_drifts_apart_is_no_copy_anymore(tmp_path):
    st = stats(tmp_path)
    st.record_fetch("https://mirror.example/http.txt", b"9.9.9.9:80\n", 1, now=NOW + DAY)
    plan = {"https://a.example/http.txt": "http", "https://mirror.example/http.txt": "http"}
    assert st.drop_duplicates(plan, now=NOW + DAY + 60)[1] == 0


def test_lists_fetched_in_different_runs_are_not_compared(tmp_path):
    st = srcs.SourceStats(tmp_path / "s.json")
    st.record_fetch("https://a.example/http.txt", LIST, 2, now=NOW)
    st.record_fetch("https://b.example/http.txt", LIST, 2, now=NOW + DAY)  # a day later: same content by chance
    plan = {"https://a.example/http.txt": "http", "https://b.example/http.txt": "http"}
    assert st.drop_duplicates(plan, now=NOW + DAY + 60)[1] == 0
