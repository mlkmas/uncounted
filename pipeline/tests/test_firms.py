from datetime import date

from uncounted import firms
from uncounted.cases import Case

SAMPLE = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
    "36.91234,31.40567,367.0,0.4,0.37,2021-07-28,1042,N,VIIRS,n,2,300.1,25.4,D,0\n"
    "36.91234,31.40567,330.0,0.4,0.37,2021-07-28,42,N,VIIRS,l,2,290.0,3.1,N,0\n"
)


class FakeResp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


def test_fetch_chunks_and_normalizes(monkeypatch):
    urls = []
    def fake_get(url, timeout):
        urls.append(url)
        return FakeResp(SAMPLE if url.endswith("2021-07-28") else SAMPLE.split("\n")[0] + "\n")
    monkeypatch.setattr(firms.requests, "get", fake_get)
    monkeypatch.setattr(firms.time, "sleep", lambda s: None)
    c = Case(case_id="t-fetch", kind="wildfire", region="R", bbox=[31.2, 36.7, 31.9, 37.2],
             period_start=date(2021, 7, 28), period_end=date(2021, 8, 8), fuel_mix={"extratropical_forest": 1.0})
    path, digest = firms.fetch_case(c, "KEY")
    # 12 days -> chunks of 5, 5, 2
    assert [u.rsplit("/", 2)[-2] for u in urls] == ["5", "5", "2"]
    assert urls[0].endswith("/KEY/VIIRS_SNPP_SP/31.2,36.7,31.9,37.2/5/2021-07-28")
    df = firms.load_snapshot(path)
    assert len(df) == 2 and set(df["acq_time"]) == {"1042", "0042"}
    # cached: a second fetch makes no new requests and gives the same hash
    n = len(urls)
    _, digest2 = firms.fetch_case(c, "KEY")
    assert len(urls) == n and digest2 == digest


def test_error_text_is_reported(monkeypatch):
    monkeypatch.setattr(firms.requests, "get", lambda url, timeout: FakeResp("Invalid MAP_KEY."))
    monkeypatch.setattr(firms.time, "sleep", lambda s: None)
    c = Case(case_id="t-err", kind="wildfire", region="R", bbox=[0, 0, 1, 1],
             period_start=date(2020, 1, 1), period_end=date(2020, 1, 2), fuel_mix={"extratropical_forest": 1.0})
    import pytest
    with pytest.raises(RuntimeError, match="Invalid MAP_KEY"):
        firms.fetch_case(c, "BAD")
