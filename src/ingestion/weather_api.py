import openmeteo_requests
import pandas as pd
from retry_requests import retry
import requests_cache
from datetime import datetime, timedelta
from ingestion import config

cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

url_historic = "https://archive-api.open-meteo.com/v1/archive"
params_historic = {
    "latitude": config.LATITUDE,
    "longitude": config.LONGITUDE,
    "start_date": config.BACKFILL_START_DATE,
    "end_date": (datetime.now() - timedelta(1)).strftime("%Y-%m-%d"),
    "daily": config.WEATHER_DAILY_VARS,
    "timezone": config.TIMEZONE,
}

url_forecast = "https://api.open-meteo.com/v1/forecast"
params_forecast = {
    "latitude": config.LATITUDE,
    "longitude": config.LONGITUDE,
    "daily": config.WEATHER_DAILY_VARS,
    "models": "meteoswiss_icon_ch1",
    "timezone": config.TIMEZONE,
    "forecast_days": 2,  # index 0 = today, index 1 = tomorrow
}


def get_weather(url, params) -> pd.DataFrame:
    """Pulls data from openmeteo weather API and parses it into a pandas DataFrame."""
    responses = openmeteo.weather_api(url=url, params=params)
    response = responses[0]
    daily = response.Daily()

    daily_data = {
        "date": pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left",
        ).tz_convert(response.Timezone().decode())
    }

    for i, var_name in enumerate(params["daily"]):
        daily_data[var_name] = daily.Variables(i).ValuesAsNumpy()

    forecast = pd.DataFrame(data=daily_data)

    return forecast


forecast_df = get_weather(url_forecast, params_forecast)
forecast_df["forecast_made_at"] = pd.Timestamp.now(tz="Europe/Zurich").normalize()
forecast_df["model"] = params_forecast["models"]

historic_df = get_weather(url_historic, params_historic)
historic_df["model"] = "best_match"
