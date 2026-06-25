from databricks.sdk import WorkspaceClient
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET
from isodate import parse_duration
import pandas as pd

w = WorkspaceClient()
api_key = w.dbutils.secrets.get(scope="demand_pipeline", key="entsoe-api-key")


def get_respone(url, payload):
    response = requests.get(url=url, params=payload)
    xml_text = response.text

    return xml_text


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


def aggregate_daily(df: pd.DataFrame):
    daily = (
        df.set_index("datetime")
        .resample("D")["load_mw"]
        .agg(["mean", "max", "sum"])
        .rename(columns={"mean": "load_mw_mean", "max": "load_mw_max", "sum": "load_mwh_total"})
        .reset_index()
        .rename(columns={"datetime": "date"})
    )

    return daily
