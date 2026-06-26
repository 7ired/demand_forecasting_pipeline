from databricks.sdk import WorkspaceClient
from datetime import timedelta, date
import requests
import xml.etree.ElementTree as ET
from isodate import parse_duration
import pandas as pd
from . import config

w = WorkspaceClient()
api_key = w.dbutils.secrets.get(scope="demand_pipeline", key="entsoe-api-key")


def parse_xml_load(xml_text):
    root = ET.fromstring(xml_text)
    namespace = {"ns": f"{root[0].tag.removeprefix('{').removesuffix('}mRID')}"}
    rows = []

    for ts in root.findall("ns:TimeSeries", namespace):
        for period in ts.findall("ns:Period", namespace):
            start = pd.to_datetime(period.find("ns:timeInterval/ns:start", namespace).text)
            resolution = parse_duration(period.find("ns:resolution", namespace).text)

            for point in period.findall("ns:Point", namespace):
                position = int(point.find("ns:position", namespace).text)
                quantity = float(point.find("ns:quantity", namespace).text)
                timestamp = start + (position - 1) * resolution

                rows.append({"datetime": timestamp, "load_mw": quantity})

    return pd.DataFrame(rows)


def get_historic_load(start_date: str, end_date: str) -> pd.DataFrame:
    """start_date/end_date as YYYY-MM-DD strings. Loops year-by-year to respect api limits."""
    chunks = []
    current_start = pd.to_datetime(start_date)
    final_end = pd.to_datetime(end_date)

    while current_start < final_end:
        chunk_end = min(current_start + pd.DateOffset(years=1), final_end)

        params = {
            "securityToken": api_key,
            "documentType": "A65",
            "processType": "A16",
            "outBiddingZone_Domain": "10YCH-SWISSGRIDZ",
            "periodStart": current_start.strftime("%Y%m%d%H%M"),
            "periodEnd": chunk_end.strftime("%Y%m%d%H%M"),
        }

        response = requests.get(url=config.URL_ENTSOE, params=params)
        response.raise_for_status()
        chunks.append(parse_xml_load(response.text))

        current_start = chunk_end

    return pd.concat(chunks, ignore_index=True)


def get_latest_load() -> pd.DataFrame:
    """Pulls yesterday's actual load — the daily incremental append."""

    yesterday = date.today() - timedelta(days=1)

    params = {
        "securityToken": api_key,
        "documentType": "A65",
        "processType": "A16",
        "outBiddingZone_Domain": "10YCH-SWISSGRIDZ",
        "periodStart": yesterday.strftime("%Y%m%d0000"),
        "periodEnd": date.today().strftime("%Y%m%d0000"),
    }

    response = requests.get(url=config.URL_ENTSOE, params=params)
    response.raise_for_status()

    xml_load = parse_xml_load(response.text)

    return pd.DataFrame(xml_load)


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.set_index("datetime")
        .resample("D")["load_mw"]
        .agg(["mean", "max", "sum"])
        .rename(columns={"mean": "load_mw_mean", "max": "load_mw_max", "sum": "load_mwh_total"})
        .reset_index()
        .rename(columns={"datetime": "date"})
    )

    return daily
